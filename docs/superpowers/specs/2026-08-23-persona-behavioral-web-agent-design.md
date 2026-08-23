# Persona-Behavioral Web Agent and Live UI

**Date:** 2026-08-23  
**Status:** Approved in chat; awaiting written-spec review  
**Primary runtime:** Local Qwen3-14B through an OpenAI-compatible endpoint  
**Primary environment:** Web, while repairing persona/task fidelity regressions shared by Survey and Chatbot

## 1. Objective

Make two personas performing the same web task observably different in how they search, inspect, compare, interact, decide, and stop. The difference must come from traceable persona attributes and enforced runtime policy, not from a post-hoc rationale or a cosmetic cursor animation.

The Playground must show each active agent's progress within roughly one second, including the latest browser screenshot, action, public step goal, persona evidence, and remaining behavior budget.

## 2. Findings That This Change Must Correct

Commit `5fc9386` made the local Qwen app runnable but reduced evaluation fidelity:

- `Persona.from_dict()` renders at most the first 35 active dimensions into `context`. Later behavioral dimensions such as `cog_patience`, `cog_attention_span`, and `cog_decision_speed` are consequently absent from the in-process Web prompt.
- In-process Web passes an empty persona YAML path and therefore cannot recover the canonical full persona render.
- In-process Chatbot uses two fixed user messages and does not condition those messages on the persona profile.
- Survey prompt construction dropped task-owned instruction and context material and forces free-text answers to one sentence, suppressing verbosity and storytelling signals.
- Web behavior before the model call is fixed: inspect up to three cards and perform the same scroll sequence for every persona.
- Browser failure falls back to a model-generated decision without observed page content.
- The worker writes multiple unrelated artifact filenames, assigns fixed positive feedback, and records unconditional success values.

The implementation must preserve the useful local-Qwen integration while removing these shortcuts.

## 3. Design Principles

1. **Persona identity and task instruction remain separate.** A persona says who acts; the task says what to accomplish.
2. **Full profile preservation.** No positional truncation such as `dimensions[:35]` is allowed.
3. **Observable causality.** Every persona-conditioned policy field records the dimensions that produced it.
4. **Prompt plus hard constraints.** The model proposes actions, while code enforces budgets, stagnation rules, and allowed actions.
5. **No fabricated completion.** Browser, model, or artifact failures remain technical failures and are never converted into simulated success.
6. **Reproducible by default.** Trial seed controls motor randomness. Model sampling stays fixed in research mode so persona effects are not confused with temperature changes.
7. **No anti-bot evasion.** CAPTCHA bypass, browser fingerprint spoofing, proxy rotation, and stealth plugins are outside scope.
8. **No hidden chain-of-thought exposure.** The UI displays a short public goal/reason supplied for the trace, not private model reasoning.

## 4. Chosen Approach

Use a custom in-process Playwright observe-plan-act loop as the primary local-Qwen Web backend. Keep the existing Harbor `persona-browser-use` backend available for supported models and Docker studies.

This approach is preferred because Qwen3-14B can be constrained to a small, validated action schema, the local endpoint is directly reachable, a visible host browser is easy to run, and persona-specific motor execution remains under application control. A Browser Use-only implementation would require relying on a larger action schema that smaller Qwen models are known to format unreliably.

Both Web backends consume the same compiled persona behavior policy and emit the same normalized trace format where their capabilities overlap.

## 5. Architecture

### 5.1 Canonical Persona Envelope

The Playground `Persona` representation gains lossless fields for the raw `dimensions` map and source metadata. `from_dict()` retains every dimension. Human-readable context is produced by the existing canonical dimension narrative builder rather than by a fixed first-N list.

Loading a requested persona becomes strict:

- missing file, invalid YAML, missing requested persona ID, or empty rendered identity fails the trial;
- no generic `Simulated Persona` fallback is permitted;
- `persona_meta.json` records the persona path, ID, schema version, display name, and a digest of the dimension map used by the trial.

### 5.2 Persona Behavior Policy Compiler

A pure compiler converts explicit persona dimensions into a `PersonaBehaviorPolicy`:

```json
{
  "cognitive": {
    "decisionStyle": "analytical",
    "searchDepth": "deep",
    "sourcePreference": ["technical", "forum"],
    "minimumOptions": 3,
    "minimumDistinctDomains": 2,
    "acceptanceRule": "cross_check_before_selecting"
  },
  "governor": {
    "maxSteps": 20,
    "maxConsecutiveNoProgress": 3,
    "maxActionFailures": 3,
    "allowAbandon": true
  },
  "motor": {
    "typingDelayMs": [25, 55],
    "dwellMs": [700, 1400],
    "scrollPixels": [280, 520],
    "cursorSteps": [12, 24],
    "typoRate": 0.0
  },
  "evidence": {
    "governor.maxSteps": ["cog_patience=Very high", "cog_attention_span=Long"]
  }
}
```

Initial mappings use only dimensions with a defensible semantic relationship:

- `cog_patience`, `cog_attention_span`, and `time_pressure` influence step and dwell budgets;
- `cog_decision_speed`, `decision_style`, and `need_for_closure` influence comparison and acceptance rules;
- `cog_skepticism`, `risk_tolerance`, and `skill_research` influence source checking and research depth;
- explicit technology capability fields can influence input speed and recovery behavior.

Age, gender, nationality, occupation, or income never directly determine motor errors. Typo and wrong-click simulation default to zero and require an explicit relevant capability/behavior signal or an experiment-level override.

Unknown or missing dimensions use neutral defaults and are listed in policy metadata. Policy compilation is deterministic and independently unit-tested.

### 5.3 Web Task Contract Loader

The runner loads the selected task's actual:

- `task.toml` metadata and environment definition;
- `instruction.md`;
- optional `input/context.md` and self-report schema;
- site URL and allowed domains;
- required output artifact name and JSON contract.

URL selection by task-name substring and generic `example.com` task descriptions are removed. A task without a resolvable start URL or output contract fails preflight with an author-facing error.

### 5.4 Observe-Plan-Act Loop

Each Web step performs:

1. **Observe:** collect URL, title, viewport screenshot, normalized interactive elements, relevant visible text, scroll position, visited-domain history, and prior action result.
2. **Plan:** ask Qwen for exactly one action using the full persona identity, compiled cognitive policy, task contract, current observation, and budget summary.
3. **Validate:** parse and validate the structured action. One repair request is allowed for malformed JSON; repeated invalid actions count toward the failure governor.
4. **Govern:** reject disallowed actions, detect stagnation, enforce step/domain/option budgets, and decide whether the persona may continue, complete, or abandon.
5. **Act:** execute through the persona-aware Playwright motor adapter.
6. **Record:** save the screenshot, normalized action, public step goal, action result, policy evidence, and updated counters before the next observation.

The initial action union is intentionally small:

```text
search, navigate, click, type, scroll, back, wait,
select_option, extract_visible, done, abandon
```

Every proposed action includes `public_goal` and `persona_evidence`. These fields are concise explanations for audit/UI use and must not request or store hidden chain-of-thought.

### 5.5 Dynamic Governor

The governor owns termination; prompting alone does not.

It tracks:

- total steps and action failures;
- repeated action signatures and unchanged page observations;
- distinct URLs/domains visited;
- options inspected and evidence collected;
- task artifact validity;
- persona-specific minimum exploration and maximum patience.

Termination statuses are distinct:

- `completed`: valid task artifact produced;
- `abandoned`: persona policy intentionally stopped the task;
- `budget_exhausted`: hard limit reached before valid completion;
- `technical_failure`: browser, model, parsing, or task-contract failure.

An impatient persona may abandon early, but the trace must state which policy threshold was met. A patient persona is not forced to consume its full budget once its acceptance rule is satisfied.

### 5.6 Persona-Aware Motor Adapter

The Playwright adapter applies a seeded motor policy:

- mouse movement uses multiple interpolated points with a bounded curved path and target-relative variation;
- click delay and dwell time use seeded values inside policy ranges;
- typing emits per-key events with bounded delay;
- scrolling uses wheel events in persona-specific increments and cadence;
- every motor action is cancelable and reports its measured duration.

Playwright primitives are sufficient for the first implementation. No Node-only `ghost-cursor` dependency is introduced. Motor behavior serves visible simulation and measurement, not bot-detection evasion.

### 5.7 Other Environment Fidelity Repairs

The same canonical persona envelope is used by Survey and Chatbot.

Survey restores task-owned instruction, context, questionnaire semantics, rationale flags, confidence flags, and output envelope. Chunking may remain for local-model reliability, but each chunk receives the same full task and persona context. Free-text length is controlled by the questionnaire, not globally forced to one sentence.

Chatbot restores the existing persona UserSim loop. The persona model generates each user turn and decides `continue`, `satisfied`, or `give_up` under a real `maxTurns` budget. A local in-process SUT may remain as a fallback application, but it is separate from the persona agent and does not fabricate feedback.

## 6. Realtime Event and Trace Contract

The current append-only `events.jsonl`, trial-events API, and 800-1000 ms frontend polling are retained. This gives near-real-time behavior without introducing a second transport.

The Web runner emits after every material state change:

```text
web_observation
web_plan_ready
web_action_started
web_action_completed
web_governor_update
web_step_checkpoint
web_termination
```

`web_step_checkpoint` contains the normalized trace event and screenshot filename. At the same checkpoint the runner atomically rewrites `agent/trajectory.json`, so both the event feed and existing trace endpoint remain useful.

The normalized trace event adds:

```json
{
  "step": 6,
  "source": "persona-agent",
  "message": "Compare a second technical source before deciding.",
  "actions": [{"name": "search", "arguments": {"query": "..."}}],
  "screenshotFile": "images/step_006.png",
  "personaEvidence": ["cog_skepticism=Very high"],
  "policyEffect": "minimumDistinctDomains=2",
  "governor": {
    "usedSteps": 6,
    "maxSteps": 20,
    "distinctDomains": 1,
    "optionsInspected": 2,
    "status": "continue"
  },
  "durationMs": 1240
}
```

Screenshots are written before the checkpoint event is appended, preventing the UI from receiving a URL to an incomplete file.

## 7. Live Playground UI

The existing `WebEvalCockpit` and `HarborTraceReplay` are extended rather than replaced.

During a run the UI shows:

- latest browser screenshot, auto-following the newest step;
- current phase and public step goal;
- action name, query/target, and action result;
- persona evidence and the resulting policy constraint;
- used/max steps, distinct sources, options inspected, and stagnation state;
- explicit completion, abandonment, budget exhaustion, or technical failure reason;
- the existing screenshot scrubber and step grid for replay.

For batch runs, the existing selected-trial mechanism continues to poll detailed events only for the trial in view. The cohort grid shows coarse stage/termination status without fetching every trajectory.

The target UI update latency is under 1.5 seconds on the local machine. This is action-level near-real-time replay, not high-frame-rate video streaming. A visible headful browser may still be watched directly.

## 8. Behavioral Comparison

Each completed Web trial writes a `behavior_summary.json` containing:

- queries issued;
- URLs and distinct domains visited;
- options inspected;
- action counts by type;
- scroll distance and dwell/typing duration summaries;
- step count and failure count;
- termination status/reason;
- selected outcome and decision basis;
- compiled policy plus evidence.

The single-trial UI shows this summary alongside the task result. Batch aggregation exposes the same fields so two personas on the same task can be compared without reading raw logs.

The first acceptance demonstration uses one controlled, deterministic web task and two intentionally contrasted personas. It must visibly demonstrate differences in query construction, exploration depth, source/option selection, motor timing, stopping behavior, and final choice where the profiles support a different choice.

## 9. Sampling and Experiment Modes

Two explicit modes prevent scientific and demo goals from being mixed:

- **Research mode (default):** fixed model temperature/top-p across personas, seeded motor policy, complete policy/trace provenance.
- **Expressive demo mode:** may apply bounded persona-derived model sampling parameters, but records them in the trace and comparison output.

Hard governor and cognitive-policy differences operate in both modes. Temperature is never the only mechanism producing persona differentiation.

## 10. Error Handling

- Browser launch/navigation failure produces `technical_failure`; no model-only selection fallback runs.
- Invalid Qwen action receives one structured repair attempt. Continued invalid output consumes the action-failure budget.
- Missing task URL, instruction, or artifact contract fails preflight.
- Missing persona or empty canonical render fails before browser launch.
- Missing target element returns a failed action observation to the planner; it does not silently pass.
- An artifact is successful only after task-specific schema validation and verifier execution.
- Partial trajectories and screenshots remain available after failure.

## 11. Testing Strategy

### Unit tests

- lossless persona parsing and canonical full-profile rendering;
- policy mappings, neutral defaults, evidence provenance, and deterministic seed behavior;
- governor completion, abandonment, stagnation, failure, and budget transitions;
- action parsing/repair and schema rejection;
- motor range calculations and typo defaults;
- task contract and artifact-name resolution;
- event-to-UI state mapping.

### Integration tests

- a local fixture website exercises search, multiple results, navigation, scrolling, selection, and artifact writing without public-network variability;
- mocked Qwen responses execute a complete multi-step trajectory;
- malformed actions demonstrate repair and failure behavior;
- checkpoints expose screenshots and partial trajectories while the run is active;
- Survey retains task context/rationale semantics;
- Chatbot uses generated persona turns rather than fixed messages.

### Behavioral acceptance test

Run two contrasted personas against the same fixture task with the same research-mode model settings. Assert differences in at least three predeclared behavioral metrics while validating both trajectories against their compiled policies. The test must not assert that every run chooses a different final item, because two realistic users may reach the same outcome through different behavior.

### Manual smoke test

- launch the local Qwen Playground;
- select two personas and one Web task;
- observe action-level UI updates and screenshots;
- inspect final artifacts and behavior summaries;
- confirm failures are labeled as failures rather than converted into positive results.

## 12. Rollout and Compatibility

- Preserve current task schemas and existing Harbor trace readers.
- Add fields to trace events compatibly; old events still render.
- Keep `persona-browser-use` selectable.
- Make the new in-process persona Web loop the `auto` backend for `local/*` models after its preflight passes.
- Do not remove OS-App task definitions. Its UI visibility remains a separate product-scope decision.
- Remove or quarantine the one-shot Web runner only after parity tests cover task loading, output validation, events, and debrief mapping.

## 13. Out of Scope

- CAPTCHA solving or bypass;
- stealth browser fingerprints, anti-detection plugins, proxies, or WAF circumvention;
- arbitrary operating-system control outside the existing OS-App runtimes;
- high-frame-rate browser video streaming;
- claiming 100% persona adherence;
- using demographic stereotypes to infer motor impairment or error rates.

## 14. Completion Criteria

The change is complete when:

1. no Web, Chatbot, or Survey local-Qwen path drops the full persona profile or required task context;
2. Web executes a validated multi-step browser loop with persona-conditioned cognitive, governor, and motor policies;
3. every action is checkpointed with screenshot and policy evidence and appears in the UI within 1.5 seconds locally;
4. technical failures cannot become fabricated successful decisions;
5. task-specific output artifacts and verifiers remain authoritative;
6. two contrasted personas produce measurably different, policy-consistent trajectories on the same controlled task;
7. targeted backend, frontend, integration, and behavioral tests pass.
