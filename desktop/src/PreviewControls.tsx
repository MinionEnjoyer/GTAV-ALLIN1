export const previewCategories = ["weapons", "vehicles", "gear"] as const;

type PreviewCount = { existing: number | null; total: number | null; status: string; reason?: string };

export default function PreviewControls({ busy, skipped, quick, missingOnly = false, counts, onChange }: {
  busy: boolean; skipped: string[]; quick: boolean; missingOnly?: boolean;
  counts?: Partial<Record<typeof previewCategories[number], PreviewCount>>;
  onChange: (skipped: string[], quick: boolean, missingOnly: boolean) => void;
}) {
  const selected = previewCategories.filter(category => !skipped.includes(category));
  return <fieldset disabled={busy} className="preview-controls launch-preview-controls">
    <legend>Launch mode</legend>
    <div className="preview-modes">
      <label className={`preview-mode${quick ? " selected" : ""}`}>
        <input type="radio" name="preview-mode" aria-label="Quick Launch" checked={quick}
          onChange={() => onChange(skipped, true, missingOnly)} />
        <span><strong>Quick Launch</strong><small>Use existing previews</small></span>
      </label>
      <label className={`preview-mode${!quick ? " selected" : ""}`}>
        <input type="radio" name="preview-mode" aria-label="Update Previews" checked={!quick}
          onChange={() => onChange(selected.length ? skipped : [], false, missingOnly)} />
        <span><strong>Update Previews</strong><small>Generate missing or outdated images</small></span>
      </label>
    </div>
    {!quick && <div className="preview-update-options">
      <label className="preview-category preview-missing-only">
        <input type="checkbox" checked={missingOnly} onChange={event => onChange(skipped, false, event.target.checked)} />
        Missing previews only
      </label>
      {missingOnly && <p className="preview-hint preview-missing-hint">Keep existing images and generate only missing selected previews.</p>}
    </div>}
    <section className="preview-coverage" aria-labelledby="preview-coverage-heading">
      <h3 id="preview-coverage-heading" className="preview-coverage-heading">Coverage <span>Existing / total</span></h3>
      <div className="preview-categories" role="group" aria-label="Preview categories">
        {previewCategories.map(category => <label key={category} className="preview-category">
          {!quick && <input type="checkbox" aria-label={category[0].toUpperCase() + category.slice(1)} checked={!skipped.includes(category)}
            disabled={selected.length === 1 && selected[0] === category}
            title={selected.length === 1 && selected[0] === category ? "Choose Quick Launch to skip all categories" : undefined}
            onChange={event => {
              onChange(event.target.checked ? skipped.filter(c => c !== category)
                : [...skipped, category], false, missingOnly);
            }} />} {category[0].toUpperCase() + category.slice(1)}
          <span className="preview-count" title={counts?.[category]?.reason || "Existing generated or downloaded default previews / catalog items. Source validation runs during Update Previews."}>
            {counts?.[category]?.status === "available" ? `${counts[category]!.existing}/${counts[category]!.total}` : "Unavailable"}
          </span>
        </label>)}
      </div>
    </section>
    <p className="preview-hint preview-coverage-hint">Counts include throwables and supported gear. Safety checks always run; missing images use a default pack or placeholder.</p>
  </fieldset>;
}
