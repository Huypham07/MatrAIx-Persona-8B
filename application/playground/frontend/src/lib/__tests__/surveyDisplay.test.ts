import { describe, expect, it } from "vitest";

import { groupSurveyTrajectory } from "../surveyDisplay";

describe("groupSurveyTrajectory", () => {
  it("pairs question events by authored id across lifecycle and retry events", () => {
    const groups = groupSurveyTrajectory([
      { actor: "system", action: "survey_started" },
      { actor: "assistant", action: "ask_question", context: { questionId: "q1" } },
      { actor: "system", action: "application_retry" },
      { actor: "assistant", action: "ask_question", context: { questionId: "q2" } },
      { actor: "user", action: "answer_question", context: { questionId: "q1" } },
      { actor: "user", action: "answer_question", context: { questionId: "q2" } },
      { actor: "system", action: "survey_completed" },
    ]);
    expect(groups.filter((group) => group.kind === "qa")).toHaveLength(2);
    expect(groups.filter((group) => group.kind === "event").map((group) => group.event.action)).toEqual([
      "survey_started", "application_retry", "survey_completed",
    ]);
  });
});
