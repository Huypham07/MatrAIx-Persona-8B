# Task 3 report — truthful multi-turn chatbot evaluation

## Delivered

- Added `PlaygroundConfig.min_turns` (default `5`) and `max_turns` default `8`.
  Construction rejects a maximum below the configured minimum, and serialized
  config includes `minTurns`.
- Parsed task-owned `runtimeDefaults.minTurns`; the restored
  `inprocess_chatbot_config` selects it and defaults an unspecified maximum to
  `8`.
- Restored `inprocess_chatbot_config` and `run_inprocess_chatbot_eval` from
  the historical implementation while retaining the current persona prompt
  path through the canonical UserSim runner.
- Enforced the depth invariant in both synchronous and asynchronous runner
  loops. Premature end actions are retried at most three times with an
  observation-bearing prompt requiring a specific, natural follow-up.
- Added `ApplicationUnavailable` and three-attempt retry handling for blank,
  recognized temporary, and transport/provider failures. HTTP sidecar failure
  no longer falls back invisibly to a generated success; the in-process
  adapter likewise propagates provider failure instead of fabricating a reply.

## TDD evidence

- RED: the new configuration test initially failed because the restored
  in-process config passed `None` for `max_turns` instead of using `8`; a
  separate opening-action test exposed that an immediate end was still
  accepted before the first exchange.
- GREEN: `PYTHONPATH=packages/playground/src:application/playground uv run --with pytest pytest packages/playground/src/playground/tests/test_runner.py packages/playground/src/playground/tests/test_user_sim.py application/playground/backend/tests/test_inprocess_eval_runners.py application/playground/backend/tests/test_chatbot_task_config.py -q`
  completed with **34 passed**.
- `git diff --check` completed without output and Ruff reported **All checks
  passed** for the Task 3 Python files.
- Broader owned verification completed with **101 passed, 11 failed**. The
  remaining failures predate/sit outside Task 3: DashScope/model-client
  routing, missing `os` import in `openai_client`, mismatched persona catalog
  fixtures, legacy scoring labels, and a legacy default-persona-model
  expectation. The only Task-3-caused `max_turns=3` test fixture failure was
  corrected by declaring `min_turns=3` explicitly.

## Follow-on dependency

`harbor_job_service.py` still contains the legacy hard-coded two-message,
fixed-score dispatcher in this base checkout. Per task ownership, Task 4 will
port the historical in-process worker dispatcher to call the restored APIs;
this Task intentionally does not modify that file.
