// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/i18n/I18nProvider", () => ({ useI18n: () => ({ t: (key: string, values?: Record<string, unknown>) => key === "eval.survey.questionNumber" ? `Question ${values?.number}` : key }) }));

import { SurveyLive } from "../SurveyEvalCockpit";

const instrument = { id: "s", title: "Survey", questions: [{ id: "q1", prompt: "question one", type: "free_text", options: [] }, { id: "q2", prompt: "question two", type: "free_text", options: [] }] };
const completion = { numQuestions: 2, numAnswered: 1, answered: 1, total: 2, valid: true };

describe("SurveyLive", () => {
  it("keeps answered cards mounted and shows the authored pending question", () => {
    const { rerender } = render(<SurveyLive instrument={instrument} result={{ instrument, answers: [{ questionId: "q1", value: "answer one" }], completion, trajectory: [] }} activeQuestion={{ id: "q2", prompt: "question two", type: "free_text", index: 2, total: 2 }} phase="running" error={null} onRetry={vi.fn()} />);
    const first = screen.getByText("answer one").closest("div");
    expect(screen.getByText("question two")).toBeTruthy();
    rerender(<SurveyLive instrument={instrument} result={{ instrument, answers: [{ questionId: "q1", value: "answer one" }, { questionId: "q2", value: "answer two" }], completion: { ...completion, numAnswered: 2, answered: 2 }, trajectory: [] }} activeQuestion={null} phase="done" error={null} onRetry={vi.fn()} />);
    expect(screen.getByText("answer two")).toBeTruthy();
    expect(screen.getByText("answer one").closest("div")).toBe(first);
  });
});
