import { applyHarborTrialEvents, type HarborCockpitLiveState } from "./harborCockpitMappers";
import { harborJobEventsUrl } from "./api";
import type { HarborJobEventEnvelope, HarborJobStateEvent, HarborTrialEvent } from "./types";

export type { HarborJobEventEnvelope } from "./types";

export interface ConnectHarborJobEventsOptions {
  jobName: string;
  cursor?: number;
  onEnvelope: (envelope: HarborJobEventEnvelope) => void;
  onError: (error: Error) => void;
}

export interface HarborJobStreamState {
  liveByTrial: Record<string, HarborCockpitLiveState>;
  trialOrder: string[];
  seenEventIds: ReadonlySet<number>;
  cursor: number;
  launchStatus: string | null;
  terminalError: string | null;
}

export const EMPTY_HARBOR_JOB_STREAM_STATE: HarborJobStreamState = {
  liveByTrial: {},
  trialOrder: [],
  seenEventIds: new Set(),
  cursor: 0,
  launchStatus: null,
  terminalError: null,
};

const EMPTY_LIVE_STATE: HarborCockpitLiveState = {
  turns: [],
  draftTurn: null,
  phase: null,
  prompts: null,
};

export function connectHarborJobEvents(options: ConnectHarborJobEventsOptions): () => void {
  const cursor = Number.isInteger(options.cursor) && (options.cursor ?? 0) >= 0 ? options.cursor ?? 0 : 0;
  const source = new EventSource(harborJobEventsUrl(options.jobName, cursor));
  let closed = false;

  const receiveEnvelope = (raw: Event): void => {
    if (closed) return;
    const parsed = parseEnvelope(raw as MessageEvent<string>, options.jobName);
    if (parsed instanceof Error) {
      options.onError(parsed);
      return;
    }
    options.onEnvelope(parsed);
  };

  const receiveStreamError = (raw: Event): void => {
    if (closed) return;
    const message = parseStreamError(raw as MessageEvent<string>, options.jobName);
    options.onError(message);
  };

  const receiveTransportError = (): void => {
    if (!closed) {
      options.onError(
        new Error(
          "Harbor job event stream disconnected. Realtime updates may be delayed while it reconnects.",
        ),
      );
    }
  };

  source.addEventListener("trial", receiveEnvelope);
  source.addEventListener("job", receiveEnvelope);
  source.addEventListener("stream_error", receiveStreamError);
  source.onerror = receiveTransportError;

  return () => {
    if (closed) return;
    closed = true;
    source.removeEventListener("trial", receiveEnvelope);
    source.removeEventListener("job", receiveEnvelope);
    source.removeEventListener("stream_error", receiveStreamError);
    source.onerror = null;
    source.close();
  };
}

export function applyHarborJobEnvelope(
  previous: HarborJobStreamState,
  envelope: HarborJobEventEnvelope,
): HarborJobStreamState {
  // The server journal is strictly ordered. An unseen lower ID is stale replay,
  // so ignoring it is safer than applying an older state transition after newer UI.
  if (envelope.id <= previous.cursor || previous.seenEventIds.has(envelope.id)) return previous;

  const seenEventIds = new Set(previous.seenEventIds);
  seenEventIds.add(envelope.id);
  if (envelope.trialName === null && envelope.event.type === "job_state") {
    const event = envelope.event as HarborJobStateEvent;
    const launchStatus = jobStatus(event) ?? previous.launchStatus;
    const failed = launchStatus === "failed" || event.terminal === true && typeof event.error === "string";
    return {
      ...previous,
      seenEventIds,
      cursor: envelope.id,
      launchStatus,
      terminalError: failed ? event.error ?? "Harbor job failed." : null,
    };
  }

  if (envelope.trialName === null) {
    return { ...previous, seenEventIds, cursor: envelope.id };
  }

  const trialName = envelope.trialName;
  const current = previous.liveByTrial[trialName] ?? EMPTY_LIVE_STATE;
  const live = applyHarborTrialEvents([envelope.event as HarborTrialEvent], current);
  const knownTrial = Object.prototype.hasOwnProperty.call(previous.liveByTrial, trialName);
  return {
    ...previous,
    seenEventIds,
    cursor: envelope.id,
    liveByTrial: { ...previous.liveByTrial, [trialName]: live },
    trialOrder: knownTrial ? previous.trialOrder : [...previous.trialOrder, trialName],
  };
}

function parseEnvelope(raw: MessageEvent<string>, expectedJobName: string): HarborJobEventEnvelope | Error {
  const record = parseRecord(raw.data, "Malformed Harbor job event: invalid JSON payload.");
  if (record instanceof Error) return record;
  if (!Number.isInteger(record.id) || (record.id as number) <= 0) {
    return new Error("Malformed Harbor job event: id must be a positive integer.");
  }
  if (record.jobName !== expectedJobName) {
    return new Error("Malformed Harbor job event: jobName does not match this stream.");
  }
  if (typeof record.trialName !== "string" && record.trialName !== null) {
    return new Error("Malformed Harbor job event: trialName must be a string or null.");
  }
  if (!isEvent(record.event)) {
    return new Error("Malformed Harbor job event: event.type is required.");
  }
  return record as unknown as HarborJobEventEnvelope;
}

function parseStreamError(raw: MessageEvent<string>, expectedJobName: string): Error {
  const record = parseRecord(raw.data, "Malformed Harbor job stream error.");
  if (
    record instanceof Error ||
    record.jobName !== expectedJobName ||
    record.trialName !== null ||
    !isEvent(record.event) ||
    record.event.type !== "stream_error" ||
    typeof record.event.message !== "string" ||
    !record.event.message.trim()
  ) {
    return new Error("Malformed Harbor job stream error.");
  }
  return new Error(`Harbor job event stream failed: ${record.event.message}`);
}

function parseRecord(value: string, message: string): Record<string, unknown> | Error {
  try {
    const parsed: unknown = JSON.parse(value);
    return parsed !== null && typeof parsed === "object" && !Array.isArray(parsed)
      ? (parsed as Record<string, unknown>)
      : new Error(message);
  } catch {
    return new Error(message);
  }
}

function isEvent(value: unknown): value is Record<string, unknown> & { type: string } {
  return (
    value !== null &&
    typeof value === "object" &&
    !Array.isArray(value) &&
    typeof (value as Record<string, unknown>).type === "string" &&
    Boolean((value as Record<string, unknown>).type)
  );
}

function jobStatus(event: HarborJobStateEvent): string | null {
  if (typeof event.state === "string" && event.state) return event.state;
  return typeof event.status === "string" && event.status ? event.status : null;
}
