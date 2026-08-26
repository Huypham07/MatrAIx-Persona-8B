# Playground Persona and Realtime Fidelity Design

**Date:** 2026-08-25

**Status:** Approved in chat; awaiting written-spec review

## Purpose

Make local Playground survey and chatbot runs faithful to the selected persona and observable in real time. A run must use the complete canonical persona prompt, obtain its answers and conversation from real model calls, publish truthful incremental events for single- and multi-persona jobs, and update the center cockpit without periodic refresh flicker.

## Problems Confirmed in the Current Branch

1. `Persona.from_dict` creates a display context from at most 35 dimensions (`active_dims[:35]`). This truncation first appeared in commit `5fc9386`. Commit `fb85e19` replaced that lossy view with a canonical persona envelope and path-backed prompt rendering, but a later branch update regressed it.
2. The current host-native worker in `harbor_job_service.py` hard-codes exactly two chatbot user messages, a two-turn transcript, and positive feedback with rating 9. It does not run the existing user-simulator conversation loop.
3. The survey runner calls the model in chunks but silently replaces absent or invalid model values with a midpoint, the first choice, or an empty string. Those synthetic values are persisted as if the persona supplied them.
4. Survey trajectory contains lifecycle events plus an ask and answer event for each question. Presenting the raw event count as a question-step count makes a survey appear to contain extra questions.
5. Live UI state is driven by periodic polling. The uncommitted stream experiment only follows a selected trial, passes an event where an array is expected in one hook, places a React hook outside a component in another, does not support cancellation at the transport layer, and can replace live state with final debrief state in a way that causes visible flashing.
6. The local chatbot SUT can return a generic temporary-failure message repeatedly. The current hard-coded worker treats those replies and its own hard-coded feedback as a successful evaluation.

## Scope

This change covers local/host-native survey and chatbot execution, canonical persona loading and prompt presentation, the Harbor event transport used by Playground, single-run and batch cockpit state, and survey trajectory presentation.

Web and OS-app execution semantics are not redesigned. They may consume the shared event transport but their agents, artifacts, and verifier logic remain unchanged. Task sampling fields continue to control cohort selection and aggregation only; they never filter the persona prompt.

## Design Principles

- The prompt shown in the run debrief is the prompt used for inference.
- No synthetic model answer or score may be represented as a genuine persona answer.
- Persisted artifacts and live events are two views of the same execution, not separately fabricated results.
- Event delivery is resumable and idempotent.
- Batch size changes concurrency and presentation, not fidelity.
- A transient application failure is observable and retried within a small bound; a persistent failure makes the run fail truthfully.

## 1. Canonical Persona Contract

### Data envelope

`playground.types.Persona` will again carry:

- all `dimensions` without filtering or count limits;
- `schema_version`;
- `persona_path`, resolved to the canonical YAML snapshot used by the trial;
- the existing legacy summary/context/preferences fields for backward compatibility.

`to_dict` and `from_dict` round-trip those fields. `from_dict` must not construct a reduced prose profile from `dimensions`.

### Prompt rendering

When a canonical path or dimension-backed persona is present, prompt rendering uses the repository persona loader and `PERSONA_SYSTEM_TEMPLATE`. Failure to load or render that canonical source is a run error; it must not silently degrade to the generic `Who you are`, preferences, dislikes, and constraints paragraph.

The legacy prose renderer remains only for genuinely legacy personas with no canonical path and no dimensions.

The worker resolves relative persona paths against the repository root, passes that resolved source through survey/chat runners, and saves complete persona metadata for the debrief. Task `persona_strategy.json` sampling fields do not participate in prompt construction.

### Debrief presentation

`prompts.personaPrompt` stores the exact rendered persona block sent to the persona model. The Persona profile rail prefers this value. Complete dimensions remain available as a structured fallback and diagnostic view, but the UI does not substitute a task-focused subset for the actual prompt.

## 2. Survey Execution

### One completion per question

The survey runner processes questions in authored order. For each question it:

1. emits `survey_question_started` with question identity, prompt, type, index, and total;
2. calls the configured persona model with the canonical persona system prompt, task context, the single question, its valid response contract, and previously answered questions as compact continuity context when relevant;
3. validates the response against the authored question type and options;
4. retries once with a validation-correction prompt if parsing or validation fails;
5. emits `survey_answer` containing the real validated value and optional rationale/confidence;
6. atomically updates the partial survey artifact.

The model is therefore genuinely called for every question, and the UI can show the active question while the request is in flight and append the answer immediately afterward.

### Invalid responses

The normalizer may coerce representation without inventing meaning, for example numeric string `"4"` to integer `4`. It may not clamp an out-of-range rating to a valid rating, choose the first option, choose a midpoint, or create an empty answer for a required question.

After the correction retry fails, the trial terminates with a structured `invalid_model_response` error naming the question. Partial answers remain inspectable but completion is invalid and the run is not reported as a successful completed survey.

### Artifacts and trajectory

The worker writes partial `structured_output.json` and `survey_result.json` after each validated answer using atomic replace, then writes the final artifacts once. The standardized final trajectory retains:

- one `survey_started` lifecycle event;
- one `ask_question` and one `answer_question` per completed question;
- one `survey_completed` lifecycle event only for successful completion, or a failure lifecycle event otherwise.

The UI labels lifecycle separately and reports question progress from `numAnswered / numQuestions`. It never describes raw trajectory event count as the number of survey questions or answers.

## 3. Chatbot Execution

### Real user-simulator loop

The host-native worker delegates chatbot trials to the existing `run_inprocess_chatbot_eval` / user-simulator runner. It must not construct messages, transcript, application result, feedback, or scores itself.

The simulator receives the complete persona prompt, task instruction/context, task-owned chatbot capability definitions, and prior conversation messages. Each next message must be generated after observing the previous application response.

### Conversation depth

The default conversation policy is:

- minimum 5 completed user/application exchanges before `end_conversation` is accepted;
- maximum remains the launch configuration, with the current UI default of 8;
- if an authored task explicitly requires a larger minimum, the task value wins;
- if configured maximum is below the effective minimum, launch validation rejects the configuration instead of weakening the minimum silently.

Before the minimum, an attempted `end_conversation` is converted into another simulator step with an observation instructing the persona to ask a natural, context-specific follow-up. This is a runner invariant rather than a prompt-only suggestion. The simulator guidelines still request progressive disclosure, reaction to prior answers, specific follow-ups, and pushback when needs are unmet.

### Application failures

A blank reply, a recognized temporary-failure reply, timeout, connection error, or model-provider error is not a meaningful completed exchange. The application adapter retries a transient failure at most twice with bounded backoff while preserving the session. Each attempt emits an error/retry event.

If no valid reply is obtained, the trial ends with `application_unavailable`; it does not generate positive self-report feedback or successful evaluation artifacts. User-visible error text includes the underlying provider/sidecar cause where available. The fallback in-process SUT may be used only when the task explicitly permits it; an unavailable task-owned sidecar is otherwise an evaluation failure rather than an invisible product substitution.

### Truthful feedback

Final self-report is generated by the configured persona model from the actual transcript and task-owned schema. Scores and rationales are never constants in the worker. Partial transcripts remain available when the trial fails, but successful feedback artifacts are only produced after a valid conversation termination.

## 4. Realtime Event Transport

### Job-scoped SSE

Add a job-scoped Server-Sent Events endpoint. One connection multiplexes lifecycle and trial events for every trial in the job. Each SSE message contains:

```json
{
  "id": "monotonic-job-event-id",
  "jobName": "job-name",
  "trialName": "trial-name-or-null",
  "event": { "type": "survey_answer" }
}
```

Each trial append also writes the wrapped event to an append-only job event journal under an inter-process file lock. The journal's ending byte offset is the stable, monotonically increasing job event ID. The server includes it in the SSE `id:` field and resumes strictly after that byte offset from `Last-Event-ID` or an explicit cursor query for clients that cannot set that header. Trial events retain their current payload shapes so the existing cockpit reducer can evolve incrementally.

The stream sends heartbeat comments while idle, closes after a terminal job event and all trial event files have been drained, and stops promptly on client disconnect. It does not swallow exceptions silently: expected disconnects are quiet, while server-side read/serialization errors produce a terminal stream error event and are logged.

### Event persistence and atomicity

Trial writers continue appending their existing NDJSON and additionally append a job envelope to the journal while holding the journal lock; both files are flushed before returning. The stream tails this journal from the requested byte offset, so concurrent trial ordering is the serialized journal order and correctness does not depend on wall-clock timestamps.

Events receive stable IDs before delivery. Reconnect replay and React Strict Mode may deliver an event more than once, so reducers deduplicate by ID. The job snapshot endpoint remains available for bootstrap, manual recovery, and terminal reconciliation, not periodic live rendering.

### Fallback

If EventSource cannot connect, the UI exposes the transport error and may use the existing incremental event endpoint as a compatibility fallback. Polling fallback is bounded and explicitly marked degraded; it is not the primary path.

## 5. Frontend State and Presentation

### Shared stream client

A single stream client owns EventSource lifecycle, replay cursor, parsing, abort/close, reconnect policy, and typed envelopes. Both `useHarborCockpitRun` and `useHarborBatchLive` consume it instead of implementing fetch-reader loops independently.

Single-run flow bootstraps the job/trial identity, subscribes once, applies events as they arrive, and fetches the debrief only after the terminal event. Batch flow subscribes once for the job and maintains `liveByTrial` for every persona, regardless of which trial is selected.

### Center cockpit

For survey, the center pane shows the active question immediately, then replaces its pending state with the returned answer card. For chatbot, user and application bubbles appear on their corresponding events. For batch, the grid shows each persona's current stage/progress while the selected cell's detailed live content stays in the center pane.

### No flicker

Live state is a monotonic reducer state keyed by trial and event ID. Terminal debrief reconciliation merges richer final fields into that state. It does not clear the live job, remount the center content, or swap through an empty loading view. Stable React keys use trial/question/turn identifiers rather than array positions.

Animation runs only for newly inserted answers/turns. Replayed or reconciled items are marked existing so reconnect and completion do not replay entrance animations.

## 6. Worker Boundary

The large host-native implementation is moved out of `HarborJobService` into a focused worker module again. `HarborJobService` remains responsible for launch coordination and calls `run_inprocess_trial(...)`.

The worker owns manifest parsing, canonical persona resolution, task-kind dispatch, event/artifact persistence, and truthful result status. Survey and chatbot behavior stays in their existing runner modules. Current Web/OpenHands and OS-app dispatch decisions remain unchanged; extracting the worker must not restore obsolete web-agent selection logic from earlier commits.

## 7. Error and Completion Semantics

The following are terminal failures, not successful runs with fallback content:

- canonical persona missing or unrenderable for a dimension-backed persona;
- required survey answer invalid after correction retry;
- chatbot application unavailable after retry;
- persona model/provider failure after retry;
- event transport failure in the browser prevents live display but does not change an otherwise truthful trial result; the UI reconciles from the snapshot/debrief and reports degraded realtime separately.

Every failure writes a failure result, emits a terminal event, preserves already-produced truthful partial artifacts, and exposes an actionable message in the cockpit. A trial is `completed: true` only when its task-specific artifact contract is satisfied.

## 8. Testing Strategy

All production behavior changes follow red-green-refactor.

### Backend regression tests

- A persona with more than 35 dimensions round-trips completely and renders a late dimension from its canonical path.
- Canonical rendering failure is explicit and never falls back to generic prose.
- Sampling fields do not alter the persona prompt.
- Survey makes one model completion per question and emits started/answer events in order.
- Invalid survey values trigger correction and then fail without synthetic defaults.
- Partial survey artifacts contain only validated model answers.
- Host-native chatbot worker calls the real simulator runner and contains no fixed two-message path or constant feedback.
- Conversation termination is rejected before five valid exchanges and accepted at/after the minimum.
- Temporary chatbot failures retry; persistent failure produces no positive feedback.
- Job SSE delivers multiple trials, preserves per-trial order, replays from cursor, emits heartbeats/terminal events, and stops on disconnect.

### Frontend tests

- Stream client parses typed SSE envelopes, resumes from cursor, closes on cleanup, and reports malformed/terminal errors.
- Reducer deduplicates replayed events and keeps every trial's state in batch mode.
- Survey pending question and answer card update incrementally.
- Selected batch persona changes detail without losing other personas' progress.
- Terminal debrief merge preserves rendered content and does not transition through empty state.
- Persona rail shows the complete stored `personaPrompt`.
- Survey progress and trajectory labels distinguish question count from lifecycle/event count.

### Verification commands

Run the focused backend tests during each TDD cycle, then the complete owned backend/unit suites. Run frontend unit tests, `npm run typecheck`, and `npm run build`. Run `git diff --check`. Finally launch one survey, one meal-planning chatbot, and a two-persona batch against the configured local model and inspect the emitted events/artifacts and center UI.

## 9. Migration and Compatibility

Existing completed jobs remain readable. Debrief prompt enrichment continues to support legacy runs with only `context` or older prompt bundles. Existing per-trial incremental event and job snapshot endpoints remain during migration.

New live clients prefer job SSE. Old clients continue to function via their existing endpoints. No task authoring schema changes are required. Canonical persona metadata added to new artifacts is additive.

## 10. Acceptance Criteria

1. A selected canonical persona's complete rendered system persona block is both sent to the persona model and visible in the run debrief; no 35-field or task-focus truncation occurs.
2. A survey visibly advances question by question from genuine model completions. No invalid/missing model output becomes a fabricated neutral or first-option answer.
3. A chatbot run contains at least five meaningful, context-dependent exchanges by default and real model-generated self-report, unless it truthfully fails.
4. Single- and multi-persona runs update the center cockpit immediately through one job SSE connection without periodic refresh as the primary mechanism.
5. Reconnect, selected-trial changes, and running-to-completed transition do not duplicate content or flash through an empty screen.
6. Survey UI reports authored questions/answers separately from lifecycle and ask/answer trajectory events.
7. Existing Web/OpenHands and OS-app behavior is not regressed.
8. Focused and full backend tests, frontend tests, typecheck, build, diff check, and the three manual live-run scenarios pass before completion is claimed.
