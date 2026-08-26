import type { ReactNode } from "react";

import { BatchTrialGrid, harborTrialsToGridCells, type BatchTrialCell } from "./BatchTrialGrid";
import { BatchTrialStage } from "./BatchTrialStage";
import { CockpitLiveStage } from "./CockpitLiveStage";
import { RunLaunchBar, type RunLaunchPhase } from "./RunLaunchBar";

export interface CockpitRunCenterProps {
  showLive: boolean;
  pipeline: ReactNode;
  liveContent: ReactNode;
  fillLiveContent?: boolean;
  batchJobName: string | null;
  batchCells: BatchTrialCell[];
  selectedBatchTrialId?: string | null;
  onSelectBatchTrial?: (trial: BatchTrialCell) => void;
  onBackToBatchGrid?: () => void;
  batchLiveContent?: ReactNode;
  runLaunchPhase: RunLaunchPhase;
  progressPct: number;
  progressLabel?: string;
  progressSublabel?: string;
  canRun: boolean;
  isBatch: boolean;
  personaCount: number;
  parallelTrials: number;
  onParallelTrialsChange: (value: number) => void;
  runBusy: boolean;
  onRun: () => void;
  error?: string | null;
  onNewRun?: () => void;
  onViewJob?: () => void;
  onCancelRun?: () => void;
  cancelRunBusy?: boolean;
  onDownload?: () => void;
  canDownload?: boolean;
  onRetryFailed?: () => void;
  failedCount?: number;
  retryBusy?: boolean;
}

/** Center column: pipeline (idle) → live stage or batch grid (running) + progress launch bar. */
export function CockpitRunCenter({
  showLive,
  pipeline,
  liveContent,
  fillLiveContent,
  batchJobName,
  batchCells,
  selectedBatchTrialId,
  onSelectBatchTrial,
  onBackToBatchGrid,
  batchLiveContent,
  runLaunchPhase,
  progressPct,
  progressLabel,
  progressSublabel,
  canRun,
  isBatch,
  personaCount,
  parallelTrials,
  onParallelTrialsChange,
  runBusy,
  onRun,
  error,
  onNewRun,
  onViewJob,
  onCancelRun,
  cancelRunBusy,
  onDownload,
  canDownload,
  onRetryFailed,
  failedCount,
  retryBusy,
}: CockpitRunCenterProps) {
  return (
    <div className="flex h-full min-h-0 w-full flex-col gap-2 overflow-hidden">
      {showLive ? (
        batchJobName ? (
          <BatchTrialStage>
            {selectedBatchTrialId && batchLiveContent ? (
              <div className="flex h-full min-h-0 flex-col gap-2">
                <button type="button" className="self-start text-sm text-primary" onClick={onBackToBatchGrid}>Back to cohort</button>
                <CockpitLiveStage className="h-0 min-h-0 flex-1" fillContent>{batchLiveContent}</CockpitLiveStage>
              </div>
            ) : (
              <BatchTrialGrid trials={batchCells} jobLabel={batchJobName} selectedTrialId={selectedBatchTrialId} onSelectTrial={onSelectBatchTrial} />
            )}
          </BatchTrialStage>
        ) : (
          <CockpitLiveStage className="h-0 min-h-0 flex-1" fillContent={fillLiveContent}>{liveContent}</CockpitLiveStage>
        )
      ) : (
        <div className="flex min-h-0 flex-1 flex-col">{pipeline}</div>
      )}
      <RunLaunchBar
        canRun={canRun}
        isBatch={isBatch}
        personaCount={personaCount}
        parallelTrials={parallelTrials}
        onParallelTrialsChange={onParallelTrialsChange}
        isRunning={runBusy}
        onRun={onRun}
        error={error}
        runPhase={runLaunchPhase}
        progressPct={progressPct}
        progressLabel={progressLabel}
        progressSublabel={progressSublabel}
        onNewRun={onNewRun}
        onViewJob={onViewJob}
        onCancelRun={onCancelRun}
        cancelRunBusy={cancelRunBusy}
        onDownload={onDownload}
        canDownload={canDownload}
        onRetryFailed={onRetryFailed}
        failedCount={failedCount}
        retryBusy={retryBusy}
      />
    </div>
  );
}

export { harborTrialsToGridCells };
