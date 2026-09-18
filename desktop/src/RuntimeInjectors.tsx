import { useEffect, useRef, useState } from "react";
import type { Client, RecordData } from "./client";

type Kind = "ped" | "traffic" | "weapon";
type Spec = { module: string; action: string; title: string; model: string; maxWeight: number; ped?: boolean; addCap?: boolean };

const SPEC: Record<Kind, Spec> = {
  ped: { module: "ped_manager", action: "ped_population_save", title: "Pedestrians", model: "model", maxWeight: 1, ped: true, addCap: true },
  traffic: { module: "vehicle_manager", action: "traffic_population_save", title: "Traffic", model: "model", maxWeight: 20 },
  weapon: { module: "weapon_manager", action: "weapon_population_save", title: "Weapons", model: "weapon", maxWeight: 100 },
};
const SHA = /^[a-f0-9]{64}$/;

type Props = {
  client: Client;
  kind: Kind;
  config: RecordData | null;
  draft: RecordData | null;
  change: (value: RecordData | null) => void;
  review: (action: string, values: RecordData) => void;
  locked: boolean;
};

const populationKey = (kind: Kind) => `${kind === "traffic" ? "traffic" : kind === "weapon" ? "weapon" : "ped"}_population`;

export default function RuntimeInjectors({ client, kind, config, draft, change, review, locked }: Props) {
  const spec = SPEC[kind];
  const [loaded, setLoaded] = useState<RecordData | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const version = useRef(0);
  const population = loaded?.[populationKey(kind)] as RecordData | undefined;
  const saved = population?.document as RecordData | undefined;
  const models = Array.isArray(population?.models) ? population.models : [];
  const sourceDocument = draft?.kind === kind ? draft.document : saved;
  const invalid = !!draft?.invalid;

  const entriesFor = (value: RecordData) => {
    const existing = Array.isArray(value.entries) ? value.entries : [];
    return models.map((model: RecordData) => existing.find((entry: RecordData) =>
      entry.package_id === model.package_id && entry[spec.model] === model[spec.model],
    ) ?? (spec.ped
      ? { package_id: model.package_id, model: model.model, mode: "disabled" }
      : { package_id: model.package_id, [spec.model]: model[spec.model], enabled: false, weight: kind === "traffic" ? 0.1 : 1 }));
  };
  // Older weapon policies did not have this setting. Normalize them locally so
  // every new review submits the explicit, safe default.
  const document = sourceDocument ? {
    ...sourceDocument,
    ...(kind === "weapon" ? { active_during_missions: !!sourceDocument.active_during_missions } : {}),
    entries: entriesFor(sourceDocument),
  } : sourceDocument;
  const entries = Array.isArray(document?.entries) ? document.entries : [];
  const missingTarget = Boolean(spec.ped && entries.some((entry: RecordData) => entry.mode === "replace" && !entry.target_model));

  const inspect = async () => {
    if (locked || busy || draft) return;
    const generation = ++version.current;
    setBusy(true); setError("");
    try {
      const result = await client.request("inspect", { module: spec.module, ...(config ? { config } : {}) });
      if (generation !== version.current) return;
      const next = result[populationKey(kind)] as RecordData;
      if (!SHA.test(String(result.state_sha256)) || !next || !SHA.test(String(next.document_sha256)) || !Array.isArray(next.models) || !Array.isArray(next.document?.entries)) {
        throw new Error("The injector catalog response was incomplete. Refresh before editing.");
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
  }, [kind]);

  const update = (mutate: (current: RecordData) => RecordData) => {
    if (document) change({ kind, document: mutate(structuredClone(document)), invalid: false });
  };
  const number = (raw: string, low: number, high: number, apply: (value: number) => void, integer = false) => {
    const value = Number(raw);
    if (!raw.trim() || !Number.isFinite(value) || value < low || value > high || (integer && !Number.isInteger(value))) {
      change({ kind, document, invalid: true });
      return;
    }
    apply(value);
  };
  const updateEntry = (index: number, mutate: (entry: RecordData) => RecordData) => update(current => ({
    ...current,
    entries: current.entries.map((entry: RecordData, currentIndex: number) => currentIndex === index ? mutate(entry) : entry),
  }));

  return <section className="injector" aria-label={`${spec.title} runtime injector`}>
    <div className="toolbar">
      <button className="primary" disabled={locked || busy || !!draft} onClick={() => void inspect()}>
        {loaded ? "Refresh authorized catalog" : "Load authorized catalog"}
      </button>
      {draft && <button disabled={locked || busy} onClick={() => change(null)}>Discard draft</button>}
    </div>
    <p className="injector-boundary">Policies apply only after review and a closed-game confirmation. Catalog entries must come from installed, receipt-authorized packages.</p>
    {kind === "ped" && <p>Ambient NPCs only; does not replace Franklin, Michael, Trevor, or mission/story characters. Player, mission, and scripted pedestrians are never edited.</p>}
    {error && <p className="notice error" role="alert">{error}</p>}
    {invalid && <p className="notice error" role="alert">Enter a finite value within the displayed range before review.</p>}
    {missingTarget && <p className="notice error" role="alert">Choose a vanilla target for every pedestrian replacement before review.</p>}
    {!loaded && !busy && <p>Load the authorized catalog to configure this runtime injector.</p>}
    {document && population && <>
      <fieldset>
        <legend>{spec.title} policy</legend>
        <label className="check">
          <input type="checkbox" checked={!!document.enabled} disabled={locked || busy} onChange={event => update(current => ({ ...current, enabled: event.target.checked }))} />
          Enable {kind === "weapon" ? "same-tier weapon replacement" : kind === "traffic" ? "traffic injector" : "optional ambient pedestrians"}
        </label>
        <label>Replacement chance · {Math.round(Number(document.replacement_chance ?? 0) * 100)}%
          <div className="range-input">
            <input type="range" min="0" max="1" step=".01" value={Number(document.replacement_chance ?? 0)} disabled={locked || busy || !document.enabled} onChange={event => update(current => ({ ...current, replacement_chance: Number(event.target.value) }))} />
            <input aria-label={`${spec.title} replacement chance percent`} type="number" min="0" max="100" value={Math.round(Number(document.replacement_chance ?? 0) * 100)} disabled={locked || busy || !document.enabled} onChange={event => number(event.target.value, 0, 100, value => update(current => ({ ...current, replacement_chance: value / 100 })))} />
          </div>
        </label>
        {spec.addCap && <label>Maximum added pedestrians
          <div className="range-input">
            <input type="range" min="0" max="20" value={Number(document.max_added ?? 0)} disabled={locked || busy || !document.enabled} onChange={event => update(current => ({ ...current, max_added: Number(event.target.value) }))} />
            <input aria-label="Maximum added pedestrians" type="number" min="0" max="20" value={Number(document.max_added ?? 0)} disabled={locked || busy || !document.enabled} onChange={event => number(event.target.value, 0, 20, value => update(current => ({ ...current, max_added: value })), true)} />
          </div>
        </label>}
        {kind === "traffic" && <p>Gameplay traffic enabled remains the master gate. When the injector is on, its curated stock pool is retained; a custom vehicle also needs package and catalog traffic opt-in—unsupported types are never silently enabled.</p>}
        {kind === "weapon" && <>
          <label className="check">
            <input type="checkbox" checked={!!document.active_during_missions} disabled={locked || busy || !document.enabled} onChange={event => update(current => ({ ...current, active_during_missions: event.target.checked }))} />
            Active during story missions
          </label>
          <p>When enabled, weapon replacement can continue during story missions. This does not alter protected story characters; wanted levels do not pause weapon replacement.</p>
          <p>Replacement is limited to compatible tiers (pistol, SMG, shotgun, rifle). Player, traffic, and GBAY loadouts are not changed.</p>
        </>}
      </fieldset>
      <fieldset>
        <legend>Authorized entries</legend>
        {!entries.length && <p>No authorized entries are available. Install a receipt-declared package with the matching catalog first.</p>}
        {entries.map((entry: RecordData, index: number) => {
          const model = models.find((item: RecordData) => item.package_id === entry.package_id && item[spec.model] === entry[spec.model]);
          const name = model?.name ?? entry[spec.model];
          return <div className="injector-entry" key={`${entry.package_id}:${entry[spec.model]}`}>
            <strong>{name}</strong><small>{model?.category ?? entry.package_id}</small>
            {spec.ped ? <PedEntry entry={entry} index={index} name={name} targets={population.targets ?? []} disabled={locked || busy || !document.enabled} update={updateEntry} /> : <WeightedEntry entry={entry} index={index} name={name} traffic={kind === "traffic"} max={spec.maxWeight} disabled={locked || busy || !document.enabled} update={updateEntry} number={number} />}
          </div>;
        })}
      </fieldset>
      {population.warnings?.length > 0 && <section className="notice warning"><strong>Catalog warnings</strong>{population.warnings.map((warning: string) => <p key={warning}>{warning}</p>)}</section>}
      <div className="toolbar"><button className="primary" disabled={locked || busy || !draft || invalid || missingTarget} onClick={() => review(spec.action, { document, expected_document_sha256: population.document_sha256 })}>Review {spec.title} policy</button></div>
    </>}
  </section>;
}

function PedEntry({ entry, index, name, targets, disabled, update }: { entry: RecordData; index: number; name: string; targets: any[]; disabled: boolean; update: (index: number, mutate: (entry: RecordData) => RecordData) => void }) {
  return <><label>Mode
    <select aria-label={`${name} mode`} value={entry.mode} disabled={disabled} onChange={event => update(index, row => event.target.value === "replace" ? { ...row, mode: "replace", target_model: row.target_model ?? "" } : (() => { const { target_model, ...withoutTarget } = row; return { ...withoutTarget, mode: event.target.value }; })())}>
      <option value="disabled">Disabled</option><option value="add">Add</option><option value="replace">Replace explicit vanilla target</option>
    </select>
  </label>{entry.mode === "replace" && <label>Vanilla target
    <select aria-label={`${name} target`} value={entry.target_model ?? ""} disabled={disabled} onChange={event => update(index, row => ({ ...row, target_model: event.target.value }))}>
      <option value="">Choose target</option>{targets.map(target => <option key={typeof target === "string" ? target : target.model} value={typeof target === "string" ? target : target.model}>{typeof target === "string" ? target : target.name ?? target.model}</option>)}
    </select>
  </label>}</>;
}

function WeightedEntry({ entry, index, name, traffic, max, disabled, update, number }: { entry: RecordData; index: number; name: string; traffic: boolean; max: number; disabled: boolean; update: (index: number, mutate: (entry: RecordData) => RecordData) => void; number: (raw: string, low: number, high: number, apply: (value: number) => void, integer?: boolean) => void }) {
  const low = traffic ? .1 : 1, step = traffic ? .1 : 1;
  return <><label className="check"><input type="checkbox" checked={!!entry.enabled} disabled={disabled} onChange={event => update(index, row => ({ ...row, enabled: event.target.checked }))} />Include</label><label>Weight
    <div className="range-input"><input type="range" min={low} max={max} step={step} value={entry.weight} disabled={disabled || !entry.enabled} onChange={event => update(index, row => ({ ...row, weight: Number(event.target.value) }))} /><input aria-label={`${name} weight`} type="number" min={low} max={max} step={step} value={entry.weight} disabled={disabled || !entry.enabled} onChange={event => number(event.target.value, low, max, value => update(index, row => ({ ...row, weight: value })), !traffic)} /></div>
  </label></>;
}
