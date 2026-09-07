import type { RecordData } from "./client";

export default function StartupStatus({ startup, acknowledged, onAcknowledge }: {
  startup: RecordData; acknowledged: boolean; onAcknowledge: () => void;
}) {
  const details = <>
    <p>{startup.failure || (startup.active ? "Waiting for fresh startup evidence…" : "Startup monitoring finished")}</p>
    <ol>{(startup.milestones ?? []).map(([key, label]: [string, string]) =>
      <li key={key}>{startup.ready?.includes(key) ? "✓" : startup.active ? "…" : "—"} {label}</li>)}</ol>
  </>;
  return <section aria-label="Reactor startup" className="startup-status">
    {acknowledged ? <details>
      <summary>Previous startup warning — acknowledged</summary>
      {details}
      <p>This clears the Launcher alert only. It does not confirm Reactor or Story Mode is ready.</p>
    </details> : <>
      <h2>Reactor startup</h2>
      {details}
      {startup.failure && <div className="startup-warning-actions">
        <button disabled={!!startup.active} onClick={onAcknowledge}>Acknowledge warning</button>
        <small>Clear the Launcher alert; keep diagnostic details. No game or service action is taken.</small>
      </div>}
    </>}
  </section>;
}
