import { describe, expect, it } from "vitest";

import {
  EMPTY_HARBOR_JOB_STREAM_STATE,
  applyHarborJobEnvelope,
} from "../harborJobEventStream";
import { applyHarborTrialEvents } from "../harborCockpitMappers";

describe("applyHarborJobEnvelope", () => {
  it("keeps all trials, advances the cursor, and ignores duplicate or stale replay", () => {
    let state = EMPTY_HARBOR_JOB_STREAM_STATE;
    state = applyHarborJobEnvelope(state, {
      id: 10,
      jobName: "job",
      trialName: "a",
      event: { type: "user_message", turnIndex: 1, message: "hello" },
    });
    const afterFirst = state;
    state = applyHarborJobEnvelope(state, {
      id: 10,
      jobName: "job",
      trialName: "a",
      event: { type: "user_message", turnIndex: 1, message: "hello" },
    });
    expect(state).toBe(afterFirst);

    state = applyHarborJobEnvelope(state, {
      id: 20,
      jobName: "job",
      trialName: "b",
      event: { type: "survey_answer", questionId: "q1", value: 4, total: 2 },
    });
    const afterSecond = state;
    state = applyHarborJobEnvelope(state, {
      id: 15,
      jobName: "job",
      trialName: "late",
      event: { type: "phase", phase: "running" },
    });

    expect(state).toBe(afterSecond);
    expect(state.cursor).toBe(20);
    expect([...state.seenEventIds]).toEqual([10, 20]);
    expect(state.trialOrder).toEqual(["a", "b"]);
    expect(Object.keys(state.liveByTrial)).toEqual(["a", "b"]);
  });

  it("tracks only job launch status and terminal error from job events", () => {
    let state = EMPTY_HARBOR_JOB_STREAM_STATE;
    state = applyHarborJobEnvelope(state, {
      id: 1,
      jobName: "job",
      trialName: null,
      event: { type: "job_state", state: "running" },
    });
    state = applyHarborJobEnvelope(state, {
      id: 2,
      jobName: "job",
      trialName: null,
      event: { type: "job_state", state: "failed", terminal: true, error: "provider unavailable" },
    });

    expect(state.launchStatus).toBe("failed");
    expect(state.terminalError).toBe("provider unavailable");
    expect(state.liveByTrial).toEqual({});
  });

  it("does not retain a stray completed-job error as a terminal failure", () => {
    const state = applyHarborJobEnvelope(EMPTY_HARBOR_JOB_STREAM_STATE, {
      id: 1,
      jobName: "job",
      trialName: null,
      event: {
        type: "job_state",
        state: "completed",
        terminal: true,
        error: "already recovered",
      },
    });

    expect(state.launchStatus).toBe("completed");
    expect(state.terminalError).toBeNull();
  });
});

describe("applyHarborTrialEvents", () => {
  it("derives survey progress from the authored started and answer totals", () => {
    const started = applyHarborTrialEvents(
      [
        {
          type: "survey_question_started",
          questionId: "q1",
          prompt: "How was it?",
          questionType: "likert",
          questionIndex: 1,
          numQuestions: 2,
        },
      ],
      { turns: [], draftTurn: null, phase: null, prompts: null },
    );

    expect(started.activeSurveyQuestion).toEqual({
      id: "q1",
      prompt: "How was it?",
      type: "likert",
      index: 1,
      total: 2,
    });
    const state = applyHarborTrialEvents(
      [{ type: "survey_answer", questionId: "q1", value: 4, total: 2 }],
      started,
    );
    expect(state.surveyResult?.completion).toMatchObject({
      numAnswered: 1,
      numQuestions: 2,
      answered: 1,
      total: 2,
    });
  });

  it("maps durable terminal done events without an embedded result", () => {
    const pending = {
      turns: [],
      draftTurn: { turnIndex: 1, userMessage: "hello", assistantMessage: "" },
      activeSurveyQuestion: { id: "q1", prompt: "How was it?", type: "likert", index: 1, total: 2 },
      phase: "survey_answering",
      prompts: null,
    };
    const completed = applyHarborTrialEvents(
      [
        {
          type: "done",
          status: "completed",
          completed: true,
          succeeded: true,
        } as Parameters<typeof applyHarborTrialEvents>[0][number],
      ],
      pending,
    );
    const failed = applyHarborTrialEvents(
      [
        {
          type: "done",
          status: "failed",
          completed: false,
          succeeded: false,
        } as Parameters<typeof applyHarborTrialEvents>[0][number],
      ],
      pending,
    );

    expect(completed).toMatchObject({ phase: "done", draftTurn: null, activeSurveyQuestion: null });
    expect(failed).toMatchObject({ phase: "error", draftTurn: null, activeSurveyQuestion: null });
  });
});
