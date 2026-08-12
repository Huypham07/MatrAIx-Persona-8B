# Product concept survey (FocusLoop)

MatrAIx **survey** reference task: read product context and a structured
questionnaire, then submit persona-aligned answers as JSON.

Canonical task package:

- `instruction.md` — scenario for the agent
- `input/context.md`, `input/questionnaire.yaml` — agent-facing materials
- `persona_strategy.json` — Playground cohort / sampling defaults (task root)
- `reporting.json` — batch reporting policy (task root)
- `task.toml`, `tests/` — runtime + verifier

This task reuses the shared `application/shared-survey-form` runtime. The
platform mounts `input/` into the trial; `persona_strategy.json` /
`reporting.json` stay at the task root for Playground / job aggregation.

See [Application Tasks](../README.md).

## Smoke run

**Oracle (no API key)** — harness smoke for the survey artifact contract:

```bash
uv run harbor run -p application/tasks/example-survey_product-feedback -a oracle
```

Writes `/app/output/survey_result.json` (platform schema) so the verifier can
score `reward=1`. Does **not** exercise the LLM persona path.

**One-persona** — smoke the full survey harness + persona agent:

```bash
uv run python application/scripts/generate_application_job.py \
  --task application/tasks/example-survey_product-feedback \
  --execution-mode auto \
  --persona-ids 0042

export ANTHROPIC_API_KEY="sk-ant-..."
export MATRIX_SURVEY_TASK_PATH=application/tasks/example-survey_product-feedback
uv run harbor run -c configs/jobs/application-task-job-recipe/example-survey-product-feedback-auto-n1.yaml
```

See [Application Quickstart](../../../docs/quickstart.md) for the UI path and full env vars.

## What this exercises

- Task-local survey docs in `input/` plus the shared `shared-survey-form` runtime
- `/app/input` → read materials → `/app/output/survey_result.json` contract
- Schema verifier (question coverage + interest scale)
