# Task-Specific Persona Segments, Native-Language Simulation, and Trace Export

Date: 2026-08-25

## Status and scope

This design is limited to the first four tasks below:

- `chat_meal-planning-nutrition`
- `survey_price-sensitivity-hasbro-gaming-candy-land`
- `survey_annual-checkup-habits`
- `example-survey_product-feedback`

The goal is to make persona comparisons intentional and auditable. Each task owns a
small set of behavioral segments inferred from its subject matter. A segment contains
exactly two pinned personas. The number of segments and the dimensions used to define
them are task-specific; there is no global two-sided or four-group template.

This design also makes persona-authored output follow the persona's primary language,
adds genuinely open survey questions, and exports complete per-trial and per-job traces.

## Task-specific segment contract

`persona_strategy.json` advances to schema version `1.1` and may use the new pinned
segment mode:

```json
{
  "schemaVersion": "1.1",
  "pool": "matraix-persona-dev-sample",
  "segments": [
    {
      "id": "budget_restricted_cautious",
      "label": "Budget-constrained and diet-restricted",
      "hypothesis": "Recommendations should be cheaper, conservative, and restriction-aware.",
      "dimensions": {
        "economic_motivation": ["Cost-sensitive"],
        "risk_tolerance": ["Risk-averse", "Cautious"],
        "health_dietary_restriction": ["Allergy", "Medical"]
      },
      "personaIds": ["0147", "0155"]
    }
  ],
  "sampling": {
    "mode": "pinnedSegments",
    "personasPerSegment": 2
  }
}
```

The pinned IDs are the execution source of truth. `dimensions` and `hypothesis` make
the experimental intent reviewable and are validated against the raw persona YAML.
Validation requires:

- a stable, unique segment ID and non-empty label/hypothesis;
- exactly two unique persona IDs per segment;
- no persona reused by another segment in the same task;
- every persona exists in the declared pool;
- each persona satisfies the declared segment dimensions;
- `primary_language` and `region` exist for each selected persona;
- the flattened selection order is segment order, then `personaIds` order.

Loading a task strategy in Playground selects all pinned personas immediately. The
setup rail displays segment labels and the two personas in each segment instead of
showing one undifferentiated sample. Existing strategy modes remain backward compatible
for tasks outside this scope.

## Initial segments and pinned personas

The following cohort is intentionally small enough to compare manually while covering
different behavioral mechanisms and languages. Exact values are validated from
`persona/datasets/matraix-persona-dev-sample` rather than inferred from names.

### Meal planning and nutrition: four segments

1. **Budget-constrained, cautious, and restricted** — `0147` and `0155`.
   The relevant fields are economic motivation, risk tolerance, dietary restriction,
   shopping/budget behavior, and diet. Expected effect: cheap, safe substitutions and
   more explicit constraint checking.
2. **Plant-based and values-led** — `0102` and `0166`.
   The relevant fields are diet type, restriction/ethics, veganism attitude, and meal
   preparation. Expected effect: plant-based recommendations and rejection of
   incompatible ingredients.
3. **Convenience-first, infrequent meal preparation** — `0157` and `0162`.
   The relevant fields are diet type, meal-prep frequency, shopping style, and risk
   tolerance. Expected effect: simpler meals, fewer steps, and realistic convenience
   substitutions.
4. **Nutrition-aware, regular planners** — `0101` and `0195`.
   The relevant fields are nutrition familiarity, meal-prep frequency, health goals,
   and decision style. Expected effect: more structured plans and detailed follow-ups.

### Candy Land price sensitivity: three segments

1. **Budget-constrained parent bargain hunters** — `0154` and `0192`.
   Relevant fields: parental status, economic motivation, income, shopping style, and
   budget tracking. Expected effect: high price pain, sale dependence, or rejection.
2. **Value-evaluating parents** — `0146` and `0173`.
   Relevant fields: parental status, value-driven motivation, risk tolerance, quality
   preference, and shopping style. Expected effect: price acceptance only when quality
   and child fit justify the increase.
3. **Affluent or quality-first gift buyers** — `0009` and `0016`.
   Relevant fields: income, premium/value motivation, quality preference, family role,
   and brand/trust attitudes. Expected effect: lower price pain and more emphasis on
   quality or suitability than the absolute price.

### Annual checkup habits: four segments

1. **High health need with weak access** — `0145` and `0197`.
   Relevant fields: general health, insurance, age, income, trust, and risk tolerance.
   Expected effect: unmet need, cost/access barriers, and irregular checkups.
2. **Relatively healthy with weak access or low urgency** — `0156` and `0192`.
   Relevant fields: general health, insurance, perceived risk, and health familiarity.
   Expected effect: postponement because preventive care feels less urgent.
3. **Healthy and adequately insured preventive users** — `0164` and `0167`.
   Relevant fields: general health, insurance, health familiarity, and trust. Expected
   effect: regular scheduling and stronger belief in preventive checkups.
4. **Older adults with meaningful health needs** — `0150` and `0166`.
   Relevant fields: age, health, insurance, trust, and technology comfort. Expected
   effect: higher clinical need but different scheduling and preparation friction.

### FocusLoop product feedback: three segments

1. **Budget- and subscription-resistant parents** — `0154` and `0183`.
   Relevant fields: parental status, economic motivation, subscription attitude,
   income, budget tracking, and shopping style. Expected effect: stay free, avoid
   annual prepay, and require a very strong upgrade case.
2. **ROI-driven value evaluators** — `0146` and `0173`.
   Relevant fields: parental status, value motivation, decision/risk style, quality
   preference, and technology comfort. Expected effect: pay only after sustained proof
   of family coordination value.
3. **Digitally ready, convenience-oriented parents** — `0101` and `0194`.
   Relevant fields: parental status, technology comfort, new-technology attitude,
   household complexity, and family values. Expected effect: stronger beta intent and
   willingness to adopt when automation reduces coordination work.

If validation reveals a sparse profile does not actually contain a declared dimension,
the implementation must replace it with another real profile in the same conceptual
segment; it must not weaken or silently skip the validator.

## Survey free-text questions

`free_text` remains a first-class questionnaire type and is answered by the persona LLM
through the same per-question execution path as other question types. It is never filled
from a constant or deterministic fixture. In addition to existing numeric free-text
items in annual checkup, add one narrative, required item to every scoped survey:

- Candy Land: “What specifically would make the current $16.24 price feel worth paying,
  or why would nothing make it worthwhile for you?”
- Annual checkup: “In your own words, what is the biggest reason you keep up with or put
  off regular checkups?”
- FocusLoop: “What specific feature, concern, or daily frustration would most influence
  whether you pay for FocusLoop?”

Realtime events contain the question prompt, question type, answer, rationale when
requested, segment ID, persona ID, and expected language. The center activity view shows
the free-text answer as soon as that question finishes.

## Persona language contract

The canonical raw persona profile stays in English for auditability. A high-priority
language block is appended to every system prompt that asks the persona to produce
natural language:

- use `dimensions.primary_language` for persona-authored conversation, free text, and
  rationale text;
- do not switch to English merely because the task instruction is English;
- keep JSON keys, enums, question/option IDs, URLs, numeric values, currencies, product
  names, and copied UI/site text unchanged;
- where a machine-readable answer selects an option, retain the option ID and place any
  explanation in the persona language;
- do not translate the canonical profile artifact itself.

The contract applies to survey answers, chat turns, post-run self-report, and report
feedback. Each LLM trace record includes `expectedLanguage` so violations are easy to
inspect.

## Complete trace capture

Each Harbor trial gets a correlation context containing job ID, trial ID, task path,
persona ID, segment ID, and expected language. All model entry points—including the meal
planning sidecar—write normalized append-only LLM call events through this context.

An LLM call record contains:

- call ID, step name, timestamps, duration, model, endpoint class, and retry number;
- complete system/developer/user messages actually sent;
- tool/schema request data when present;
- raw returned model content and parsed output;
- token usage and finish reason when exposed by the provider;
- validation/retry/error details;
- job/trial/task/persona/segment correlation fields and `expectedLanguage`.

Secrets, API keys, authorization headers, and process environment dumps are never
written. “Complete output” means the content returned by the model API; it does not mean
private provider reasoning that the API did not return.

Each trial directory exposes:

- `manifest.json`
- `persona.yaml` and the rendered persona prompt block
- `trajectory.json`
- `events.jsonl`
- `prompts.json`
- `llm_calls.jsonl`
- task artifacts, verifier output, and captured errors

Two ZIP endpoints are added:

- one ZIP for the entire job, containing a manifest plus every persona/trial directory;
- one ZIP for a selected persona trial.

The job detail view gets “Download task trace ZIP.” Each persona trial/run gets its own
“Download persona trace ZIP” button. ZIPs are generated from an allowlisted trial root,
streamed rather than accumulated in browser memory, and use stable relative paths.

## Realtime behavior

The existing Harbor event stream remains the primary transport. Segment metadata,
questions, answers, chat turns, and LLM step completion events arrive over the same
stream. Reconnection resumes from the last event cursor and deduplicates by event ID.
Polling remains only a degraded fallback and must not replace or clear already-rendered
activity, preventing multi-persona runs from flashing when a snapshot arrives.

## Failure behavior

- Invalid task strategy: reject with an actionable validation error before launch.
- Missing pinned persona: show the exact task, segment, and persona ID.
- LLM failure: retain attempted prompts, retry/error metadata, and partial trajectory.
- Sidecar failure: attach sidecar logs to the trial trace and mark only that trial failed.
- Trace ZIP requested during a run: return the consistent artifacts available at request
  time and mark the manifest as `running`; completed runs are marked `complete`.
- Language mismatch: preserve the answer and emit an auditable warning; do not invent a
  translated answer after the fact.

## Verification strategy

Implementation follows test-driven development:

1. Unit tests for strategy normalization/validation, including variable segment counts,
   two IDs per segment, uniqueness, existence, and dimension matching.
2. Task contract tests proving only the four scoped strategies use pinned segments and
   all selected raw personas pass validation.
3. Survey tests proving each scoped survey contains a narrative `free_text` question and
   that answers flow through the LLM execution path and realtime events.
4. Prompt tests proving primary-language instructions appear in every persona-authored
   LLM call without changing machine-readable keys/options.
5. Trace tests for complete prompt/output records, redaction, partial failure retention,
   job ZIP layout, and persona ZIP layout.
6. Frontend tests for grouped task-strategy selection, realtime free-text rendering,
   reconnect deduplication, and both ZIP buttons.
7. Targeted backend/frontend suites followed by the frontend production build.

## Non-goals for this iteration

- Converting every application task to pinned segments.
- Automatically discovering optimal segments at runtime.
- Translating canonical persona YAML or task instructions.
- Storing hidden chain-of-thought or unavailable provider internals.
- Adding a fixed global number of persona groups.
