# Task 7 report — stable realtime Harbor cockpit rendering

## Delivered

- Replaced single-run and batch polling loops with one typed job EventSource
  connection per active job. Cursor state is ref-backed, so incoming envelopes
  do not re-subscribe; cleanup closes the source during reset, cancellation,
  unmount, and React Strict Mode cycles.
- Batch state now retains `liveByTrial` for every trial regardless of the
  selected persona. The only HTTP snapshot is bootstrap; one explicit bounded
  snapshot is used when the transport degrades, and terminal job events perform
  one final reconciliation.
- Single runs bootstrap trial identity once, render all trial envelopes through
  the shared reducer, and reconcile the detail/debrief only on the terminal job
  lifecycle event. Final state merges with partial survey answers and chat turns
  by stable question/turn identities instead of clearing/remounting the center.
- The survey center displays an authored active question while the model answer
  is pending. Answer cards use question IDs as stable keys. Trajectory question
  counts now exclude lifecycle events, which render in a separate lifecycle
  section.
- Persona debrief rails use the durable `prompts.personaPrompt` verbatim when
  present; context and dimensions remain legacy-only fallbacks.

## TDD evidence

1. RED: focused Task 7 tests failed before implementation: batch created no
   job EventSource, `SurveyLive` was not exported, and its pending-question API
   was absent.
2. GREEN: focused stream/reducer/hook/UI suite passed after the shared stream
   hooks, monotonic merge, and survey/rail rendering changes.

## Verification

```text
npm test -- --run
17 test files passed, 82 tests passed

npm run typecheck
passed

npm run build
passed (existing Vite large-chunk warning only)

git diff --check
passed
```

## Commit scope

The pre-existing `application/playground/frontend/package-lock.json` change is
intentionally excluded.

## Fix round 1

- Removed the large-cohort aggregate status poller and route every cohort size
  through the one job EventSource + bootstrap snapshot path.
- Stream terminal `done`/`error` phases now immediately enrich displayed trial
  completion, success/error state, grid status, and batch counts before the
  terminal snapshot arrives.
- Batch grid cells are selectable; Survey batches retain selected live detail
  in the center and provide a Back to cohort control without clearing state.
- Trajectory pairing now uses authored `questionId`, tolerates interleaved
  lifecycle/retry events, and renders authored answered/total progress rather
  than counting raw event groups.
