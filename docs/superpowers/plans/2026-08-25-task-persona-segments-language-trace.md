# Task Persona Segments, Language, Free Text, and Trace Export Implementation Plan

> **For Codex:** Execute this plan task-by-task with test-driven development. Work on
> `feat/local-qwen3-playground`; do not create a worktree and do not stage unrelated
> user changes.

**Goal:** Make four selected tasks launch task-specific pinned persona segments, answer
open survey questions through the LLM in the persona language, and export complete job
or persona trial traces.

**Architecture:** Extend `persona_strategy.json` with a backward-compatible
`pinnedSegments` mode. Carry segment/language metadata from task selection into trial
metadata and prompt construction. Record all model requests and returned outputs in a
normalized per-trial JSONL file, including the shared meal-plan sidecar via an explicit
trace envelope. Build allowlisted ZIPs from trial artifacts and expose download actions
in the existing job/run views.

**Tech stack:** Python 3.9+, FastAPI/Pydantic, pytest, React/TypeScript, TanStack Query,
Vitest, Vite.

---

## Task 1: Add and validate pinned persona segments

**Files:**

- Modify: `application/playground/backend/service/persona_strategy.py`
- Modify: `application/playground/backend/api/schemas.py`
- Modify: `application/playground/backend/service/persona_pool_service.py`
- Modify: `application/playground/frontend/src/lib/types.ts`
- Modify: `application/playground/frontend/src/components/cockpit/setup/personaSamplingTypes.ts`
- Test: `tests/environment/test_persona_strategy_gate.py`
- Test: `application/playground/backend/tests/test_persona_pool_service.py`
- Test: `application/playground/frontend/src/components/cockpit/setup/__tests__/personaSamplingTypes.test.ts`

1. Write failing tests for normalization of variable segment counts, preservation of
   labels/hypotheses/dimensions, flattening in stable order, exactly two IDs per segment,
   cross-segment uniqueness, and `sampling.mode=pinnedSegments`.
2. Run the targeted Python and Vitest tests and confirm the new cases fail.
3. Add `PersonaSegment` API/TypeScript models and extend sampling-mode types without
   changing existing modes.
4. Normalize and validate pinned segment fields. Resolve the declared pool safely and
   validate the raw YAML ID, language, region, and declared dimension membership.
5. Add a pool-service path that returns the pinned IDs/cards directly; it must not
   synthesize or randomly resample them.
6. Re-run the targeted tests until green.

## Task 2: Pin the four task cohorts and add narrative free text

**Files:**

- Modify: `application/tasks/chat_meal-planning-nutrition/persona_strategy.json`
- Modify: `application/tasks/survey_price-sensitivity-hasbro-gaming-candy-land/persona_strategy.json`
- Modify: `application/tasks/survey_annual-checkup-habits/persona_strategy.json`
- Modify: `application/tasks/example-survey_product-feedback/persona_strategy.json`
- Modify: each scoped survey's `input/questionnaire.yaml`
- Test: `tests/environment/test_application_tasks.py`
- Test: `tests/environment/test_application_task_contracts.py`
- Add: `tests/environment/test_scoped_task_persona_segments.py`

1. Write a failing contract test that loads exactly the four strategies, verifies their
   task-specific segment counts, two IDs per segment, primary-language/region coverage,
   and raw dimension matches.
2. Write a failing survey contract test requiring a narrative `free_text` item in all
   three scoped surveys (numeric-only text does not qualify).
3. Replace the four strategies with the approved pinned IDs and task-specific dimensions
   from the design spec.
4. Add `q_price_open_reason`, `q_checkup_open_reason`, and
   `q_product_open_influence` as required `free_text` questions.
5. Run the contract tests and correct any profile mismatch by choosing a matching real
   persona, never by weakening validation.

## Task 3: Enforce persona primary language in all persona-authored prompts

**Files:**

- Modify: `packages/playground/src/playground/user_sim/prompt.py`
- Modify: `packages/playground/src/playground/inprocess/survey_eval.py`
- Modify: `packages/playground/src/playground/user_sim/self_report.py`
- Modify: `packages/playground/src/playground/user_sim/tool_client.py`
- Test: `packages/playground/src/playground/tests/test_user_sim.py`
- Test: `packages/playground/src/playground/tests/test_survey_eval.py`
- Add: `packages/playground/src/playground/tests/test_persona_language_contract.py`

1. Write failing tests for Spanish/Mandarin/Swahili persona prompts, English canonical
   profile preservation, and exact JSON option IDs.
2. Add one shared `persona_language_contract()` helper reading
   `dimensions.primary_language`; append it after task text so it has final priority.
3. Use the helper in chat simulation, per-question survey completion, report/self-report,
   and tool-client prompt construction.
4. Include `expectedLanguage` in survey question/answer events and prompt bundles.
5. Run the new and existing prompt/survey suites.

## Task 4: Capture normalized LLM calls for survey, chat persona, and feedback

**Files:**

- Add: `packages/playground/src/playground/llm_trace.py`
- Modify: `packages/playground/src/playground/openai_client.py`
- Modify: `packages/playground/src/playground/model_client.py`
- Modify: `packages/playground/src/playground/user_sim/tool_client.py`
- Modify: `packages/playground/src/playground/inprocess/survey_eval.py`
- Modify: `packages/playground/src/playground/harbor/chat_eval.py`
- Modify: `packages/playground/src/playground/harbor/playground.py`
- Test: `packages/playground/src/playground/tests/test_openai_client.py`
- Add: `packages/playground/src/playground/tests/test_llm_trace.py`

1. Write failing tests for success, invalid JSON/retry, provider error, token usage,
   expected language, and authorization redaction.
2. Implement a context-managed `LlmTraceWriter` that appends one atomic JSON object per
   attempt to `<trial>/llm_calls.jsonl`; record timestamps, model, messages, raw output,
   parsed output, usage, finish reason, retry/error, and correlation metadata.
3. Add optional trace hooks to JSON and tool clients while keeping their public behavior
   compatible with tests and non-Harbor callers.
4. Initialize the writer from trial metadata in survey/chat/report execution and retain
   partial records when a call fails.
5. Add prompt/segment/language fields to realtime completion events.
6. Run targeted client, survey, chat, and feedback tests.

## Task 5: Capture meal-plan sidecar prompts and outputs

**Files:**

- Modify: `environment/task-environments/application/chatbot-api-sidecar_meal-plan-api/meal-plan-api/llm.py`
- Modify: `environment/task-environments/application/chatbot-api-sidecar_meal-plan-api/meal-plan-api/server.py`
- Modify: `packages/playground/src/playground/harbor/chat_api_session.py`
- Modify: `packages/playground/src/playground/inprocess/chatbot_shared_sidecar.py`
- Test: `environment/task-environments/application/chatbot-api-sidecar_meal-plan-api/meal-plan-api/test_llm.py`
- Test: `environment/task-environments/application/chatbot-api-sidecar_meal-plan-api/meal-plan-api/test_server.py`
- Test: `application/playground/backend/tests/test_harbor_chat_eval.py`

1. Write failing tests proving an evaluator-correlated request returns an internal trace
   envelope with exact grounded messages, `Qwen3-14B`, raw reply, usage/error metadata,
   and no auth data; ordinary product API responses must not expose the envelope.
2. Refactor `generate_llm_reply` to return reply plus trace data internally and stop
   silently discarding exception details.
3. Pass a trial correlation header/body field from the evaluator session. Consume and
   remove the trace envelope before persisting the public transcript, then append it to
   the trial `llm_calls.jsonl`.
4. Preserve deterministic fallback replies while tracing the failed LLM attempt.
5. Run sidecar and Harbor chat tests.

## Task 6: Build safe per-trial and per-job trace ZIP downloads

**Files:**

- Add: `application/playground/backend/service/trace_export_service.py`
- Modify: `application/playground/backend/service/harbor_job_service.py`
- Modify: `application/playground/backend/api/app.py`
- Test: `application/playground/backend/tests/test_trace_export_service.py`
- Test: `application/playground/backend/tests/test_api.py`

1. Write failing tests for stable ZIP layout, running/completed manifest state, partial
   failure artifacts, multiple trials, path traversal rejection, and an explicit file
   allowlist.
2. Build per-trial manifests and ZIPs containing canonical persona, rendered prompt,
   trajectory, events, prompts, LLM calls, artifacts, verifier output, and errors.
3. Build the job ZIP as a manifest plus nested trial trace directories.
4. Add streaming endpoints:
   `GET /api/harbor/jobs/{job}/trace.zip` and
   `GET /api/harbor/jobs/{job}/trials/{trial}/trace.zip`.
5. Run the service and API tests.

## Task 7: Group the UI selection, show free text realtime, and add ZIP buttons

**Files:**

- Modify: `application/playground/frontend/src/components/cockpit/setup/useSetupPersonaSampling.ts`
- Modify: `application/playground/frontend/src/components/cockpit/setup/PersonaSamplingRail.tsx`
- Modify: `application/playground/frontend/src/lib/api.ts`
- Modify: `application/playground/frontend/src/components/HarborJobDetail.tsx`
- Modify: `application/playground/frontend/src/components/RunDetail.tsx`
- Modify: `application/playground/frontend/src/lib/useHarborBatchLive.ts`
- Modify: relevant files under `application/playground/frontend/src/i18n/`
- Test: `application/playground/frontend/src/components/cockpit/setup/__tests__/PersonaSamplingRail.test.tsx`
- Test: `application/playground/frontend/src/lib/__tests__/useHarborLiveStreams.test.tsx`
- Add: `application/playground/frontend/src/components/__tests__/TraceDownloadButtons.test.tsx`

1. Write failing component tests for automatic pinned selection, segment labels and
   membership, narrative answer rendering, and both download scopes.
2. Teach setup state to flatten pinned segments into persona IDs without exposing
   `pinnedSegments` as a general manual sampling tab.
3. Render task strategy groups and hypotheses in the setup rail.
4. Render completed `free_text` answers immediately from `survey_answer` events; retain
   existing activity on reconnect/snapshot merge and deduplicate by event ID.
5. Add API blob-download helpers and the job/persona ZIP buttons with stable filenames
   and visible failure states.
6. Run Vitest and `npm run build`.
