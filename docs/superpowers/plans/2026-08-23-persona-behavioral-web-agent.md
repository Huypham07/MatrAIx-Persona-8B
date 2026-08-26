# Persona-Behavioral Web Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make persona information lossless across Survey, Chatbot, and Web, then add a local-Qwen Playwright agent whose choices, persistence, and input behavior visibly and measurably reflect the selected persona in realtime.

**Architecture:** Preserve the canonical persona profile at the boundary, compile explicit persona dimensions into an auditable behavior policy, and feed that policy into an observe-plan-act web loop. Keep cognition, hard loop governance, and motor execution separate so each layer can be deterministic and independently tested. Stream public action/checkpoint events through the existing Harbor NDJSON path and enrich the current web trace UI without exposing hidden chain-of-thought.

**Tech Stack:** Python 3.12, Pydantic, Playwright, local Qwen/OpenAI-compatible client, pytest, React, TypeScript, Vitest, Testing Library, Harbor NDJSON event stream.

**Spec:** `docs/superpowers/specs/2026-08-23-persona-behavioral-web-agent-design.md`

## Global Constraints

- Preserve the user's untracked `.codegraph/`, `paper_tex/`, `persona_8b_dataset_deep_dive.md`, and `qwen3-14b.txt` files.
- Do not add stealth, CAPTCHA bypass, fingerprint spoofing, download execution, or anti-bot evasion.
- Derive behavior only from explicit persona dimensions; never infer motor skill, patience, safety, or competence from demographic attributes.
- Keep typo probability at zero unless the persona explicitly supplies an input-error tendency.
- Never publish hidden model reasoning. Events may expose a short public goal, selected action, target, policy evidence, and result.
- Research mode uses fixed model sampling and a recorded seed. Expressive demo mode may apply bounded persona-driven sampling and must record the effective values.
- Existing `persona-browser-use` remains available. The new in-process Playwright backend is the default for local-Qwen web trials.
- Every task below follows red-green-refactor: write the failing test, run it and observe the intended failure, implement the minimum behavior, rerun focused tests, then commit.

---

## Task 1: Make Persona Transport Lossless and Strict

**Files:**

- Modify: `packages/playground/src/playground/types.py`
- Modify: `packages/playground/src/playground/user_sim/prompt.py`
- Test: `packages/playground/src/playground/tests/test_persona.py`
- Test: `application/playground/backend/tests/test_inprocess_survey_prompt.py`

- [ ] Add tests proving `Persona.from_dict()` preserves dimensions after index 35, nested values, schema version, and source path.

```python
def test_persona_from_dict_preserves_all_dimensions() -> None:
    raw = {
        "name": "Mai",
        "schema_version": "persona.v1",
        "dimensions": {f"dimension_{i}": {"value": i} for i in range(50)},
    }
    persona = Persona.from_dict(raw, persona_path="personas/mai.yaml")
    assert len(persona.dimensions) == 50
    assert persona.dimensions["dimension_49"] == {"value": 49}
    assert persona.schema_version == "persona.v1"
    assert persona.persona_path == "personas/mai.yaml"
```

- [ ] Add a rendering test proving a late behavioral dimension appears in the canonical persona block and that rendering fails clearly when a required persona source cannot be resolved.
- [ ] Run `PYTHONPATH=packages/playground/src:application/playground uv run pytest packages/playground/src/playground/tests/test_persona.py application/playground/backend/tests/test_inprocess_survey_prompt.py -q` and confirm failures identify the 35-dimension truncation and empty source path.
- [ ] Replace the lossy `active_dims[:35]` projection with a lossless `dimensions: dict[str, Any]`, `schema_version`, and `persona_path` envelope while keeping compatibility accessors needed by existing callers.
- [ ] Route prompt rendering through the canonical persona renderer in `environment/agents/matraix/agents/persona/templating.py`; reject an empty or missing persona path rather than silently emitting a reduced persona.
- [ ] Rerun the focused tests and confirm all pass.
- [ ] Commit: `git commit -am "fix: preserve complete persona profiles"`

## Task 2: Restore Survey and Chatbot Evaluation Fidelity

**Files:**

- Modify: `packages/playground/src/playground/inprocess/survey_eval.py`
- Modify: `packages/playground/src/playground/inprocess/chatbot_eval.py`
- Modify: `application/playground/backend/service/harbor_job_service.py`
- Create: `application/playground/backend/service/inprocess_trial_worker.py`
- Modify: `application/playground/backend/tests/test_inprocess_survey_prompt.py`
- Create: `application/playground/backend/tests/test_inprocess_trial_worker.py`

- [ ] Extend survey prompt tests to require full task instruction, context, questionnaire semantics, rationale flags, and the requested answer envelope in every chunk.
- [ ] Add worker tests asserting Survey forwards task context and Chatbot calls the existing `run_playground` UserSim loop with the real task path, persona YAML path, repository root, event callback, and configured turn budget.
- [ ] Add negative assertions that Chatbot does not synthesize a fixed two-message transcript, fixed satisfaction result, or hard-coded success.
- [ ] Run `PYTHONPATH=packages/playground/src:application/playground uv run pytest application/playground/backend/tests/test_inprocess_survey_prompt.py application/playground/backend/tests/test_inprocess_trial_worker.py -q` and confirm the current shortcuts fail the tests.
- [ ] Extract `_inprocess_trial_worker` dispatch into `run_inprocess_trial(manifest_path: Path, env: Mapping[str, str], *, repo_root: Path) -> int`; leave `HarborJobService` responsible only for process orchestration.
- [ ] Restore Survey prompt construction from the task content bundle, including context and rationale/output requirements for chunked questionnaires.
- [ ] Make Chatbot invoke `playground.user_sim.runner.run_playground` and persist its actual turns, decisions, self-report, and termination reason.
- [ ] Ensure non-success terminal decisions remain distinguishable from technical failures and are not rewritten as successful satisfaction.
- [ ] Rerun the focused tests and confirm all pass.
- [ ] Commit: `git add packages/playground/src/playground/inprocess application/playground/backend/service application/playground/backend/tests && git commit -m "fix: restore survey and chatbot fidelity"`

## Task 3: Compile Persona Dimensions into an Auditable Behavior Policy

**Files:**

- Create: `packages/playground/src/playground/persona_behavior_policy.py`
- Create: `tests/unit/test_persona_behavior_policy.py`

- [ ] Write table-driven tests for two explicit profiles: a meticulous source-checker and an impatient visual shopper. Assert different source preferences, option breadth, acceptance thresholds, step budgets, dwell/scroll styles, and evidence paths.
- [ ] Test that demographic-only inputs produce neutral defaults and that research mode does not change model temperature/top-p.
- [ ] Test deterministic compilation for the same seed and bounded sampling in expressive demo mode.
- [ ] Run `PYTHONPATH=packages/playground/src:application/playground uv run pytest tests/unit/test_persona_behavior_policy.py -q` and confirm the module is missing.
- [ ] Implement immutable `CognitivePolicy`, `GovernorPolicy`, `MotorPolicy`, `SamplingPolicy`, and `PersonaBehaviorPolicy` dataclasses.
- [ ] Implement `compile_persona_behavior_policy(dimensions, *, seed: int, mode: Literal["research", "expressive_demo"] = "research")` using an explicit dimension-to-policy mapping. Store each non-default decision as `PolicyEvidence(dimension_path, observed_value, policy_field, applied_value)`.
- [ ] Clamp all numeric outputs to documented safe ranges, use neutral defaults for absent dimensions, and reject unsupported modes.
- [ ] Rerun focused tests and confirm all pass.
- [ ] Commit: `git add packages/playground/src/playground/persona_behavior_policy.py tests/unit/test_persona_behavior_policy.py && git commit -m "feat: compile persona behavior policies"`

## Task 4: Load the Real Web Task Contract and Validate Actions

**Files:**

- Create: `packages/playground/src/playground/inprocess/web_task_contract.py`
- Create: `packages/playground/src/playground/inprocess/web_actions.py`
- Create: `tests/unit/test_web_task_contract.py`
- Create: `tests/unit/test_web_actions.py`

- [ ] Add contract tests using temporary `task.toml` fixtures with instruction, context, start URL, output artifact, and completion requirements. Assert no URL is guessed from task-name substrings.
- [ ] Add failure tests for absent task files, malformed URLs, missing output artifacts, and unsupported schemes.
- [ ] Add discriminated-union tests for `search`, `navigate`, `click`, `type`, `scroll`, `back`, `wait`, `select_option`, `extract_visible`, `done`, and `abandon` actions.
- [ ] Add parser tests that allow one schema-repair attempt and then return a typed planning failure without executing an action.
- [ ] Run `PYTHONPATH=packages/playground/src:application/playground uv run pytest tests/unit/test_web_task_contract.py tests/unit/test_web_actions.py -q` and confirm both modules are missing.
- [ ] Implement `WebTaskContract` and `load_web_task_contract(task_path: Path, *, repo_root: Path)` by reading the existing task content bundle plus `task.toml` metadata.
- [ ] Implement Pydantic action models with a discriminating `kind`, public `goal`, target fields, and action-specific validation. Keep model output schema separate from Playwright execution.
- [ ] Implement `parse_web_action(raw: str, repair: Callable[[str, str], str]) -> WebAction` with exactly one repair call and a typed `WebActionParseError` after the second invalid payload.
- [ ] Rerun focused tests and confirm all pass.
- [ ] Commit: `git add packages/playground/src/playground/inprocess/web_task_contract.py packages/playground/src/playground/inprocess/web_actions.py tests/unit/test_web_task_contract.py tests/unit/test_web_actions.py && git commit -m "feat: define web task and action contracts"`

## Task 5: Enforce Persona-Specific Progress and Termination

**Files:**

- Create: `packages/playground/src/playground/inprocess/web_governor.py`
- Create: `tests/unit/test_web_governor.py`

- [ ] Write state-machine tests for `running`, `completed`, `abandoned`, `budget_exhausted`, and `technical_failure`.
- [ ] Test hard step/time/source/option budgets, repeated-action detection, stagnation thresholds, explicit give-up permission, and task completion requirements.
- [ ] Test that `done` cannot claim completion without contract evidence and that a normal persona abandonment is not converted into a technical failure.
- [ ] Run `PYTHONPATH=packages/playground/src:application/playground uv run pytest tests/unit/test_web_governor.py -q` and confirm the module is missing.
- [ ] Implement `GovernorSnapshot`, `ProgressSignal`, `Termination`, and `WebGovernor`. Expose `before_action(action)`, `after_action(action, observation, result)`, and `terminate(reason, status)` methods.
- [ ] Include remaining steps, elapsed budget, distinct sources/options, repeated action count, stagnation count, and the final reason in every snapshot.
- [ ] Rerun focused tests and confirm all pass.
- [ ] Commit: `git add packages/playground/src/playground/inprocess/web_governor.py tests/unit/test_web_governor.py && git commit -m "feat: add persona-aware web governor"`

## Task 6: Execute Seeded Human-Like Input Without Anti-Bot Features

**Files:**

- Create: `packages/playground/src/playground/inprocess/web_motor.py`
- Create: `tests/unit/test_web_motor.py`

- [ ] Define a fake page/input adapter in tests and assert seeded cursor paths, typing delays, scroll increments, dwell timing, and optional correction events are reproducible.
- [ ] Test that precise personas use lower cursor variance and reading personas use smaller scroll increments/longer dwell than skimming personas.
- [ ] Test that typo simulation is disabled by default, corrections never alter the final intended text, and navigation/download/CAPTCHA boundaries remain enforced.
- [ ] Run `PYTHONPATH=packages/playground/src:application/playground uv run pytest tests/unit/test_web_motor.py -q` and confirm the module is missing.
- [ ] Implement a small `BrowserInputPort` protocol and a `PersonaMotorController` that generates seeded eased/Bezier-like point sequences, per-character delays, bounded jitter, persona-driven scroll chunks, and dwell delays.
- [ ] Use Playwright's supported mouse, keyboard, locator, and wheel APIs only. Do not modify `navigator.webdriver`, browser fingerprints, CAPTCHA state, or site security controls.
- [ ] Emit structured motor telemetry with durations and correction counts so the UI and behavior summary can show the difference without replaying private reasoning.
- [ ] Rerun focused tests and confirm all pass.
- [ ] Commit: `git add packages/playground/src/playground/inprocess/web_motor.py tests/unit/test_web_motor.py && git commit -m "feat: add seeded persona motor controls"`

## Task 7: Build the Observe-Plan-Act Web Agent and Atomic Checkpoints

**Files:**

- Create: `packages/playground/src/playground/inprocess/web_agent.py`
- Create: `packages/playground/src/playground/inprocess/web_trace_checkpoint.py`
- Modify: `packages/playground/src/playground/inprocess/web_eval.py`
- Replace: `tests/unit/test_web_eval_qwen.py`
- Create: `tests/unit/test_web_trace_checkpoint.py`

- [ ] Replace the live-network unit test with injected fake browser and planner ports. Cover observation, policy-aware prompt construction, action validation/repair, execution, governor updates, and all terminal states.
- [ ] Assert planner prompts contain the full canonical persona block, task contract, compiled policy/evidence, current visible observation, public action history, and governor snapshot, but do not request or persist chain-of-thought.
- [ ] Add checkpoint tests proving screenshot files are written before an atomic trajectory replacement and event emission.
- [ ] Assert event order for each step: `web_observation`, `web_plan_ready`, `web_action_started`, `web_action_completed`, `web_governor_update`, `web_step_checkpoint`, followed once by `web_termination`.
- [ ] Run `PYTHONPATH=packages/playground/src:application/playground uv run pytest tests/unit/test_web_eval_qwen.py tests/unit/test_web_trace_checkpoint.py -q` and confirm failures reflect the current one-shot scan.
- [ ] Implement injectable `PlannerPort`, `BrowserSessionPort`, and `EventSink` protocols plus `PersonaWebAgent.run(contract, persona, policy)`.
- [ ] Build compact visible observations from URL, title, viewport text, interactable elements, and prior result; cap by structured fields rather than truncating the entire page body at 3,500 characters.
- [ ] Delegate physical action execution to `PersonaMotorController`, progress decisions to `WebGovernor`, and JSON validation to `web_actions.py`.
- [ ] Implement `WebTraceCheckpointWriter` using same-directory temporary files and `Path.replace()` for trajectory updates. Persist the screenshot, action/result, policy evidence, governor snapshot, and timestamps at every completed step.
- [ ] Refactor `run_qwen_web_eval` into a coordinator that loads inputs, constructs dependencies, invokes the loop, and returns a typed run result.
- [ ] Rerun focused tests and confirm all pass.
- [ ] Commit: `git add packages/playground/src/playground/inprocess/web_agent.py packages/playground/src/playground/inprocess/web_trace_checkpoint.py packages/playground/src/playground/inprocess/web_eval.py tests/unit/test_web_eval_qwen.py tests/unit/test_web_trace_checkpoint.py && git commit -m "feat: run persona-aware web agent loop"`

## Task 8: Integrate Truthful Harbor Artifacts and Behavior Summaries

**Files:**

- Modify: `application/playground/backend/service/inprocess_trial_worker.py`
- Modify: `application/playground/backend/service/web_tasks.py`
- Modify: `application/playground/backend/service/web_eval_service.py`
- Modify: `application/playground/backend/service/harbor_web_trace.py`
- Modify: `application/playground/backend/tests/test_inprocess_trial_worker.py`
- Modify: `application/playground/backend/tests/test_harbor_job_service.py`
- Modify: `application/playground/backend/tests/test_harbor_web_eval.py`
- Modify: `application/playground/backend/tests/test_harbor_web_trace.py`
- Modify: `application/playground/backend/tests/test_web_tasks.py`

- [ ] Add backend tests that select `local-qwen-playwright` by default for in-process Qwen web runs and retain `persona-browser-use` when explicitly selected.
- [ ] Test that the worker uses the task's actual URL and single declared output artifact, propagates the persona seed/mode, and never writes unrelated guessed artifact names.
- [ ] Test truthful mappings for completed, abandoned, budget exhausted, and technical failure, including verifier results and process exit codes.
- [ ] Test a `behavior_summary.json` containing queries, visited domains, considered options, action counts, scroll distance/style, dwell time, steps, recoverable failures, termination, outcome, effective sampling, seed, and policy evidence.
- [ ] Test Harbor trace parsing for all new web events while retaining compatibility with older trajectory records.
- [ ] Run `PYTHONPATH=packages/playground/src:application/playground uv run pytest application/playground/backend/tests/test_inprocess_trial_worker.py application/playground/backend/tests/test_harbor_job_service.py application/playground/backend/tests/test_harbor_web_eval.py application/playground/backend/tests/test_harbor_web_trace.py application/playground/backend/tests/test_web_tasks.py -q` and confirm the current hard-coded success/artifact behavior fails.
- [ ] Wire the web task registry to `WebTaskContract`, invoke `PersonaWebAgent`, and store the declared artifact, trajectory, screenshots, event stream, and behavior summary.
- [ ] Make Harbor status and reward reflect the typed termination plus verifier outcome; include the exact stop reason in public metadata.
- [ ] Extend trace normalization with typed fields for phase, public goal, action, target, result, persona evidence, governor values, screenshot, and termination.
- [ ] Rerun focused tests and confirm all pass.
- [ ] Commit: `git add application/playground/backend/service application/playground/backend/tests && git commit -m "feat: integrate web agent artifacts and events"`

## Task 9: Show Realtime Persona Behavior in the Existing Web Cockpit

**Files:**

- Modify: `application/playground/frontend/src/lib/types.ts`
- Modify: `application/playground/frontend/src/lib/harborCockpitMappers.ts`
- Modify: `application/playground/frontend/src/components/cockpit/WebEvalCockpit.tsx`
- Modify: `application/playground/frontend/src/components/cockpit/HarborTraceReplay.tsx`
- Create: `application/playground/frontend/src/components/cockpit/BehaviorSummaryPanel.tsx`
- Create: `application/playground/frontend/src/lib/__tests__/harborCockpitWebEvents.test.ts`
- Create: `application/playground/frontend/src/components/cockpit/__tests__/HarborTraceReplay.test.tsx`
- Create: `application/playground/frontend/src/components/cockpit/__tests__/BehaviorSummaryPanel.test.tsx`
- Modify: `application/playground/frontend/src/i18n/messages/en-US.json`
- Modify: `application/playground/frontend/src/i18n/messages/es.json`
- Modify: `application/playground/frontend/src/i18n/messages/ja.json`
- Modify: `application/playground/frontend/src/i18n/messages/ko.json`
- Modify: `application/playground/frontend/src/i18n/messages/pt-BR.json`
- Modify: `application/playground/frontend/src/i18n/messages/zh-Hans.json`
- Modify: `application/playground/frontend/src/i18n/messages/zh-Hant.json`

- [ ] Add mapper tests for incremental web events, backward-compatible records, duplicate polling responses, terminal events, and an event arriving while the user has manually selected an older step.
- [ ] Add component tests showing live phase, screenshot, public goal, action/target/result, persona-policy evidence, remaining step/source/option budgets, stagnation, and termination.
- [ ] Test auto-follow behavior: follow the newest checkpoint by default, pause when the user scrubs backward, and resume only after the explicit “Follow live” control.
- [ ] Test `BehaviorSummaryPanel` comparison metrics without requiring two personas to choose different final answers.
- [ ] Run `npm --prefix application/playground/frontend exec -- vitest run src/lib/__tests__/harborCockpitWebEvents.test.ts src/components/cockpit/__tests__/HarborTraceReplay.test.tsx src/components/cockpit/__tests__/BehaviorSummaryPanel.test.tsx` and confirm the new fields/components are absent.
- [ ] Extend `WebTraceEvent` and the Harbor mappers with typed web lifecycle payloads. Deduplicate using the event identifier/step plus event type so the existing 800–1,000 ms polling does not append duplicates.
- [ ] Update `HarborTraceReplay` to render the latest screenshot and a compact, public event timeline. Keep hidden reasoning out of types and DOM.
- [ ] Add `BehaviorSummaryPanel` for query/source/option/motor/governor/outcome metrics and mount it in `WebEvalCockpit` when summary data becomes available.
- [ ] Add all new labels to every locale pack and keep the locale pack key-set test green.
- [ ] Rerun the focused tests, then run `npm --prefix application/playground/frontend test` and `npm --prefix application/playground/frontend run build`.
- [ ] Commit: `git add application/playground/frontend && git commit -m "feat: stream persona web behavior in cockpit"`

## Task 10: Prove Two Personas Behave Differently on One Controlled Task

**Files:**

- Create: `tests/fixtures/persona_web_behavior_site/index.html`
- Create: `tests/fixtures/persona_web_behavior_site/data/options.json`
- Create: `tests/fixtures/personas/meticulous_source_checker.yaml`
- Create: `tests/fixtures/personas/impatient_visual_shopper.yaml`
- Create: `tests/integration/test_persona_web_behavior_contrast.py`
- Create: `docs/persona-web-agent.md`

- [ ] Build a local fixture site with a search page, two source-detail pages, visual product cards, a comparison view, and a deterministic completion target. It must require no external network and perform no downloads.
- [ ] Define two fixture personas using explicit behavioral dimensions only. Predeclare comparison metrics before execution: unique sources opened, options considered, scroll/dwell pattern, query specificity, and terminal reason/step count.
- [ ] Write an integration test that starts the fixture on an ephemeral localhost port, runs both personas with the same task and seed through injected deterministic planner responses, and records two complete trajectories.
- [ ] Assert at least three predeclared metrics differ in the expected direction, both traces remain valid, and the assertion does not require different final choices.
- [ ] Run `PYTHONPATH=packages/playground/src:application/playground uv run pytest tests/integration/test_persona_web_behavior_contrast.py -q` and confirm the fixture/test initially fails because the files are absent.
- [ ] Add the fixture, explicit personas, deterministic planner fixture, and comparison assertions. If Playwright is unavailable, fail with an installation message rather than silently skipping the acceptance test.
- [ ] Document backend selection, persona policy evidence, research versus demo mode, event schema, artifact locations, termination meanings, and the exact command to reproduce the two-persona comparison.
- [ ] Rerun the integration test twice and confirm each persona's metrics are reproducible for the fixed seed.
- [ ] Commit: `git add tests/fixtures tests/integration/test_persona_web_behavior_contrast.py docs/persona-web-agent.md && git commit -m "test: verify contrasting persona web behavior"`

## Task 11: Run Cross-Environment Regression and Final Verification

**Files:**

- Modify only files required to fix failures introduced by Tasks 1–10; do not broaden scope.

- [ ] Run Python unit and backend regression tests:

```bash
PYTHONPATH=packages/playground/src:application/playground uv run pytest \
  packages/playground/src/playground/tests \
  tests/unit \
  application/playground/backend/tests -q
```

- [ ] Run the controlled behavior acceptance test:

```bash
PYTHONPATH=packages/playground/src:application/playground uv run pytest \
  tests/integration/test_persona_web_behavior_contrast.py -q
```

- [ ] Run frontend tests and production build:

```bash
npm --prefix application/playground/frontend test
npm --prefix application/playground/frontend run build
```

- [ ] Run `git diff --check` and inspect `git status --short` to verify only intended files changed and the user's pre-existing untracked files remain untouched.
- [ ] Manually run the Playground once with each fixture persona against the local task; verify the live UI updates during execution, manual scrubbing pauses auto-follow, and the final summaries expose at least three expected behavioral differences.
- [ ] Inspect both trajectories and summaries to confirm no hidden reasoning, CAPTCHA/stealth mechanism, demographic inference, fake success, or undeclared artifact is present.
- [ ] Use the `superpowers:verification-before-completion` skill before making completion claims.
- [ ] Commit any verification-only fixes with a narrowly scoped message; leave no generated browser profiles, screenshots, or test-server artifacts in the repository.
