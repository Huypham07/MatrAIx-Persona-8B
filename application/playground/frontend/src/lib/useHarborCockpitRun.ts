import { useCallback, useEffect, useRef, useState } from "react";

import { api, ApiError } from "./api";
import {
  createHarborCockpitRestoreMappers,
  harborTrialErrorFromResult,
  isRewardOnlyTrialFailure,
  mergeHarborCockpitJob,
  type HarborCockpitLiveState,
  type HarborCockpitTaskKind,
} from "./harborCockpitMappers";
import {
  EMPTY_HARBOR_JOB_STREAM_STATE,
  applyHarborJobEnvelope,
  connectHarborJobEvents,
} from "./harborJobEventStream";
import type { PlaygroundResult } from "./types";
import { useUrlState } from "./useUrlState";

export type HarborLaunchMode = "auto" | "force_docker" | "smoke";
export type HarborCockpitPhase = "idle" | "launching" | "running" | "done" | "error" | "timeout";

export interface HarborCockpitRunInput<TJob> {
  taskPath: string;
  personaId: string;
  personaPool: string;
  personaModel: string;
  mode?: HarborLaunchMode;
  chatDomain?: string;
  chatApplicationId?: string;
  chatApplicationContext?: string;
  chatMaxTurns?: number | null;
  osAppSubmissionProfile?: string;
  agentName?: string;
  osAppBackend?: string;
  mapDebrief: (debrief: PlaygroundResult, ctx: { jobName: string; trialName: string }) => TJob;
  mapLive?: (live: HarborCockpitLiveState, ctx: { jobName: string; trialName: string }) => TJob;
}

export interface UseHarborCockpitRunOptions {
  taskKind: HarborCockpitTaskKind;
}

export function singleHarborLaunchBody<TJob>(input: HarborCockpitRunInput<TJob>) {
  return {
    taskPath: input.taskPath,
    sampleSize: 1,
    personaPool: input.personaPool,
    personaIds: [input.personaId],
    personaModel: input.personaModel,
    agentName: input.agentName,
    nConcurrentTrials: 1,
    mode: input.mode ?? ("auto" as const),
    chatDomain: input.chatDomain,
    chatApplicationId: input.chatApplicationId,
    chatApplicationContext: input.chatApplicationContext,
    chatMaxTurns: input.chatMaxTurns,
    osAppSubmissionProfile: input.osAppSubmissionProfile,
    osAppBackend: input.osAppBackend,
  };
}

const TIMEOUT_MS = 30 * 60 * 1_000;

const EMPTY_LIVE: HarborCockpitLiveState = {
  turns: [],
  draftTurn: null,
  phase: null,
  prompts: null,
};

function normalizeTaskKind(value: unknown): HarborCockpitTaskKind | null {
  if (value === "chatbot" || value === "survey" || value === "web" || value === "os-app") {
    return value;
  }
  if (value === "cua") return "os-app";
  return null;
}

export function useHarborCockpitRun<TJob>(options: UseHarborCockpitRunOptions) {
  const { taskKind } = options;
  const { state: urlState, setState: setUrlState } = useUrlState();

  const [job, setJob] = useState<TJob | null>(null);
  const [harborJobName, setHarborJobName] = useState<string | null>(null);
  const [harborTrialName, setHarborTrialName] = useState<string | null>(null);
  const [phase, setPhase] = useState<HarborCockpitPhase>("idle");
  const [error, setError] = useState<string | null>(null);
  const [harborPhase, setHarborPhase] = useState<string | null>(null);
  const [vncUrl, setVncUrl] = useState<string | null>(null);
  const [sandboxId, setSandboxId] = useState<string | null>(null);
  const lastInput = useRef<HarborCockpitRunInput<TJob> | null>(null);
  const startedAt = useRef(0);
  const liveStateRef = useRef<HarborCockpitLiveState>(EMPTY_LIVE);
  const streamStateRef = useRef(EMPTY_HARBOR_JOB_STREAM_STATE);
  const cursorRef = useRef(0);
  const terminalReconciledRef = useRef(false);
  const restoreAttemptedRef = useRef(false);

  const clearCockpitUrl = useCallback(() => {
    setUrlState({ cockpitJob: null, cockpitTrial: null });
  }, [setUrlState]);

  const reset = useCallback(() => {
    setJob(null);
    setHarborJobName(null);
    setHarborTrialName(null);
    setPhase("idle");
    setError(null);
    setHarborPhase(null);
    setVncUrl(null);
    setSandboxId(null);
    liveStateRef.current = EMPTY_LIVE;
    streamStateRef.current = EMPTY_HARBOR_JOB_STREAM_STATE;
    cursorRef.current = 0;
    terminalReconciledRef.current = false;
    clearCockpitUrl();
  }, [clearCockpitUrl]);

  const finishFromDebrief = useCallback(
    async (input: HarborCockpitRunInput<TJob>, jobName: string, resolvedTrial: string) => {
      setHarborTrialName(resolvedTrial);
      setUrlState({ cockpitJob: jobName, cockpitTrial: resolvedTrial, cockpitBatch: null });
      setHarborPhase("collecting");
      const jobDetail = await api.getHarborJob(jobName);
      const finishedTrial = jobDetail.trials.find((trial) => trial.trialName === resolvedTrial);
      const trialError =
        (typeof finishedTrial?.error === "string" && finishedTrial.error) ||
        harborTrialErrorFromResult(finishedTrial?.result ?? null);
      const debrief = await api.getHarborTrialDebrief(jobName, resolvedTrial);
      const ctx = { jobName, trialName: resolvedTrial };
      let mapped = input.mapDebrief(debrief, ctx);
      mapped = mergeHarborCockpitJob(mapped, liveStateRef.current, input, ctx);
      const mappedRecord = mapped as Record<string, unknown>;
      const recoveredFromLive =
        Boolean((mappedRecord.surveyResult as { answers?: unknown[] } | null)?.answers?.length) ||
        Boolean((mappedRecord.turns as unknown[] | undefined)?.length) ||
        Boolean(mappedRecord.webResult) ||
        Boolean(
          ((mappedRecord.trace as { events?: unknown[] } | null)?.events?.length ??
            (debrief.webTrace as { events?: unknown[] } | null)?.events?.length) ??
            0,
        ) ||
        Boolean(mappedRecord.osAppResult);
      if (recoveredFromLive) {
        mapped = { ...mapped, status: "done", error: null } as TJob;
      }
      setJob(mapped);
      const rewardOnlyFailure = isRewardOnlyTrialFailure(trialError, debrief);
      if (trialError || (mapped as { status?: string; error?: string | null }).status === "error") {
        if (rewardOnlyFailure) {
          setPhase("done");
          setHarborPhase(null);
          return;
        }
        setError(
          trialError ||
            (mapped as { error?: string | null }).error ||
            "Trial failed.",
        );
        setPhase("error");
        setHarborPhase(null);
        return;
      }
      setPhase("done");
      setHarborPhase(null);
    },
    [setUrlState],
  );

  const run = useCallback(
    async (input: HarborCockpitRunInput<TJob>) => {
      lastInput.current = input;
      startedAt.current = Date.now();
      liveStateRef.current = EMPTY_LIVE;
      streamStateRef.current = EMPTY_HARBOR_JOB_STREAM_STATE;
      cursorRef.current = 0;
      terminalReconciledRef.current = false;
      setJob(null);
      setError(null);
      setHarborJobName(null);
      setHarborTrialName(null);
      setHarborPhase("launching");
      setPhase("launching");
      try {
        const launched = await api.launchHarborJob(singleHarborLaunchBody(input));
        setHarborJobName(launched.jobName);
        setUrlState({
          pgTask: taskKind,
          cockpitJob: launched.jobName,
          cockpitTrial: null,
          cockpitBatch: null,
        });
        setPhase("running");
        setHarborPhase("harbor_running");
      } catch (exc) {
        const message = exc instanceof ApiError ? exc.message : exc instanceof Error ? exc.message : String(exc);
        setError(message);
        setPhase(message.includes("longer than expected") ? "timeout" : "error");
        clearCockpitUrl();
      }
    },
    [clearCockpitUrl, setUrlState, taskKind],
  );

  // Restore a single-run job after refresh (only for this cockpit task tab).
  useEffect(() => {
    if (restoreAttemptedRef.current) return;
    const jobName = urlState.cockpitJob;
    if (urlState.cockpitBatch || !jobName || phase !== "idle") return;
    if (typeof window !== "undefined") {
      const params = new URLSearchParams(window.location.search);
      if (!params.get("cockpitJob")) {
        restoreAttemptedRef.current = true;
        return;
      }
    }
    if (urlState.pgTask && urlState.pgTask !== taskKind) {
      return;
    }

    let cancelled = false;
    const restoreMappers = createHarborCockpitRestoreMappers(taskKind);
    const restoreInput = {
      taskPath: "",
      personaId: "",
      personaPool: "",
      personaModel: "",
      mapDebrief: restoreMappers.mapDebrief as HarborCockpitRunInput<TJob>["mapDebrief"],
      mapLive: restoreMappers.mapLive as HarborCockpitRunInput<TJob>["mapLive"],
    };

    void (async () => {
      try {
        const jobDetail = await api.getHarborJob(jobName);
        if (cancelled) return;

        const completed = jobDetail.trials.find((trial) => trial.completed);
        const active = jobDetail.trials.find((trial) => !trial.completed) ?? jobDetail.trials[0];
        const resolvedTrial =
          urlState.cockpitTrial ?? completed?.trialName ?? active?.trialName ?? null;

        if (completed && resolvedTrial) {
          const debrief = await api.getHarborTrialDebrief(jobName, resolvedTrial);
          if (cancelled) return;
          const actualTaskKind = normalizeTaskKind(debrief.applicationType);
          if (actualTaskKind && actualTaskKind !== taskKind) {
            setUrlState({ pgTask: actualTaskKind });
            return;
          }
        }

        if (!urlState.pgTask) {
          if (!completed || !resolvedTrial) {
            restoreAttemptedRef.current = true;
            return;
          }
          const debrief = await api.getHarborTrialDebrief(jobName, resolvedTrial);
          if (cancelled) return;
          const actualTaskKind = normalizeTaskKind(debrief.applicationType);
          if (actualTaskKind && actualTaskKind !== taskKind) {
            setUrlState({ pgTask: actualTaskKind });
            return;
          }
          if (!actualTaskKind && debrief.applicationType !== taskKind) {
            restoreAttemptedRef.current = true;
            return;
          }
          setUrlState({ pgTask: taskKind });
        }

        restoreAttemptedRef.current = true;
        lastInput.current = restoreInput;
        startedAt.current = Date.now();
        liveStateRef.current = EMPTY_LIVE;
        streamStateRef.current = EMPTY_HARBOR_JOB_STREAM_STATE;
        cursorRef.current = 0;
        terminalReconciledRef.current = false;
        setHarborJobName(jobName);

        if (jobDetail.launch?.status === "failed") {
          setError(jobDetail.launch.error ?? "Batch run failed.");
          setPhase("error");
          return;
        }

        if (completed && resolvedTrial) {
          await finishFromDebrief(restoreInput, jobName, resolvedTrial);
          return;
        }

        if (resolvedTrial) {
          setHarborTrialName(resolvedTrial);
          setUrlState({ cockpitTrial: resolvedTrial });
        }
        setPhase("running");
        setHarborPhase("harbor_running");
      } catch (exc) {
        if (cancelled) return;
        restoreAttemptedRef.current = true;
        const message = exc instanceof ApiError ? exc.message : exc instanceof Error ? exc.message : String(exc);
        setError(message);
        setPhase("error");
        clearCockpitUrl();
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [
    clearCockpitUrl,
    finishFromDebrief,
    phase,
    setUrlState,
    taskKind,
    urlState.cockpitBatch,
    urlState.cockpitJob,
    urlState.cockpitTrial,
    urlState.pgTask,
  ]);

  useEffect(() => {
    if (phase !== "running" || !harborJobName || !lastInput.current) return;

    const input = lastInput.current;
    let cancelled = false;
    let resolvedTrial = harborTrialName;
    const reconcileTerminal = async () => {
      if (terminalReconciledRef.current || cancelled) return;
      terminalReconciledRef.current = true;
      try {
        if (!resolvedTrial) {
          setError("Run finished without producing a trial.");
          setPhase("error");
          return;
        }
        await finishFromDebrief(input, harborJobName, resolvedTrial);
      } catch (exc) {
        if (!cancelled) {
          setError(exc instanceof Error ? exc.message : String(exc));
          setPhase("error");
        }
      }
    };

    const close = connectHarborJobEvents({
      jobName: harborJobName,
      cursor: cursorRef.current,
      onEnvelope: (envelope) => {
        cursorRef.current = envelope.id;
        const next = applyHarborJobEnvelope(streamStateRef.current, envelope);
        streamStateRef.current = next;
        if (envelope.trialName) {
          resolvedTrial = envelope.trialName;
          setHarborTrialName(envelope.trialName);
          setUrlState({ cockpitTrial: envelope.trialName });
          liveStateRef.current = next.liveByTrial[envelope.trialName] ?? liveStateRef.current;
          setHarborPhase(liveStateRef.current.phase ?? "trial_running");
          if (input.mapLive) setJob(input.mapLive(liveStateRef.current, { jobName: harborJobName, trialName: envelope.trialName }));
        }
        if (envelope.trialName === null && envelope.event.type === "job_state") {
          const jobPhase = typeof envelope.event.state === "string"
            ? envelope.event.state
            : typeof envelope.event.status === "string"
              ? envelope.event.status
              : "harbor_running";
          setHarborPhase(jobPhase);
          if (envelope.event.terminal) void reconcileTerminal();
        }
      },
      onError: (cause) => {
        if (!cancelled) setError(`Realtime updates degraded: ${cause.message}`);
      },
    });
    // A single bootstrap identifies an already-created trial after refresh or
    // a slow worker start; it never drives rendering after the stream begins.
    void (async () => {
      try {
        const detail = await api.getHarborJob(harborJobName);
        if (cancelled) return;
        const active = detail.trials.find((trial) => !trial.completed) ?? detail.trials[0];
        if (!active || resolvedTrial) return;
        resolvedTrial = active.trialName;
        setHarborTrialName(active.trialName);
        setUrlState({ cockpitTrial: active.trialName });
      } catch (cause) {
        if (!cancelled) setError(`Realtime updates degraded: ${cause instanceof Error ? cause.message : String(cause)}`);
      }
    })();
    const timeout = window.setTimeout(() => {
      if (!cancelled && Date.now() - startedAt.current >= TIMEOUT_MS) {
        setError("This run is taking longer than expected.");
        setPhase("timeout");
      }
    }, TIMEOUT_MS);
    return () => {
      cancelled = true;
      window.clearTimeout(timeout);
      close();
    };
  }, [finishFromDebrief, harborJobName, phase, setUrlState]);

  const retry = useCallback(() => {
    if (lastInput.current) void run(lastInput.current);
  }, [run]);

  const [cancelBusy, setCancelBusy] = useState(false);

  const cancelRun = useCallback(async () => {
    if (cancelBusy) return;
    const jobName = harborJobName;
    if (!jobName || (phase !== "launching" && phase !== "running")) return;
    setCancelBusy(true);
    try {
      await api.deleteHarborJob(jobName);
    } finally {
      setCancelBusy(false);
      // Stay locked until Reset — same end-state as a failed/finished run.
      setJob(null);
      setHarborJobName(null);
      setHarborTrialName(null);
      setHarborPhase(null);
      setVncUrl(null);
      setSandboxId(null);
      liveStateRef.current = EMPTY_LIVE;
      streamStateRef.current = EMPTY_HARBOR_JOB_STREAM_STATE;
      cursorRef.current = 0;
      terminalReconciledRef.current = false;
      clearCockpitUrl();
      setPhase("error");
      setError("Run stopped. Reset to change setup and launch again.");
    }
  }, [cancelBusy, clearCockpitUrl, harborJobName, phase]);

  return {
    run,
    job,
    harborJobName,
    harborTrialName,
    harborPhase,
    vncUrl,
    sandboxId,
    phase,
    error,
    timedOut: phase === "timeout",
    isRunning: phase === "launching" || phase === "running",
    retry,
    reset,
    cancelRun,
    cancelBusy,
  };
}
