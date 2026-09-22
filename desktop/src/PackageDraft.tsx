import type { RecordData } from "./client";
import ContentSettings from "./ContentSettings";

export default function PackageDraft({ draft, locked, change, review }: {
  draft: RecordData; locked: boolean; change: (value: RecordData) => void;
  review: (component?: RecordData) => void;
}) {
  const item = draft.package;
  return <section aria-label="Package inspection">
    <h2>{item.name} · {item.version}</h2>
    <p>{item.description || "This package does not provide a description."}</p>
    <p><strong>Package source</strong></p>
    <p className="path">{draft.source}</p>
    <p><strong>Compatibility:</strong> {item.editions.join(" / ")} · {item.type} · schema {item.schema_version}</p>
    {item.bundle_editions?.length > 0 && <p role="status">
      {item.selected_edition
        ? `Edition bundle: ${item.selected_edition} selected automatically. Only this variant will be installed.`
        : "Edition bundle: select a GTA installation to choose the matching variant."}
    </p>}
    {item.schema_version === 6 ? <>
      <p>Components are listed in installation order. Review and install each separately; each keeps its own Content controls, receipt and uninstall action. This is not an all-or-nothing batch install.</p>
      {item.components.map((component: RecordData, index: number) => <section key={component.id} aria-label={`Component ${index + 1} of ${item.components.length}: ${component.name}`}>
        <h3>Component {index + 1} of {item.components.length}</h3>
        <PackageDraft draft={{ source: draft.source, package: component }} locked={locked}
          review={() => review(component)}
          change={(value) => change({ ...draft, package: { ...item,
            components: item.components.map((row: RecordData) => row.id === component.id ? value.package : row) } })} />
      </section>)}
    </> : <>
    {item.installed && <p role="status"><strong>Installed:</strong> {item.installed_version} · {item.enabled ? "Enabled" : "Disabled"}</p>}
    {item.install_blocked_reason && <p role="status">{item.install_blocked_reason}</p>}
    <p><strong>Package contents:</strong> {item.files.length} files · {item.rpf_entry_count} RPF entries</p>
    {item.dependencies.length > 0 && <p><strong>Requires:</strong> {item.dependencies.join(", ")}</p>}
    {item.conflicts.length > 0 && <p><strong>Conflicts:</strong> {item.conflicts.join(", ")}</p>}
    <details><summary>File destinations</summary>
      <ul>{item.files.map((file: RecordData) => <li className="path" key={file.destination}>{file.destination}</li>)}</ul>
    </details>
    {item.extension && <>
      <h3>Initial settings</h3>
      <p>These settings are saved with the package after you review and apply installation.</p>
      <ContentSettings item={{ ...item.extension, installed: true }} values={item.settings} locked={locked}
        change={(key, value) => change({ ...draft, package: { ...item, settings: { ...item.settings, [key]: value } } })} />
    </>}
    <div className="toolbar">
      <button className="primary" disabled={locked || !!item.install_blocked_reason || (item.bundle_editions?.length > 0 && !item.selected_edition)}
        onClick={() => review()}>Review package installation</button>
      <small>Review shows the exact changes before anything is installed.</small>
    </div>
    </>}
  </section>;
}
