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

  listenerCount(): number {
    return [...this.listeners.values()].flat().length;
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
      event: { type: "job_state", state: "running", terminal: false },
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

  it("rejects cross-channel and mismatched SSE-ID payloads without dispatching them", () => {
    vi.stubGlobal("EventSource", FakeEventSource);
    const received: HarborJobEventEnvelope[] = [];
    const onError = vi.fn();
    connectHarborJobEvents({
      jobName: "job",
      onEnvelope: (envelope) => received.push(envelope),
      onError,
    });
    const source = FakeEventSource.instances[0];

    source.emit("job", {
      id: 1,
      jobName: "job",
      trialName: "a",
      event: { type: "job_state", state: "running", terminal: false },
    }, "1");
    source.emit("trial", {
      id: 2,
      jobName: "job",
      trialName: null,
      event: { type: "phase", phase: "running" },
    }, "2");
    source.emit("trial", {
      id: 3,
      jobName: "job",
      trialName: "a",
      event: { type: "job_state", state: "running", terminal: false },
    }, "3");
    source.emit("trial", {
      id: 4,
      jobName: "job",
      trialName: "a",
      event: { type: "phase", phase: "running" },
    }, "99");
    source.emit("trial", {
      id: 5,
      jobName: "job",
      trialName: "a",
      event: { type: "phase", phase: "running" },
    }, "5");

    expect(onError).toHaveBeenCalledTimes(4);
    expect(received.map((event) => event.id)).toEqual([5]);
  });

  it("closes after a server stream error and prevents later callbacks", () => {
    vi.stubGlobal("EventSource", FakeEventSource);
    const onEnvelope = vi.fn();
    const onError = vi.fn();
    connectHarborJobEvents({ jobName: "job", onEnvelope, onError });
    const source = FakeEventSource.instances[0];

    source.emit("stream_error", {
      jobName: "job",
      trialName: null,
      event: { type: "stream_error", message: "journal read failed" },
    });
    source.onerror?.(new Event("error"));
    source.emit("trial", {
      id: 7,
      jobName: "job",
      trialName: "a",
      event: { type: "phase", phase: "running" },
    });

    expect(onError.mock.calls.map(([error]) => (error as Error).message)).toEqual([
      "Harbor job event stream failed: journal read failed",
    ]);
    expect(source.closed).toBe(true);
    expect(source.listenerCount()).toBe(0);
    expect(onEnvelope).not.toHaveBeenCalled();
  });

  it("reports one transport outage until a valid envelope proves recovery", () => {
    vi.stubGlobal("EventSource", FakeEventSource);
    const onError = vi.fn();
    connectHarborJobEvents({ jobName: "job", onEnvelope: vi.fn(), onError });
    const source = FakeEventSource.instances[0];

    source.onerror?.(new Event("error"));
    source.onerror?.(new Event("error"));
    source.emit("trial", {
      id: 8,
      jobName: "job",
      trialName: "a",
      event: { type: "phase", phase: "running" },
    }, "8");
    source.onerror?.(new Event("error"));

    expect(onError.mock.calls.map(([error]) => (error as Error).message)).toEqual([
      "Harbor job event stream disconnected. Realtime updates may be delayed while it reconnects.",
      "Harbor job event stream disconnected. Realtime updates may be delayed while it reconnects.",
    ]);
  });
});
