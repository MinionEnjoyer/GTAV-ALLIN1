export interface RpfWork {
  estimated_actions: number; completed_actions: number; entries: number;
  elapsed_seconds: number; budget_seconds: number; active_seconds: number;
  slow_action: boolean; budget_exceeded: boolean;
}
const duration = (seconds: number) => `${Math.floor(seconds / 60)}m ${seconds % 60}s`;

export default function OperationProgress({ heading, message, percentage, rpfWork }: {
  heading: string; message: string; percentage?: number; active?: boolean;
  rpfWork?: RpfWork;
}) {
  const progress = Number.isFinite(percentage) ? Math.max(0, Math.min(100, percentage as number)) : undefined;
  return <section className="operation-progress" aria-label={heading}>
    <div className="operation-progress-title"><strong>{heading}</strong>
      {progress !== undefined && <span aria-label={`${progress}% complete`}>{progress}%</span>}</div>
    <p role="status" aria-live="polite">{message}</p>
    {rpfWork && <section aria-label="RPF workload">
      <p>{rpfWork.completed_actions} of approximately {rpfWork.estimated_actions} RPF actions finished
        {rpfWork.entries > 0 ? ` across ${rpfWork.entries} entries` : ""}.</p>
      <p>Elapsed: {duration(rpfWork.elapsed_seconds)} · Workload budget: {duration(rpfWork.budget_seconds)}.</p>
      <small>The budget is an estimate, not a cancellation deadline. Extra archive work can extend it.</small>
      {rpfWork.slow_action && <p role="status">This RPF action has been running for {duration(rpfWork.active_seconds)}.
        The service is connected, but the action has not finished. Keep the launcher open; do not retry the write.</p>}
      {rpfWork.budget_exceeded && <p role="status">This operation is taking longer than its workload budget.
        It has not been stopped or retried. Waiting for a definitive result.</p>}
    </section>}
    {progress !== undefined && <div className="operation-progress-track"
      role="progressbar" aria-label={heading} aria-valuemin={0} aria-valuemax={100}
      aria-valuenow={progress} aria-valuetext={`${progress}% — ${message}`}>
      <div style={{ width: `${progress}%` }} />
    </div>}
  </section>;
}
