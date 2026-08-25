import { describe, expect, it } from "vitest";

import { setupFromPersonaStrategy } from "./cockpitPersonaSetupStorage";
import { readStrategySampling } from "./personaSamplingTypes";
import type { TaskPersonaStrategy } from "@/lib/types";

const strategy: TaskPersonaStrategy = {
  schemaVersion: "1.1",
  pool: "persona/datasets/task-eval-personas",
  segments: [
    {
      id: "careful",
      label: "Careful",
      hypothesis: "Will proceed carefully.",
      dimensions: { risk_tolerance: ["Cautious"] },
      personaIds: ["0001", "0002"],
    },
    {
      id: "premium",
      label: "Premium",
      hypothesis: "Will prioritize quality.",
      dimensions: { economic_motivation: ["Premium-seeking"] },
      personaIds: ["0003", "0004"],
    },
  ],
  sampling: { mode: "pinnedSegments", personasPerSegment: 2 },
};

describe("pinned task persona segments", () => {
  it("keeps pinnedSegments out of the manual sampling tabs", () => {
    expect(readStrategySampling(strategy)).toMatchObject({
      mode: "single",
      isPinnedSegments: true,
    });
  });

  it("selects all pinned personas in segment order immediately", () => {
    const setup = setupFromPersonaStrategy(strategy, "local/qwen3-14b");

    expect(setup.personaPool).toBe(
      "persona/datasets/task-eval-personas",
    );
    expect(setup.selectedPersonaIds).toEqual(["0001", "0002", "0003", "0004"]);
    expect(setup.selectedCount).toBe(4);
    expect(setup.useTaskDefaultStrategy).toBe(true);
  });
});
