import type { RecordData } from "./client";
import ContentSettings from "./ContentSettings";

export default function PackageDraft({ draft, locked, change, review }: {
  draft: RecordData; locked: boolean; change: (value: RecordData) => void;
  review: () => void;
}) {
  const item = draft.package;
  return <section aria-label="Package inspection">
    <h2>{item.name} · {item.version}</h2>
    <p>{item.description || "This package does not provide a description."}</p>
    <p className="path">{draft.source}</p>
    <p>{item.editions.join(" / ")} · {item.type} · schema {item.schema_version}</p>
    <p>{item.files.length} files · {item.rpf_entry_count} RPF entries</p>
    {item.dependencies.length > 0 && <p>Requires: {item.dependencies.join(", ")}</p>}
    {item.conflicts.length > 0 && <p>Conflicts: {item.conflicts.join(", ")}</p>}
    <details><summary>File destinations</summary>
      <ul>{item.files.map((file: RecordData) => <li className="path" key={file.destination}>{file.destination}</li>)}</ul>
    </details>
    {item.extension && <>
      <h3>Initial settings</h3>
      <p>These settings are saved with the package after you review and apply installation.</p>
      <ContentSettings item={{ ...item.extension, installed: true }} values={item.settings} locked={locked}
        change={(key, value) => change({ ...draft, package: { ...item, settings: { ...item.settings, [key]: value } } })} />
    </>}
    <button disabled={locked} onClick={review}>Review package installation</button>
  </section>;
}
