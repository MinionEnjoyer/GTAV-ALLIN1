import { useEffect, useRef, useState } from "react";
import type { Client, RecordData } from "./client";

const SHA = /^[a-f0-9]{64}$/;

type Props = {
  client: Client;
  config: RecordData | null;
  draft: RecordData | null;
  change: (value: RecordData | null) => void;
  review: (action: string, values: RecordData) => void;
  locked: boolean;
};

export default function RuntimeInjectors({ client, config, draft, change, review, locked }: Props) {
  const [loaded, setLoaded] = useState<RecordData | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const version = useRef(0);
  const population = loaded?.traffic_population as RecordData | undefined;
  const saved = population?.document as RecordData | undefined;
  const models = Array.isArray(population?.models) ? population.models : [];
  const sourceDocument = draft?.kind === "traffic" ? draft.document : saved;
  const invalid = !!draft?.invalid;
  const document = sourceDocument ? {
    ...sourceDocument,
    entries: models.map((model: RecordData) =>
      (Array.isArray(sourceDocument.entries) ? sourceDocument.entries : []).find((entry: RecordData) =>
        entry.package_id === model.package_id && entry.model === model.model,
      ) ?? { package_id: model.package_id, model: model.model, enabled: false, weight: 0.1 }),
  } : sourceDocument;
  const entries = Array.isArray(document?.entries) ? document.entries : [];

  const inspect = async () => {
    if (locked || busy || draft) return;
    const generation = ++version.current;
    setBusy(true); setError("");
    try {
      const result = await client.request("inspect", { module: "vehicle_manager", ...(config ? { config } : {}) });
      if (generation !== version.current) return;
      const next = result.traffic_population as RecordData;
      if (!SHA.test(String(result.state_sha256)) || !next || !SHA.test(String(next.document_sha256)) || !Array.isArray(next.models) || !Array.isArray(next.document?.entries)) {
        throw new Error("The traffic catalog response was incomplete. Refresh before editing.");
      }
      setLoaded(result); change(null);
    } catch (reason) {
      if (generation === version.current) setError(String(reason));
    } finally {
      if (generation === version.current) setBusy(false);
    }
  };

  useEffect(() => {
    version.current++; setBusy(false); setLoaded(null); setError(""); change(null);
    return () => { version.current++; };
  }, []);

  const update = (mutate: (current: RecordData) => RecordData) => {
    if (document) change({ kind: "traffic", document: mutate(structuredClone(document)), invalid: false });
  };
  const number = (raw: string, apply: (value: number) => void) => {
    const value = Number(raw);
    if (!raw.trim() || !Number.isFinite(value) || value < .1 || value > 20) {
      change({ kind: "traffic", document, invalid: true });
      return;
    }
    apply(value);
  };
  const updateEntry = (index: number, mutate: (entry: RecordData) => RecordData) => update(current => ({
    ...current,
    entries: current.entries.map((entry: RecordData, currentIndex: number) => currentIndex === index ? mutate(entry) : entry),
  }));

  return <section className="injector" aria-label="Traffic runtime injector">
    <div className="toolbar">
      <button className="primary" disabled={locked || busy || !!draft} onClick={() => void inspect()}>
        {loaded ? "Refresh authorized catalog" : "Load authorized catalog"}
      </button>
      {draft && <button disabled={locked || busy} onClick={() => change(null)}>Discard draft</button>}
    </div>
    <p className="injector-boundary">Policies apply only after review and a closed-game confirmation. Catalog entries must come from installed, receipt-authorized packages.</p>
    {error && <p className="notice error" role="alert">{error}</p>}
    {invalid && <p className="notice error" role="alert">Enter a finite value within the displayed range before review.</p>}
    {!loaded && !busy && <p>Load the authorized catalog to configure traffic.</p>}
    {document && population && <>
      <fieldset>
        <legend>Traffic policy</legend>
        <label className="check">
          <input type="checkbox" checked={!!document.enabled} disabled={locked || busy} onChange={event => update(current => ({ ...current, enabled: event.target.checked }))} />
          Enable traffic injector
        </label>
        <label>Replacement chance · {Math.round(Number(document.replacement_chance ?? 0) * 100)}%
          <div className="range-input">
            <input type="range" min="0" max="1" step=".01" value={Number(document.replacement_chance ?? 0)} disabled={locked || busy || !document.enabled} onChange={event => update(current => ({ ...current, replacement_chance: Number(event.target.value) }))} />
            <input aria-label="Traffic replacement chance percent" type="number" min="0" max="100" value={Math.round(Number(document.replacement_chance ?? 0) * 100)} disabled={locked || busy || !document.enabled} onChange={event => {
              const value = Number(event.target.value);
              if (!event.target.value.trim() || !Number.isFinite(value) || value < 0 || value > 100) change({ kind: "traffic", document, invalid: true });
              else update(current => ({ ...current, replacement_chance: value / 100 }));
            }} />
          </div>
        </label>
        <p>Gameplay traffic enabled remains the master gate. When the injector is on, its curated stock pool is retained; a custom vehicle also needs package and catalog traffic opt-in—unsupported types are never silently enabled.</p>
      </fieldset>
      <fieldset>
        <legend>Authorized entries</legend>
        {!entries.length && <p>No authorized entries are available. Install a receipt-declared package with a traffic catalog first.</p>}
        {entries.map((entry: RecordData, index: number) => {
          const model = models.find((item: RecordData) => item.package_id === entry.package_id && item.model === entry.model);
          const name = model?.name ?? entry.model;
          return <div className="injector-entry" key={`${entry.package_id}:${entry.model}`}>
            <strong>{name}</strong><small>{model?.category ?? entry.package_id}</small>
            <label className="check"><input type="checkbox" checked={!!entry.enabled} disabled={locked || busy || !document.enabled} onChange={event => updateEntry(index, row => ({ ...row, enabled: event.target.checked }))} />Include</label>
            <label>Weight
              <div className="range-input"><input type="range" min=".1" max="20" step=".1" value={entry.weight} disabled={locked || busy || !document.enabled || !entry.enabled} onChange={event => updateEntry(index, row => ({ ...row, weight: Number(event.target.value) }))} /><input aria-label={`${name} weight`} type="number" min=".1" max="20" step=".1" value={entry.weight} disabled={locked || busy || !document.enabled || !entry.enabled} onChange={event => number(event.target.value, value => updateEntry(index, row => ({ ...row, weight: value })))} /></div>
            </label>
          </div>;
        })}
      </fieldset>
      {population.warnings?.length > 0 && <section className="notice warning"><strong>Catalog warnings</strong>{population.warnings.map((warning: string) => <p key={warning}>{warning}</p>)}</section>}
      <div className="toolbar"><button className="primary" disabled={locked || busy || !draft || invalid} onClick={() => review("traffic_population_save", { document, expected_document_sha256: population.document_sha256 })}>Review Traffic policy</button></div>
    </>}
  </section>;
}
