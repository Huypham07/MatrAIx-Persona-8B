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
  let transportErrorReported = false;

  const close = (): void => {
    if (closed) return;
    closed = true;
    source.removeEventListener("trial", receiveTrialEnvelope);
    source.removeEventListener("job", receiveJobEnvelope);
    source.removeEventListener("stream_error", receiveStreamError);
    source.onerror = null;
    source.close();
  };

  const receiveEnvelope = (channel: "job" | "trial", raw: Event): void => {
    if (closed) return;
    const parsed = parseEnvelope(raw as MessageEvent<string>, options.jobName, channel);
    if (parsed instanceof Error) {
      options.onError(parsed);
      return;
    }
    transportErrorReported = false;
    options.onEnvelope(parsed);
    if (
      channel === "job"
      && parsed.trialName === null
      && parsed.event.type === "job_state"
      && (parsed.event as HarborJobStateEvent).terminal === true
    ) {
      close();
    }
  };

  const receiveTrialEnvelope = (raw: Event): void => receiveEnvelope("trial", raw);
  const receiveJobEnvelope = (raw: Event): void => receiveEnvelope("job", raw);

  const receiveStreamError = (raw: Event): void => {
    if (closed) return;
    const message = parseStreamError(raw as MessageEvent<string>, options.jobName);
    options.onError(message);
    close();
  };

  const receiveTransportError = (): void => {
    if (!closed && !transportErrorReported) {
      transportErrorReported = true;
      options.onError(
        new Error(
          "Harbor job event stream disconnected. Realtime updates may be delayed while it reconnects.",
        ),
      );
    }
  };

  source.addEventListener("trial", receiveTrialEnvelope);
  source.addEventListener("job", receiveJobEnvelope);
  source.addEventListener("stream_error", receiveStreamError);
  source.onerror = receiveTransportError;

  return close;
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
    const failed = isFailedTerminalJobState(event, launchStatus);
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

function parseEnvelope(
  raw: MessageEvent<string>,
  expectedJobName: string,
  channel: "job" | "trial",
): HarborJobEventEnvelope | Error {
  const record = parseRecord(raw.data, "Malformed Harbor job event: invalid JSON payload.");
  if (record instanceof Error) return record;
  if (!Number.isSafeInteger(record.id) || (record.id as number) <= 0) {
    return new Error("Malformed Harbor job event: id must be a positive integer.");
  }
  if (raw.lastEventId) {
    const lastEventId = Number(raw.lastEventId);
    if (!Number.isSafeInteger(lastEventId) || lastEventId <= 0 || lastEventId !== record.id) {
      return new Error("Malformed Harbor job event: SSE lastEventId does not match envelope.id.");
    }
  }
  if (record.jobName !== expectedJobName) {
    return new Error("Malformed Harbor job event: jobName does not match this stream.");
  }
  if (!isEvent(record.event)) {
    return new Error("Malformed Harbor job event: event.type is required.");
  }
  if (channel === "job") {
    if (record.trialName !== null) {
      return new Error("Malformed Harbor job event: job events require trialName null.");
    }
    if (!isJobStateEvent(record.event)) {
      return new Error("Malformed Harbor job event: job events require a valid job_state payload.");
    }
  } else {
    if (typeof record.trialName !== "string" || !record.trialName.trim()) {
      return new Error("Malformed Harbor job event: trial events require a nonempty trialName.");
    }
    if (!isTrialEvent(record.event)) {
      return new Error("Malformed Harbor job event: unsupported or incomplete trial event.");
    }
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

function isJobStateEvent(event: Record<string, unknown> & { type: string }): boolean {
  if (event.type !== "job_state") return false;
  const state = typeof event.state === "string" ? event.state : event.status;
  if (typeof state !== "string" || !state.trim() || typeof event.terminal !== "boolean") return false;
  return !Object.prototype.hasOwnProperty.call(event, "error") || event.error === null || typeof event.error === "string";
}

function isTrialEvent(event: Record<string, unknown> & { type: string }): boolean {
  switch (event.type) {
    case "phase":
      return nonemptyString(event.phase);
    case "stage":
      return nonemptyString(event.stage);
    case "prompts":
      return isRecord(event.prompts);
    case "instruction":
      return typeof event.markdown === "string";
    case "user_message":
      return positiveInteger(event.turnIndex) && typeof event.message === "string";
    case "assistant_message":
      return positiveInteger(event.turnIndex) && typeof event.assistantMessage === "string";
    case "turn":
      return isRecord(event.turn);
    case "survey_question_started":
      return (
        nonemptyString(event.questionId) &&
        typeof event.prompt === "string" &&
        nonemptyString(event.questionType) &&
        positiveInteger(event.questionIndex) &&
        positiveInteger(event.numQuestions)
      );
    case "survey_answer":
      return nonemptyString(event.questionId) && Object.prototype.hasOwnProperty.call(event, "value");
    case "survey_progress":
      return isRecord(event.result);
    case "done":
      return (
        nonemptyString(event.status) &&
        typeof event.completed === "boolean" &&
        typeof event.succeeded === "boolean" &&
        (!Object.prototype.hasOwnProperty.call(event, "result") || isRecord(event.result))
      );
    case "application_retry":
    case "application_error":
      return positiveInteger(event.attempt) && positiveInteger(event.maxAttempts) && nonemptyString(event.cause);
    case "error":
      return nonemptyString(event.cause);
    case "thought":
      return positiveInteger(event.step) && typeof event.thought === "string";
    default:
      return false;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function nonemptyString(value: unknown): value is string {
  return typeof value === "string" && Boolean(value.trim());
}

function positiveInteger(value: unknown): boolean {
  return typeof value === "number" && Number.isSafeInteger(value) && value > 0;
}

function jobStatus(event: HarborJobStateEvent): string | null {
  if (typeof event.state === "string" && event.state) return event.state;
  return typeof event.status === "string" && event.status ? event.status : null;
}

function isFailedTerminalJobState(event: HarborJobStateEvent, status: string | null): boolean {
  if (event.terminal !== true || !status) return false;
  const normalized = status.toLowerCase();
  return normalized === "failed" || normalized === "error";
}
