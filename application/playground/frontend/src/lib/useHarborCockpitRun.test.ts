import { describe, expect, it } from "vitest";

import { singleHarborLaunchBody, type HarborCockpitRunInput } from "./useHarborCockpitRun";

describe("single Harbor cockpit launch", () => {
  it("forwards the selected persona pool with the persona id", () => {
    const input: HarborCockpitRunInput<unknown> = {
      taskPath: "application/tasks/survey_price-sensitivity-hasbro-gaming-candy-land",
      personaId: "0593",
      personaPool: "persona/datasets/task-eval-personas",
      personaModel: "local/qwen3-14b",
      mapDebrief: () => null,
    };

    expect(singleHarborLaunchBody(input)).toMatchObject({
      personaPool: "persona/datasets/task-eval-personas",
      personaIds: ["0593"],
      sampleSize: 1,
    });
  });
});
