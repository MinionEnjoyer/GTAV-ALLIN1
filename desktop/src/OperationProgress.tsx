export default function OperationProgress({ heading, message, percentage }: {
  heading: string; message: string; percentage?: number; active?: boolean;
}) {
  return <section className="operation-progress" aria-label={heading}>
    <div className="operation-progress-title"><strong>{heading}</strong>
      {percentage !== undefined && <span>{percentage}%</span>}</div>
    <p role="status">{message}</p>
    {percentage !== undefined && <div className="operation-progress-track"
      role="progressbar" aria-label={heading} aria-valuemin={0} aria-valuemax={100}
      aria-valuenow={percentage} aria-valuetext={message}>
      <div style={{ width: `${percentage}%` }} />
    </div>}
  </section>;
}
