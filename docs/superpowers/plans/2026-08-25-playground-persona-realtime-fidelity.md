# Playground Persona and Realtime Fidelity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make local Playground survey and chatbot runs use complete canonical personas, real model output, and stable realtime single/batch rendering without polling flicker.

**Architecture:** Restore the canonical persona envelope and a focused host-native worker. Survey answers and chatbot turns flow through their real runners into a locked job event journal; a job-scoped SSE endpoint replays it by byte cursor. One typed frontend stream feeds idempotent per-trial state for both single and batch cockpits, with terminal debrief data merged into live state.

**Tech Stack:** Python 3.12, FastAPI/Starlette, NDJSON plus `fcntl.flock`, pytest, React 18, TypeScript, EventSource, Vitest, Vite.

**Spec:** `docs/superpowers/specs/2026-08-25-playground-persona-realtime-fidelity-design.md`

## Global Constraints

- The Persona profile shown in a run is the exact persona block used for inference.
- Sampling/focus fields select or aggregate cohorts only; they never filter the persona prompt.
- Never represent a synthetic answer, turn, score, or positive feedback as model output.
- Chat defaults to at least 5 meaningful exchanges and at most the configured maximum (UI default 8).
- One resumable job SSE connection carries every persona/trial event.
- Preserve current Web/OpenHands and OS-app semantics.
- Preserve unrelated uncommitted user changes; reconcile only overlapping realtime and sidecar edits.
- Every behavior change follows RED, GREEN, REFACTOR in that order.

---

### Task 1: Restore the canonical persona envelope

**Files:**
- Modify: `packages/playground/src/playground/types.py`
- Modify: `packages/playground/src/playground/user_sim/prompt.py`
- Modify: `application/playground/backend/service/harbor_trial_debrief.py`
- Modify: `packages/playground/src/playground/tests/test_persona.py`
- Modify: `application/playground/backend/tests/test_inprocess_survey_prompt.py`

**Interfaces:**
- Consumes: canonical persona YAML accepted by `load_persona(path)`.
- Produces: `Persona.from_dict(data, *, persona_path="")`, complete `dimensions`, `schema_version`, `persona_path`, and `render_persona_block(persona, *, persona_yaml_path=None) -> str`.

- [ ] **Step 1: Write failing complete-envelope tests**

```python
def test_persona_envelope_round_trips_every_dimension():
    dims = {f"dimension_{i}": f"value-{i}" for i in range(50)}
    persona = Persona.from_dict(
        {"persona_id": "mai", "schema_version": "persona.v1", "dimensions": dims},
        persona_path="personas/mai.yaml",
    )
    assert persona.dimensions == dims
    assert persona.to_dict()["dimensions"]["dimension_49"] == "value-49"
    assert persona.persona_path == "personas/mai.yaml"
    assert "Key Attributes" not in persona.context

def test_persona_prompt_renders_late_dimension_from_canonical_path(tmp_path: Path):
    path = _write_dims_yaml(
        tmp_path / "mai.yaml", persona_id="mai",
        **{f"dimension_{i}": f"value-{i}" for i in range(49)},
        cog_attention_span="Long",
    )
    persona = Persona.from_dict(
        {"persona_id": "mai", "dimensions": {"cog_attention_span": "Long"}},
        persona_path=str(path),
    )
    assert "Long" in persona_system_prompt(persona)

def test_dimension_persona_requires_canonical_source():
    persona = Persona.from_dict({"persona_id": "mai", "dimensions": {"cog_attention_span": "Long"}})
    with pytest.raises(ValueError, match="canonical persona path"):
        persona_system_prompt(persona, persona_yaml_path="")
```

- [ ] **Step 2: Run tests and verify RED**

```bash
PYTHONPATH=packages/playground/src:application/playground uv run pytest packages/playground/src/playground/tests/test_persona.py application/playground/backend/tests/test_inprocess_survey_prompt.py -q
```

Expected: FAIL because `Persona` lacks canonical envelope fields and still truncates at `active_dims[:35]`.

- [ ] **Step 3: Implement the envelope and strict renderer**

```python
dimensions: Dict[str, Any] = field(default_factory=dict)
schema_version: str = ""
persona_path: str = ""

@classmethod
def from_dict(cls, d: Dict[str, Any], *, persona_path: str = "") -> "Persona":
    dimensions = d.get("dimensions")
    return cls(
        id=str(d.get("id") or d.get("persona_id") or "unknown"),
        name=str(d.get("name") or d.get("display_name") or d.get("persona_id") or "unknown"),
        summary=str(d.get("summary") or ""), context=str(d.get("context") or ""),
        source=str(d.get("source") or ""), preferences=list(d.get("preferences", [])),
        dislikes=list(d.get("dislikes", [])), constraints=list(d.get("constraints", [])),
        goal=str(d.get("goal") or ""),
        communication_style=str(d.get("communicationStyle", d.get("communication_style", ""))),
        dimensions=dict(dimensions) if isinstance(dimensions, dict) else {},
        schema_version=str(d.get("schema_version", d.get("schemaVersion", "")) or ""),
        persona_path=str(persona_path or d.get("persona_path") or d.get("personaPath") or ""),
    )
```

Add `dimensions`, `schemaVersion`, and `personaPath` to `to_dict`. In `render_persona_block`, prefer the explicit path, then `persona.persona_path`; a dimension-backed persona without a path raises `ValueError`. Do not swallow canonical loader/template errors. Retain `_persona_context` only for legacy personas with neither path nor dimensions. Update debrief loading to carry `persona_path` and all raw dimensions.

- [ ] **Step 4: Run the Step 2 command and verify GREEN**

Expected: PASS, including the 50th dimension and explicit missing-source failure.

- [ ] **Step 5: Commit**

```bash
git add packages/playground/src/playground/types.py packages/playground/src/playground/user_sim/prompt.py packages/playground/src/playground/tests/test_persona.py application/playground/backend/service/harbor_trial_debrief.py application/playground/backend/tests/test_inprocess_survey_prompt.py
git commit -m "fix: restore complete canonical persona prompts"
```

---

### Task 2: Generate and stream one truthful survey answer per question

**Files:**
- Modify: `packages/playground/src/playground/inprocess/survey_eval.py`
- Modify: `application/playground/backend/tests/test_inprocess_eval_runners.py`
- Modify: `application/playground/backend/tests/test_inprocess_survey_prompt.py`

**Interfaces:**
- Consumes: `SurveyInstrument`, Task 1 prompt, and a JSON completion client.
- Produces: `InvalidSurveyResponse(question_id, detail)`, `survey_question_started`, validated `survey_answer`, and partial `survey_progress` events.

- [ ] **Step 1: Write failing per-question and invalid-output tests**

```python
class ScriptedJSONClient:
    def __init__(self, payloads): self.payloads, self.calls = list(payloads), []
    def complete_json(self, system, user):
        self.calls.append({"system": system, "user": user})
        return self.payloads.pop(0)

def test_survey_calls_model_once_per_question_and_streams_in_order(tmp_path):
    client = ScriptedJSONClient([
        {"answer": {"questionId": "q1", "value": 4}},
        {"answer": {"questionId": "q2", "value": "b"}},
    ])
    instrument = SurveyInstrument(id="s", title="S", questions=[
        SurveyQuestion(id="q1", prompt="Rate", type="likert", min_value=1, max_value=5),
        SurveyQuestion(id="q2", prompt="Pick", type="single_choice", options=["a", "b"]),
    ])
    events = []
    result = InprocessSurveyEvalRunner()(
        _persona(), instrument, client=client, on_event=events.append,
        persona_yaml_path=_persona_yaml(tmp_path),
    )
    assert len(client.calls) == 2
    assert [a.value for a in result.answers] == [4, "b"]
    assert [e["type"] for e in events if e["type"].startswith("survey_")] == [
        "survey_question_started", "survey_answer", "survey_progress",
        "survey_question_started", "survey_answer", "survey_progress",
    ]

def test_invalid_choice_retries_once_then_fails_without_first_option(tmp_path):
    client = ScriptedJSONClient([
        {"answer": {"questionId": "q1", "value": "bad"}},
        {"answer": {"questionId": "q1", "value": "still-bad"}},
    ])
    with pytest.raises(InvalidSurveyResponse, match="q1"):
        InprocessSurveyEvalRunner()(
            _persona(),
            SurveyInstrument(id="s", title="S", questions=[SurveyQuestion(id="q1", prompt="Pick", type="single_choice", options=["a", "b"])]),
            client=client, persona_yaml_path=_persona_yaml(tmp_path),
        )
    assert len(client.calls) == 2
    assert "not one of" in client.calls[1]["user"]
```

- [ ] **Step 2: Run and verify RED**

```bash
PYTHONPATH=packages/playground/src:application/playground uv run pytest application/playground/backend/tests/test_inprocess_eval_runners.py application/playground/backend/tests/test_inprocess_survey_prompt.py -q
```

Expected: FAIL because the runner batches questions and `_default_value` invents midpoint/first-option answers.

- [ ] **Step 3: Implement strict one-question completion**

```python
class InvalidSurveyResponse(ValueError):
    def __init__(self, question_id: str, detail: str) -> None:
        super().__init__(f"Invalid model response for survey question {question_id}: {detail}")
        self.question_id, self.detail = question_id, detail

def _validate_answer(raw: Any, question: SurveyQuestion, instrument: SurveyInstrument) -> SurveyAnswer:
    payload = raw.get("answer") if isinstance(raw, dict) else None
    if not isinstance(payload, dict):
        raise InvalidSurveyResponse(question.id, "answer must be an object")
    answer = SurveyAnswer.from_dict(payload)
    if answer.question_id != question.id:
        raise InvalidSurveyResponse(question.id, "questionId does not match")
    if question.type == "likert":
        if isinstance(answer.value, bool) or not str(answer.value).strip().isdigit():
            raise InvalidSurveyResponse(question.id, "value must be an integer")
        answer.value = int(answer.value)
        if not question.min_value <= answer.value <= question.max_value:
            raise InvalidSurveyResponse(question.id, "value is outside the authored range")
    elif question.type == "single_choice" and str(answer.value) not in question.options:
        raise InvalidSurveyResponse(question.id, "value is not one of the authored option ids")
    elif question.type == "multi_choice":
        if not isinstance(answer.value, list) or not answer.value or any(str(v) not in question.options for v in answer.value):
            raise InvalidSurveyResponse(question.id, "values must be authored option ids")
        answer.value = [str(v) for v in answer.value]
    elif question.type == "free_text" and not str(answer.value or "").strip():
        raise InvalidSurveyResponse(question.id, "free-text value must not be empty")
    answer.rationale = answer.rationale if question.resolves_ask_rationale(instrument) else ""
    answer.confidence = answer.confidence if question.resolves_ask_confidence(instrument) else None
    return answer
```

Replace chunks with an authored-order question loop. Emit started before request; validate; retry once with the validation detail; emit answer/progress only after validation. Delete `_default_value` and every clamp/first-option fallback. Merge usage across all calls.

- [ ] **Step 4: Run the Step 2 command and verify GREEN**

- [ ] **Step 5: Commit**

```bash
git add packages/playground/src/playground/inprocess/survey_eval.py application/playground/backend/tests/test_inprocess_eval_runners.py application/playground/backend/tests/test_inprocess_survey_prompt.py
git commit -m "fix: stream truthful survey answers per question"
```

---

### Task 3: Enforce real multi-turn chatbot behavior and truthful failures

**Files:**
- Modify: `packages/playground/src/playground/types.py`
- Modify: `packages/playground/src/playground/chatbot_task_config.py`
- Modify: `packages/playground/src/playground/user_sim/session.py`
- Modify: `packages/playground/src/playground/user_sim/runner.py`
- Modify: `packages/playground/src/playground/inprocess/chatbot_eval.py`
- Modify: `packages/playground/src/playground/user_sim/sim_guidelines.md`
- Modify: `packages/playground/src/playground/tests/test_user_sim.py`
- Modify: `application/playground/backend/tests/test_inprocess_eval_runners.py`

**Interfaces:**
- Produces: `PlaygroundConfig.min_turns`, task `runtimeDefaults.minTurns`, `UserSimSession.next_action(observation, *, allow_end=True)`, `ApplicationUnavailable`, `inprocess_chatbot_config`, and `run_inprocess_chatbot_eval`.

- [ ] **Step 1: Write failing depth and retry tests**

```python
def test_runner_rejects_early_end_until_five_exchanges(monkeypatch):
    monkeypatch.setattr("playground.user_sim.runner.build_json_client", lambda *_: FakeSelfReportClient())
    session = FakeSession([{"assistantMessage": f"reply-{i}"} for i in range(5)])
    client = FakeToolStepClient([
        [ToolCall("send_message", {"message": "start"})],
        [ToolCall("end_conversation", {"reason": "satisfied"})],
        *[[ToolCall("send_message", {"message": f"follow-up {i}"})] for i in range(2, 6)],
        [ToolCall("end_conversation", {"reason": "satisfied"})],
    ])
    monkeypatch.setattr("playground.user_sim.runner.build_tool_step_client", lambda *_args, **_kwargs: client)
    result = run_playground(session, _persona(), "Meal assistant", PlaygroundConfig(min_turns=5, max_turns=8), created_at="2026-08-25T00:00:00Z")
    assert len(result.transcript) == 5
    assert result.transcript[-1].decision == "satisfied"

def test_maximum_below_minimum_is_rejected():
    with pytest.raises(ValueError, match="max_turns.*min_turns"):
        PlaygroundConfig(min_turns=5, max_turns=4)

def test_http_chatbot_retries_temporary_reply_then_returns_real_reply(monkeypatch):
    app = HTTPChatbotApplication(application_id="meal_planning_nutrition", default_context="meal", base_url="http://meal")
    replies = iter([
        {"sessionId": "s", "reply": "I'm temporarily unable to generate a reply. Please try again in a moment."},
        {"sessionId": "s", "reply": "What foods do you dislike?"},
    ])
    monkeypatch.setattr(app, "_request_json", lambda *_args, **_kwargs: next(replies))
    response = app.send_message(session_id=None, message="Help", title=None, context="meal", engine=None, bot_type="chat")
    assert response["reply"] == "What foods do you dislike?"
```

```python
def test_http_chatbot_persistent_temporary_reply_fails_after_three_attempts(monkeypatch):
    app = HTTPChatbotApplication(application_id="meal_planning_nutrition", default_context="meal", base_url="http://meal")
    calls = []
    def temporary(*_args, **_kwargs):
        calls.append(1)
        return {"sessionId": "s", "reply": "I'm temporarily unable to generate a reply. Please try again in a moment."}
    monkeypatch.setattr(app, "_request_json", temporary)
    with pytest.raises(ApplicationUnavailable, match="temporary failure"):
        app.send_message(session_id=None, message="Help", title=None, context="meal", engine=None, bot_type="chat")
    assert len(calls) == 3
```

- [ ] **Step 2: Run and verify RED**

```bash
PYTHONPATH=packages/playground/src:application/playground uv run pytest packages/playground/src/playground/tests/test_user_sim.py application/playground/backend/tests/test_inprocess_eval_runners.py -q
```

- [ ] **Step 3: Implement minimum turns and bounded retry**

Add `min_turns: int = 5` plus `__post_init__` validation to `PlaygroundConfig`; serialize `minTurns`. Parse `runtimeDefaults.minTurns` in `ChatbotRuntimeDefaults`.

```python
def next_action(self, observation: str, *, allow_end: bool = True) -> TurnAction:
    prompt = observation
    for _ in range(3):
        self._messages.append({"role": "user", "content": prompt})
        action = parse_tool_calls(self._client.complete_with_tools(self._messages))
        self._messages.append({"role": "assistant", "content": _format_assistant_turn(action)})
        if allow_end or not action.end_reason:
            return action
        prompt = "You have not completed at least 5 meaningful exchanges. Ask one specific natural follow-up based on the latest answer; do not end yet."
    raise RuntimeError("persona model repeatedly ended before the minimum conversation depth")
```

Call the next simulator action with `allow_end=index >= config.min_turns` in sync and async loops. Restore `inprocess_chatbot_config` and `run_inprocess_chatbot_eval` from commit `7afe320`, extended with minimum turns. Define `ApplicationUnavailable`; retry blank/recognized temporary replies or transport exceptions at most three total attempts. Remove invisible HTTP sidecar fallback and canned in-process success replies; provider failure propagates.

- [ ] **Step 4: Run Step 2 and verify GREEN**

- [ ] **Step 5: Commit**

```bash
git add packages/playground/src/playground/types.py packages/playground/src/playground/chatbot_task_config.py packages/playground/src/playground/user_sim/session.py packages/playground/src/playground/user_sim/runner.py packages/playground/src/playground/inprocess/chatbot_eval.py packages/playground/src/playground/user_sim/sim_guidelines.md packages/playground/src/playground/tests/test_user_sim.py application/playground/backend/tests/test_inprocess_eval_runners.py
git commit -m "fix: enforce truthful multi-turn chatbot evaluation"
```

---

### Task 4: Restore a focused host-native worker using real runners

**Files:**
- Create: `application/playground/backend/service/inprocess_trial_worker.py`
- Modify: `application/playground/backend/service/harbor_job_service.py`
- Create: `application/playground/backend/tests/test_inprocess_trial_worker.py`

**Interfaces:**
- Produces: `run_inprocess_trial(manifest_path, env, *, repo_root) -> int`; Harbor service delegates to it.

- [ ] **Step 1: Write failing worker behavior tests**

```python
def _write_manifest(tmp_path: Path) -> tuple[Path, Path]:
    persona = tmp_path / "personas" / "p.yaml"
    persona.parent.mkdir(parents=True)
    persona.write_text("persona_id: p\ndisplay_name: Pat\ndimensions:\n  decision_style: analytical\n")
    trials = tmp_path / "jobs" / "job"
    manifest = {
        "trial_name": "trial-p", "trials_dir": str(trials),
        "task": {"path": "application/tasks/chat_meal-planning-nutrition"},
        "agent": {"name": "persona-user-sim", "model_name": "test/model", "kwargs": {"persona_path": str(persona.relative_to(tmp_path))}},
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest))
    return path, trials / "trial-p"

def _playground_result() -> PlaygroundResult:
    turns = [PlaygroundTurn(turn_index=i, user_message=f"question-{i}", assistant_message=f"reply-{i}") for i in range(1, 6)]
    return PlaygroundResult(
        config=PlaygroundConfig(min_turns=5, max_turns=8),
        persona=Persona(id="p", name="Pat", dimensions={"decision_style": "analytical"}),
        sut_description="Meal assistant", transcript=turns,
        questionnaire=Questionnaire(3, "partial", 3, "partial", 3, "mixed", True, "asked"),
        metric_scores=MetricScores(num_turns=5), created_at="2026-08-25T00:00:00Z",
    )

def test_chat_worker_persists_actual_runner_result(monkeypatch, tmp_path):
    manifest, trial_dir = _write_manifest(tmp_path)
    expected = _playground_result()
    captured = {}
    def fake_run(persona, config, **kwargs):
        captured.update(persona=persona, config=config, kwargs=kwargs)
        return expected
    monkeypatch.setattr("backend.service.inprocess_trial_worker.run_inprocess_chatbot_eval", fake_run)
    assert run_inprocess_trial(manifest, {}, repo_root=tmp_path) == 0
    transcript = json.loads((trial_dir / "verifier" / "transcript.json").read_text())
    feedback = json.loads((trial_dir / "verifier" / "user_feedback.json").read_text())
    assert len(transcript["turns"]) == 5
    assert feedback["overallExperienceRating"] == 3
    assert captured["persona"].dimensions["decision_style"] == "analytical"

def test_survey_worker_persists_each_partial_progress(monkeypatch, tmp_path):
    manifest, trial_dir = _write_manifest(tmp_path)
    payload = json.loads(manifest.read_text())
    payload["task"]["path"] = "application/tasks/example-survey_product-feedback"
    payload["agent"]["name"] = "persona-json-survey"
    manifest.write_text(json.dumps(payload))
    class FakeRunner:
        def __call__(self, persona, instrument, config, **kwargs):
            answers = []
            for question_id, value in (("q1", 4), ("q2", "b")):
                answers.append(SurveyAnswer(question_id=question_id, value=value))
                partial = SurveyEvalResult(config, persona, instrument, list(answers), [], SurveyMetrics(len(instrument.questions), len(answers)), "2026-08-25T00:00:00Z")
                kwargs["on_event"]({"type": "survey_answer", "questionId": question_id, "value": value})
                kwargs["on_event"]({"type": "survey_progress", "result": partial.to_dict()})
            return partial
    monkeypatch.setattr("backend.service.inprocess_trial_worker.InprocessSurveyEvalRunner", FakeRunner)
    monkeypatch.setattr("backend.service.inprocess_trial_worker.survey_questionnaire_id_for_task_path", lambda *_args, **_kwargs: "fixture-survey")
    monkeypatch.setattr("backend.service.inprocess_trial_worker.get_survey_instrument", lambda *_args, **_kwargs: SurveyInstrument(id="s", title="S", questions=[SurveyQuestion(id="q1", prompt="Rate"), SurveyQuestion(id="q2", prompt="Pick", type="single_choice", options=["a", "b"])]))
    assert run_inprocess_trial(manifest, {}, repo_root=tmp_path) == 0
    events = [json.loads(line) for line in (trial_dir / "events.jsonl").read_text().splitlines()]
    assert [e["questionId"] for e in events if e["type"] == "survey_answer"] == ["q1", "q2"]
    assert json.loads((trial_dir / "verifier" / "survey_result.json").read_text())["metrics"]["numAnswered"] == 2
```

- [ ] **Step 2: Run and verify RED**

```bash
PYTHONPATH=packages/playground/src:application/playground uv run pytest application/playground/backend/tests/test_inprocess_trial_worker.py -q
```

Expected: collection FAIL because the worker module is absent.

- [ ] **Step 3: Extract and implement the worker**

Use the generic manifest/persona/artifact/result structure from commit `7afe320`. Use its survey/chat delegation with Tasks 2–3. Move the current HEAD web/other branch unchanged; do not restore obsolete `local-qwen-playwright` selection.

```python
def _inprocess_trial_worker(self, manifest_path: Path, env: dict[str, str]) -> int:
    from backend.service.inprocess_trial_worker import run_inprocess_trial
    return run_inprocess_trial(manifest_path, env, repo_root=self.repo_root)
```

Resolve canonical persona path against repo root and call `Persona.from_dict(payload, persona_path=str(path))`. Survey partial events atomically replace partial artifacts. Chat persists only the returned real transcript/result/self-report. Delete literal two-message and rating-9 construction.

- [ ] **Step 4: Run and verify GREEN**

```bash
PYTHONPATH=packages/playground/src:application/playground uv run pytest application/playground/backend/tests/test_inprocess_trial_worker.py application/playground/backend/tests/test_harbor_job_service.py -q
```

- [ ] **Step 5: Commit**

```bash
git add application/playground/backend/service/inprocess_trial_worker.py application/playground/backend/service/harbor_job_service.py application/playground/backend/tests/test_inprocess_trial_worker.py
git commit -m "refactor: restore faithful host-native trial worker"
```

---

### Task 5: Add locked job event journal and resumable SSE

**Files:**
- Modify: `packages/playground/src/playground/harbor/trial_events.py`
- Replace: `application/playground/backend/api/sse_stream.py`
- Modify: `application/playground/backend/api/app.py`
- Modify: `application/playground/backend/service/harbor_job_service.py`
- Modify: `application/playground/backend/tests/test_trial_events.py`
- Modify: `application/playground/backend/tests/test_harbor_jobs_api.py`

**Interfaces:**
- Produces: `JOB_EVENTS_FILENAME`, `append_job_event`, `read_job_events_after`, `stream_job_events`, and `GET /api/harbor/jobs/{job_name}/events?cursor=N`.

- [ ] **Step 1: Write failing journal/replay/SSE tests**

```python
def test_job_journal_multiplexes_trials_and_replays_by_byte_cursor(tmp_path):
    job = tmp_path / "job"
    TrialEventWriter.for_trial_dir(job / "a").append({"type": "phase", "phase": "running"})
    TrialEventWriter.for_trial_dir(job / "b").append({"type": "survey_answer", "questionId": "q1", "value": 4})
    first, cursor = read_job_events_after(job / JOB_EVENTS_FILENAME, 0)
    assert [item["trialName"] for item in first] == ["a", "b"]
    TrialEventWriter.for_trial_dir(job / "a").append({"type": "done"})
    replay, next_cursor = read_job_events_after(job / JOB_EVENTS_FILENAME, cursor)
    assert [item["event"]["type"] for item in replay] == ["done"]
    assert replay[0]["id"] == next_cursor > cursor

@pytest.mark.asyncio
async def test_sse_drains_terminal_job(tmp_path):
    job = tmp_path / "job"
    append_job_event(job, trial_name="a", event={"type": "done"})
    async def _always_false():
        return False
    chunks = [chunk async for chunk in stream_job_events(job, after=0, is_disconnected=_always_false, is_terminal=lambda: True, poll_seconds=0)]
    body = "".join(chunks)
    assert "event: trial\n" in body and "id: " in body and '"trialName": "a"' in body
```

```python
def test_job_sse_route_returns_resumable_event_stream(client, fake_harbor_jobs, tmp_path):
    job_dir = tmp_path / "demo-job"
    append_job_event(job_dir, trial_name="trial-0", event={"type": "done"})
    fake_harbor_jobs.job_events_path = lambda job_name: job_dir / JOB_EVENTS_FILENAME
    fake_harbor_jobs.is_job_terminal = lambda job_name: True
    response = client.get("/api/harbor/jobs/demo-job/events?cursor=0")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert '"trialName": "trial-0"' in response.text
```

- [ ] **Step 2: Run and verify RED**

```bash
PYTHONPATH=packages/playground/src:application/playground uv run pytest application/playground/backend/tests/test_trial_events.py application/playground/backend/tests/test_harbor_jobs_api.py -q
```

- [ ] **Step 3: Implement byte-safe locked journal**

```python
JOB_EVENTS_FILENAME = "live-events.jsonl"

def append_job_event(job_dir: Path, *, trial_name: str | None, event: dict[str, Any]) -> None:
    path = job_dir / JOB_EVENTS_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as handle:
        import fcntl
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            handle.write(json.dumps({"trialName": trial_name, "event": event}, ensure_ascii=False) + "\n")
            handle.flush()
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
```

`TrialEventWriter` appends to its old trial file, then the job journal. Read the journal in binary; decorate every complete line with `id` equal to its ending byte offset and `jobName` equal to `journal_path.parent.name`. Harbor launch queued/running/completed/failed transitions append `trialName=null`, `type=job_state`. Expose validated `job_events_path` and `is_job_terminal`.

- [ ] **Step 4: Implement disconnect-aware SSE route**

```python
@app.get("/api/harbor/jobs/{job_name}/events", tags=["harbor-jobs"])
async def stream_harbor_job_events(job_name: str, request: Request, cursor: int = Query(0, ge=0), services: AppState = Depends(get_services)) -> StreamingResponse:
    header = request.headers.get("last-event-id", "").strip()
    after = int(header) if header.isdigit() else cursor
    job_dir = services.harbor_jobs.job_events_path(job_name).parent
    return StreamingResponse(
        stream_job_events(job_dir, after=after, is_disconnected=request.is_disconnected, is_terminal=lambda: services.harbor_jobs.is_job_terminal(job_name)),
        media_type="text/event-stream", headers={"Cache-Control": "no-cache"},
    )
```

Replace the uncommitted per-trial stream. Emit heartbeat comments after 15 idle seconds, drain once after terminal state, close on disconnect, and log/yield `stream_error` for serialization/read failure.

```python
async def stream_job_events(job_dir, *, after, is_disconnected, is_terminal, poll_seconds=0.1):
    cursor, idle_since = after, time.monotonic()
    while not await is_disconnected():
        envelopes, cursor = read_job_events_after(job_dir / JOB_EVENTS_FILENAME, cursor)
        for envelope in envelopes:
            name = "job" if envelope["trialName"] is None else "trial"
            yield f"id: {envelope['id']}\nevent: {name}\ndata: {json.dumps(envelope)}\n\n"
            idle_since = time.monotonic()
        if is_terminal():
            remaining, cursor = read_job_events_after(job_dir / JOB_EVENTS_FILENAME, cursor)
            for envelope in remaining:
                name = "job" if envelope["trialName"] is None else "trial"
                yield f"id: {envelope['id']}\nevent: {name}\ndata: {json.dumps(envelope)}\n\n"
            return
        if time.monotonic() - idle_since >= 15:
            yield ": heartbeat\n\n"
            idle_since = time.monotonic()
        await asyncio.sleep(poll_seconds)
```

- [ ] **Step 5: Run Step 2 and verify GREEN**

- [ ] **Step 6: Commit**

```bash
git add packages/playground/src/playground/harbor/trial_events.py application/playground/backend/api/sse_stream.py application/playground/backend/api/app.py application/playground/backend/service/harbor_job_service.py application/playground/backend/tests/test_trial_events.py application/playground/backend/tests/test_harbor_jobs_api.py
git commit -m "feat: stream resumable job events over SSE"
```

---

### Task 6: Add typed EventSource client and multi-trial reducer

**Files:**
- Modify: `application/playground/frontend/src/lib/types.ts`
- Create: `application/playground/frontend/src/lib/harborJobEventStream.ts`
- Create: `application/playground/frontend/src/lib/__tests__/harborJobEventStream.test.ts`
- Modify: `application/playground/frontend/src/lib/harborCockpitMappers.ts`
- Create: `application/playground/frontend/src/lib/__tests__/harborCockpitEvents.test.ts`
- Modify: `application/playground/frontend/src/lib/api.ts`

**Interfaces:**
- Produces: `HarborJobEventEnvelope`, `connectHarborJobEvents(options) -> cleanup`, and `applyHarborJobEnvelope(state, envelope)`.

- [ ] **Step 1: Write failing parser, cleanup, and dedupe tests**

```typescript
it("parses envelopes and closes cleanly", () => {
  const received: HarborJobEventEnvelope[] = [];
  const close = connectHarborJobEvents({ jobName: "job 1", cursor: 7, onEnvelope: (e) => received.push(e), onError: vi.fn() });
  const source = FakeEventSource.instances[0];
  source.emit("trial", { lastEventId: "19", data: JSON.stringify({ id: 19, jobName: "job 1", trialName: "a", event: { type: "phase", phase: "running" } }) });
  expect(received[0].id).toBe(19);
  close();
  expect(source.closed).toBe(true);
});

it("deduplicates replay and retains all trials", () => {
  let state = EMPTY_JOB_STREAM_STATE;
  const a = { id: 10, jobName: "job", trialName: "a", event: { type: "user_message", turnIndex: 1, message: "hello" } };
  state = applyHarborJobEnvelope(state, a);
  state = applyHarborJobEnvelope(state, a);
  state = applyHarborJobEnvelope(state, { id: 20, jobName: "job", trialName: "b", event: { type: "survey_answer", questionId: "q1", value: 4, total: 2 } });
  expect(state.seenEventIds.size).toBe(2);
  expect(Object.keys(state.liveByTrial)).toEqual(["a", "b"]);
});
```

- [ ] **Step 2: Run and verify RED**

```bash
cd application/playground/frontend && npm test -- --run src/lib/__tests__/harborJobEventStream.test.ts src/lib/__tests__/harborCockpitEvents.test.ts
```

- [ ] **Step 3: Implement client and reducer**

```typescript
export interface HarborJobEventEnvelope {
  id: number;
  jobName: string;
  trialName: string | null;
  event: HarborTrialEvent | { type: "job_state"; status: string; error?: string | null };
}

export function connectHarborJobEvents(options: ConnectOptions): () => void {
  const source = new EventSource(`/api/harbor/jobs/${encodeURIComponent(options.jobName)}/events?cursor=${options.cursor ?? 0}`);
  const receive = (raw: MessageEvent<string>) => {
    const envelope = JSON.parse(raw.data) as HarborJobEventEnvelope;
    if (!Number.isInteger(envelope.id) || envelope.jobName !== options.jobName || !envelope.event?.type) return options.onError(new Error("Malformed Harbor job event"));
    options.onEnvelope(envelope);
  };
  source.addEventListener("trial", receive as EventListener);
  source.addEventListener("job", receive as EventListener);
  source.addEventListener("stream_error", (raw) => options.onError(new Error((raw as MessageEvent<string>).data)));
  source.onerror = () => options.onError(new Error("Harbor job event stream disconnected"));
  return () => source.close();
}
```

`HarborJobStreamState` contains `liveByTrial`, `trialOrder`, `seenEventIds`, `cursor`, `launchStatus`, and `terminalError`. Duplicate ID returns unchanged state. Trial envelope calls existing `applyHarborTrialEvents`; job state updates launch only. Map `survey_question_started` and use event `total`, never hard-coded 45. Remove untyped fetch-reader `streamHarborTrialEvents`.

- [ ] **Step 4: Run Step 2 and verify GREEN**

- [ ] **Step 5: Commit**

```bash
git add application/playground/frontend/src/lib/types.ts application/playground/frontend/src/lib/harborJobEventStream.ts application/playground/frontend/src/lib/__tests__/harborJobEventStream.test.ts application/playground/frontend/src/lib/harborCockpitMappers.ts application/playground/frontend/src/lib/__tests__/harborCockpitEvents.test.ts application/playground/frontend/src/lib/api.ts
git commit -m "feat: add typed idempotent Harbor event stream"
```

---

### Task 7: Drive single and batch cockpits without polling or flicker

**Files:**
- Modify: `application/playground/frontend/src/lib/useHarborCockpitRun.ts`
- Modify: `application/playground/frontend/src/lib/useHarborBatchLive.ts`
- Modify: `application/playground/frontend/src/components/cockpit/SurveyEvalCockpit.tsx`
- Modify: `application/playground/frontend/src/components/cockpit/Trajectory.tsx`
- Modify: `application/playground/frontend/src/components/cockpit/setup/useCockpitBatchJob.ts`
- Modify: `application/playground/frontend/src/components/TrialDebriefRails.tsx`
- Create: `application/playground/frontend/src/lib/__tests__/useHarborLiveStreams.test.tsx`
- Create: `application/playground/frontend/src/components/cockpit/__tests__/SurveyLive.test.tsx`
- Create: `application/playground/frontend/src/components/__tests__/TrialDebriefRails.test.tsx`

**Interfaces:**
- Consumes: Task 6 stream/reducer and final debrief.
- Produces: one subscription per job, stable `liveByTrial`, pending survey card, and monotonic terminal merge.

- [ ] **Step 1: Write failing hook and UI tests**

```tsx
it("batch subscribes once and updates unselected trials without polling", async () => {
  vi.useFakeTimers();
  vi.spyOn(api, "getHarborJobLive").mockResolvedValue({ jobName: "job", launchStatus: "running", trialCount: 2, completedTrials: 0, trials: [] });
  const stream = installStreamHarness();
  const { result } = renderHook(() => useHarborBatchLive("job"));
  await waitFor(() => expect(stream.connections).toHaveLength(1));
  act(() => stream.emit({ id: 1, jobName: "job", trialName: "a", event: { type: "phase", phase: "persona_thinking" } }));
  act(() => stream.emit({ id: 2, jobName: "job", trialName: "b", event: { type: "survey_answer", questionId: "q1", value: 4, total: 2 } }));
  expect(result.current.liveByTrial.a.phase).toBe("persona_thinking");
  expect(result.current.liveByTrial.b.surveyResult?.answers).toHaveLength(1);
  await vi.advanceTimersByTimeAsync(5000);
  expect(api.getHarborJobLive).toHaveBeenCalledTimes(1);
});
```

```tsx
it("single run keeps partial content while terminal debrief merges", async () => {
  const stream = installStreamHarness();
  vi.spyOn(api, "launchHarborJob").mockResolvedValue({ jobName: "job" });
  vi.spyOn(api, "getHarborJob").mockResolvedValue(completedSurveyJobDetail);
  vi.spyOn(api, "getHarborTrialDebrief").mockResolvedValue(twoAnswerDebrief);
  const { result } = renderHook(() => useHarborCockpitRun<SurveyEvalJobView>({ taskKind: "survey" }));
  act(() => void result.current.run(singleSurveyInput));
  act(() => stream.emit(oneAnswerEnvelope));
  expect(result.current.job?.surveyResult?.answers).toHaveLength(1);
  act(() => stream.emit(doneJobEnvelope));
  await waitFor(() => expect(result.current.phase).toBe("done"));
  expect(result.current.job?.surveyResult?.answers).toHaveLength(2);
});

it("survey pending card becomes answered without remounting earlier answer", () => {
  const { rerender } = render(<SurveyLive instrument={twoQuestionInstrument} result={oneAnswerRunningResult} phase="running" error={null} onRetry={vi.fn()} />);
  const first = screen.getByText("answer one").closest("div");
  expect(screen.getByText("question two")).toBeInTheDocument();
  rerender(<SurveyLive instrument={twoQuestionInstrument} result={twoAnswerDoneResult} phase="done" error={null} onRetry={vi.fn()} />);
  expect(screen.getByText("answer two")).toBeInTheDocument();
  expect(screen.getByText("answer one").closest("div")).toBe(first);
});

it("persona rail prefers the complete stored prompt", async () => {
  render(<TrialDebriefRails prompts={{ personaPrompt: "Canonical field one\nCanonical field fifty" }} persona={{ id: "p", name: "Pat", dimensions: { focus_only: "fallback" } }} />);
  await userEvent.click(screen.getByRole("button", { name: /persona profile/i }));
  expect(screen.getByText(/Canonical field fifty/)).toBeInTheDocument();
  expect(screen.queryByText(/Focus Only/)).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run and verify RED**

```bash
cd application/playground/frontend && npm test -- --run src/lib/__tests__/useHarborLiveStreams.test.tsx src/components/cockpit/__tests__/SurveyLive.test.tsx src/components/__tests__/TrialDebriefRails.test.tsx
```

- [ ] **Step 3: Replace polling with one job stream**

Each hook fetches one bootstrap snapshot, subscribes once keyed by job, applies functional reducer updates for every trial, fetches terminal detail/debrief once, and closes on cleanup/reset/cancel. Remove `setInterval`, `POLL_MS`, offsets, selected-trial connection, `streamStartedRef`, and the invalid hook inside `jobDetailToLive`. Keep per-trial GET only as explicit degraded fallback after SSE error.

```typescript
const cursorRef = useRef(0);
useEffect(() => {
  if (!jobName || !enabled) return;
  return connectHarborJobEvents({
    jobName,
    cursor: cursorRef.current,
    onEnvelope: (envelope) => {
      cursorRef.current = envelope.id;
      setStreamState((current) => applyHarborJobEnvelope(current, envelope));
    },
    onError: (cause) => setError(cause.message),
  });
}, [jobName, enabled]);

const selectedLive = selectedTrial ? streamState.liveByTrial[selectedTrial] ?? null : null;
```

Final debrief merges through `mergeHarborCockpitJob` into current live state; never `setJob(null)` during terminal reconciliation. Batch selection reads existing `liveByTrial` and never drops other persona state.

- [ ] **Step 4: Render active question and honest trajectory counts**

Extend live survey state with `activeQuestionId`, `activeQuestionIndex`, `activeQuestionTotal`. Export the existing production `SurveyLive` component so its observable rendering can be tested. Render the authored active prompt as pending after completed answer cards, keyed by question ID. Group ask/answer trajectory by `questionId`; render start/end in a separate lifecycle block and derive question count from the instrument/answers, not event count. Persona rail continues to prefer `prompts.personaPrompt` over context/dimensions.

- [ ] **Step 5: Run Step 2 and verify GREEN**

- [ ] **Step 6: Run full frontend verification**

```bash
cd application/playground/frontend && npm test -- --run && npm run typecheck && npm run build
```

- [ ] **Step 7: Commit**

```bash
git add application/playground/frontend/src/lib/useHarborCockpitRun.ts application/playground/frontend/src/lib/useHarborBatchLive.ts application/playground/frontend/src/components/cockpit/SurveyEvalCockpit.tsx application/playground/frontend/src/components/cockpit/Trajectory.tsx application/playground/frontend/src/components/cockpit/setup/useCockpitBatchJob.ts application/playground/frontend/src/components/TrialDebriefRails.tsx application/playground/frontend/src/lib/__tests__/useHarborLiveStreams.test.tsx application/playground/frontend/src/components/cockpit/__tests__/SurveyLive.test.tsx application/playground/frontend/src/components/__tests__/TrialDebriefRails.test.tsx
git commit -m "feat: render stable realtime survey and chat runs"
```

---

### Task 8: Full regression and live acceptance verification

**Files:**
- Modify only the files named above if a scoped regression is found.
- Never add generated jobs, logs, `.env` files, model dumps, or helper scripts.

**Interfaces:**
- Produces: fresh automated evidence and inspected survey/chat/two-persona live runs.

- [ ] **Step 1: Run complete owned Python suites**

```bash
PYTHONPATH=packages/playground/src:application/playground uv run pytest application/playground/backend/tests packages/playground/src/playground/tests tests/unit -q
```

Expected: zero failures. If an external-service-only test is blocked, record the exact command/output and rerun every focused suite from Tasks 1–5; do not claim the blocked suite passed.

- [ ] **Step 2: Run complete frontend and hygiene verification**

```bash
cd application/playground/frontend && npm test -- --run && npm run typecheck && npm run build
cd ../../.. && git diff --check && git status --short
```

Expected: zero failures/errors and no whitespace errors; status contains only intentional work plus pre-existing user files.

- [ ] **Step 3: Inspect one real survey**

Start `application/playground/run_demo.sh`, launch `survey_annual-checkup-habits` for one persona, then inspect every discovered journal directly:

```bash
find application/playground -name live-events.jsonl -exec rg -n 'survey_question_started|survey_answer|job_state' {} +
```

Use the job name printed by the launch response to identify its output lines. Verify every question starts before its real validated answer, and the center card appears on the same event.

- [ ] **Step 4: Inspect one real meal-planning chatbot**

Launch `chat_meal-planning-nutrition` with maximum 8. Inspect its exact `transcript.json` and `user_feedback.json` paths reported by the job detail API. Verify at least 5 context-dependent exchanges, no accepted repeated temporary error, and non-constant model feedback.

- [ ] **Step 5: Inspect one two-persona batch**

Launch a survey or chat batch with two personas and concurrency 2. Browser Network must show one job-level request whose URL ends in `/events`. Both cells advance before completion; selecting either retains its detail; reconnect creates no duplicates; terminal merge does not flash empty.

- [ ] **Step 6: Repeat Steps 1–2 after the last live-test edit**

Read full output before claiming completion.

- [ ] **Step 7: Commit scoped verification fixes only when present**

```bash
git commit -m "fix: close playground realtime fidelity regressions"
```

Do not create an empty commit when no source fix was required.
