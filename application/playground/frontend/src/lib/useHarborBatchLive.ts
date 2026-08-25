import { useCallback, useEffect, useRef, useState } from "react";

import { api, ApiError } from "./api";
import {
  EMPTY_HARBOR_JOB_STREAM_STATE,
  applyHarborJobEnvelope,
  connectHarborJobEvents,
  type HarborJobStreamState,
} from "./harborJobEventStream";
import type { HarborJobDetail, HarborJobLiveResponse } from "./types";

const STALE_BACKEND_HINT =
  "Live events API is unavailable. Realtime updates are degraded; the final job snapshot will still be reconciled.";

function jobDetailToLive(job: HarborJobDetail): HarborJobLiveResponse {
  const trials = job.trials.map((trial) => ({
    trialName: trial.trialName, completed: trial.completed, succeeded: trial.succeeded,
    error: trial.error, phase: null,
  }));
  return { jobName: job.jobName, launchStatus: job.launch?.status ?? null, trialCount: trials.length,
    completedTrials: trials.filter((trial) => trial.completed).length, trials };
}

async function fetchLiveSnapshot(jobName: string): Promise<HarborJobLiveResponse> {
  try { return await api.getHarborJobLive(jobName); }
  catch (exc) {
    if (exc instanceof ApiError && exc.status === 404) return jobDetailToLive(await api.getHarborJob(jobName));
    throw exc;
  }
}

function liveWithStream(snapshot: HarborJobLiveResponse, stream: HarborJobStreamState): HarborJobLiveResponse {
  const byName = new Map(snapshot.trials.map((trial) => [trial.trialName, trial]));
  for (const trialName of stream.trialOrder) if (!byName.has(trialName)) byName.set(trialName, { trialName });
  const trials = [...byName.values()].map((trial) => ({
    ...trial,
    phase: stream.liveByTrial[trial.trialName]?.phase ?? trial.phase ?? null,
    completed:
      stream.liveByTrial[trial.trialName]?.phase === "done" || stream.liveByTrial[trial.trialName]?.phase === "error"
        ? true
        : trial.completed,
    succeeded:
      stream.liveByTrial[trial.trialName]?.phase === "done"
        ? true
        : stream.liveByTrial[trial.trialName]?.phase === "error"
          ? false
          : trial.succeeded,
    error:
      stream.liveByTrial[trial.trialName]?.phase === "error"
        ? trial.error ?? "Trial failed."
        : trial.error,
  }));
  const launchStatus = stream.launchStatus ?? snapshot.launchStatus ?? null;
  return {
    ...snapshot, launchStatus, trials, trialCount: Math.max(snapshot.trialCount, trials.length),
    completedTrials: trials.filter((trial) => trial.completed).length,
  };
}

/** One job stream owns every batch trial; selection only chooses which state is displayed. */
export function useHarborBatchLive(jobName: string | null, options?: { enabled?: boolean }) {
  const enabled = options?.enabled ?? true;
  const [live, setLive] = useState<HarborJobLiveResponse | null>(null);
  const [selectedTrial, setSelectedTrial] = useState<string | null>(null);
  const [streamState, setStreamState] = useState<HarborJobStreamState>(EMPTY_HARBOR_JOB_STREAM_STATE);
  const streamStateRef = useRef<HarborJobStreamState>(EMPTY_HARBOR_JOB_STREAM_STATE);
  const [error, setError] = useState<string | null>(null);
  const cursorRef = useRef(0);
  const terminalReconciledRef = useRef(false);
  const degradedRef = useRef(false);

  const selectTrial = useCallback((trialName: string) => setSelectedTrial(trialName), []);

  useEffect(() => {
    if (!jobName || !enabled) {
      setLive(null); setSelectedTrial(null); setStreamState(EMPTY_HARBOR_JOB_STREAM_STATE); streamStateRef.current = EMPTY_HARBOR_JOB_STREAM_STATE;
      cursorRef.current = 0; terminalReconciledRef.current = false; degradedRef.current = false;
      return;
    }
    let cancelled = false;
    let snapshot: HarborJobLiveResponse | null = null;
    const reconcileTerminal = async () => {
      if (terminalReconciledRef.current) return;
      terminalReconciledRef.current = true;
      try {
        const finalSnapshot = await fetchLiveSnapshot(jobName);
        if (!cancelled) setLive((current) => current ? liveWithStream(finalSnapshot, streamStateRef.current) : current);
      } catch (cause) {
        if (!cancelled) setError(cause instanceof Error ? cause.message : String(cause));
      }
    };
    void (async () => {
      try {
        snapshot = await fetchLiveSnapshot(jobName);
        if (cancelled) return;
        setLive(liveWithStream(snapshot, streamStateRef.current));
        setSelectedTrial((current) => current ?? snapshot?.trials.find((trial) => !trial.completed)?.trialName ?? snapshot?.trials[0]?.trialName ?? null);
      } catch (cause) {
        if (!cancelled) setError(cause instanceof Error ? cause.message : String(cause));
      }
    })();
    const close = connectHarborJobEvents({
      jobName, cursor: cursorRef.current,
      onEnvelope: (envelope) => {
        cursorRef.current = envelope.id;
        setStreamState((current) => {
          const next = applyHarborJobEnvelope(current, envelope);
          streamStateRef.current = next;
          if (snapshot) setLive(liveWithStream(snapshot, next));
          return next;
        });
        if (envelope.trialName) setSelectedTrial((current) => current ?? envelope.trialName);
        if (envelope.trialName === null && envelope.event.type === "job_state" && envelope.event.terminal) void reconcileTerminal();
      },
      onError: (cause) => {
        if (cancelled) return;
        setError(`${STALE_BACKEND_HINT} ${cause.message}`);
        // EventSource itself retries. A single snapshot is the bounded compatibility fallback.
        if (!degradedRef.current) {
          degradedRef.current = true;
          void (async () => {
            try {
              const fallback = await fetchLiveSnapshot(jobName);
              if (!cancelled) setLive((current) => current ? liveWithStream(fallback, streamStateRef.current) : current);
            } catch { /* Preserve the visible transport cause. */ }
          })();
        }
      },
    });
    return () => { cancelled = true; close(); };
  }, [enabled, jobName]);

  const selectedLive = selectedTrial ? streamState.liveByTrial[selectedTrial] ?? null : null;
  return {
    live, selectedTrial, selectTrial, selectedLive, liveByTrial: streamState.liveByTrial, error,
    isActive: live?.launchStatus === "running" || live?.launchStatus === "queued" || (live != null && live.completedTrials < live.trialCount),
  };
}
