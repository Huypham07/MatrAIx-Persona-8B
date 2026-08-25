// @vitest-environment jsdom
import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { api } from "../api";
import { useHarborBatchLive } from "../useHarborBatchLive";

type Listener = (event: MessageEvent<string>) => void;

class FakeEventSource {
  static instances: FakeEventSource[] = [];
  listeners = new Map<string, Listener[]>();
  onerror: ((event: Event) => void) | null = null;
  closed = false;

  constructor(_url: string) { FakeEventSource.instances.push(this); }
  addEventListener(type: string, listener: Listener) { this.listeners.set(type, [...(this.listeners.get(type) ?? []), listener]); }
  removeEventListener(type: string, listener: Listener) { this.listeners.set(type, (this.listeners.get(type) ?? []).filter((item) => item !== listener)); }
  close() { this.closed = true; }
  emit(envelope: unknown) {
    for (const listener of this.listeners.get("trial") ?? []) {
      listener({ data: JSON.stringify(envelope), lastEventId: String((envelope as { id: number }).id) } as MessageEvent<string>);
    }
  }
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  FakeEventSource.instances = [];
});

describe("useHarborBatchLive", () => {
  it("subscribes once and retains unselected trial progress without polling", async () => {
    vi.stubGlobal("EventSource", FakeEventSource);
    const getLive = vi.spyOn(api, "getHarborJobLive").mockResolvedValue({
      jobName: "job", launchStatus: "running", trialCount: 2, completedTrials: 0,
      trials: [{ trialName: "a" }, { trialName: "b" }],
    });
    const { result, unmount } = renderHook(() => useHarborBatchLive("job"));
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));

    act(() => FakeEventSource.instances[0].emit({ id: 1, jobName: "job", trialName: "a", event: { type: "phase", phase: "persona_thinking" } }));
    act(() => FakeEventSource.instances[0].emit({ id: 2, jobName: "job", trialName: "b", event: { type: "survey_answer", questionId: "q1", value: 4, total: 2 } }));

    expect(result.current.liveByTrial.a.phase).toBe("persona_thinking");
    expect(result.current.liveByTrial.b.surveyResult?.answers).toHaveLength(1);
    act(() => FakeEventSource.instances[0].emit({ id: 3, jobName: "job", trialName: "a", event: { type: "done", status: "completed", completed: true, succeeded: true } }));
    await waitFor(() => expect(result.current.live?.trials.find((trial) => trial.trialName === "a")?.completed).toBe(true));
    await new Promise((resolve) => window.setTimeout(resolve, 20));
    expect(getLive).toHaveBeenCalledTimes(1);
    unmount();
    expect(FakeEventSource.instances[0].closed).toBe(true);
  });
});
