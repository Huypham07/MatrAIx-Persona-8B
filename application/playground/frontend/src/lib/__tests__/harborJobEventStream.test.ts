import { afterEach, describe, expect, it, vi } from "vitest";

import {
  connectHarborJobEvents,
  type HarborJobEventEnvelope,
} from "../harborJobEventStream";

type Listener = (event: MessageEvent<string>) => void;

class FakeEventSource {
  static instances: FakeEventSource[] = [];

  readonly listeners = new Map<string, Listener[]>();
  readonly url: string;
  closed = false;
  onerror: ((event: Event) => void) | null = null;

  constructor(url: string) {
    this.url = url;
    FakeEventSource.instances.push(this);
  }

  addEventListener(type: string, listener: Listener): void {
    this.listeners.set(type, [...(this.listeners.get(type) ?? []), listener]);
  }

  removeEventListener(type: string, listener: Listener): void {
    this.listeners.set(type, (this.listeners.get(type) ?? []).filter((item) => item !== listener));
  }

  close(): void {
    this.closed = true;
  }

  emit(type: string, data: unknown, lastEventId = ""): void {
    for (const listener of this.listeners.get(type) ?? []) {
      listener({ data: JSON.stringify(data), lastEventId } as MessageEvent<string>);
    }
  }

  emitRaw(type: string, data: string, lastEventId = ""): void {
    for (const listener of this.listeners.get(type) ?? []) {
      listener({ data, lastEventId } as MessageEvent<string>);
    }
  }
}

afterEach(() => {
  FakeEventSource.instances = [];
  vi.unstubAllGlobals();
});

describe("connectHarborJobEvents", () => {
  it("encodes the job cursor, delivers a valid envelope, and closes idempotently", () => {
    vi.stubGlobal("EventSource", FakeEventSource);
    const received: HarborJobEventEnvelope[] = [];
    const onError = vi.fn();

    const close = connectHarborJobEvents({
      jobName: "job / one",
      cursor: 7,
      onEnvelope: (envelope) => received.push(envelope),
      onError,
    });
    const source = FakeEventSource.instances[0];
    source.emit(
      "trial",
      {
        id: 19,
        jobName: "job / one",
        trialName: "a",
        event: { type: "phase", phase: "running" },
      },
      "19",
    );

    expect(source.url).toBe("/api/harbor/jobs/job%20%2F%20one/events?cursor=7");
    expect(received).toEqual([
      {
        id: 19,
        jobName: "job / one",
        trialName: "a",
        event: { type: "phase", phase: "running" },
      },
    ]);
    expect(onError).not.toHaveBeenCalled();

    close();
    close();
    expect(source.closed).toBe(true);
  });

  it("reports malformed envelopes without preventing later valid events", () => {
    vi.stubGlobal("EventSource", FakeEventSource);
    const received: HarborJobEventEnvelope[] = [];
    const onError = vi.fn();
    connectHarborJobEvents({
      jobName: "job",
      onEnvelope: (envelope) => received.push(envelope),
      onError,
    });
    const source = FakeEventSource.instances[0];

    source.emitRaw("trial", "not-json");
    source.emit("trial", {
      id: 0,
      jobName: "job",
      trialName: "a",
      event: { type: "phase" },
    });
    source.emit("job", {
      id: 5,
      jobName: "other-job",
      trialName: null,
      event: { type: "job_state", state: "running" },
    });
    source.emit("job", {
      id: 6,
      jobName: "job",
      trialName: null,
      event: { type: "job_state", state: "running" },
    });

    expect(onError).toHaveBeenCalledTimes(3);
    expect(onError.mock.calls.map(([error]) => (error as Error).message)).toEqual([
      "Malformed Harbor job event: invalid JSON payload.",
      "Malformed Harbor job event: id must be a positive integer.",
      "Malformed Harbor job event: jobName does not match this stream.",
    ]);
    expect(received).toHaveLength(1);
    expect(received[0].id).toBe(6);
  });

  it("distinguishes a server stream error envelope from a transport disconnect", () => {
    vi.stubGlobal("EventSource", FakeEventSource);
    const onError = vi.fn();
    connectHarborJobEvents({ jobName: "job", onEnvelope: vi.fn(), onError });
    const source = FakeEventSource.instances[0];

    source.emit("stream_error", {
      jobName: "job",
      trialName: null,
      event: { type: "stream_error", message: "journal read failed" },
    });
    source.onerror?.(new Event("error"));

    expect(onError.mock.calls.map(([error]) => (error as Error).message)).toEqual([
      "Harbor job event stream failed: journal read failed",
      "Harbor job event stream disconnected. Realtime updates may be delayed while it reconnects.",
    ]);
  });
});
