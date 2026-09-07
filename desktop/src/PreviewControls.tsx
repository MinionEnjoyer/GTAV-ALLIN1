export const previewCategories = ["weapons", "vehicles", "gear"] as const;

type PreviewCount = { existing: number | null; total: number | null; status: string; reason?: string };

export default function PreviewControls({ busy, skipped, quick, missingOnly = false, counts, onChange }: {
  busy: boolean; skipped: string[]; quick: boolean; missingOnly?: boolean;
  counts?: Partial<Record<typeof previewCategories[number], PreviewCount>>;
  onChange: (skipped: string[], quick: boolean, missingOnly: boolean) => void;
}) {
  const selected = previewCategories.filter(category => !skipped.includes(category));
  return <fieldset disabled={busy} className="preview-controls">
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
    {!quick && <label className="preview-category">
      <input type="checkbox" checked={missingOnly} onChange={event => onChange(skipped, false, event.target.checked)} />
      Missing previews only
    </label>}
    {!quick && missingOnly && <p className="preview-hint">Keep intact generated images, even after renderer or model updates. Generate only missing images in the selected categories. Package validation still runs.</p>}
    <div className="preview-categories" role="group" aria-label="Preview categories">
        {previewCategories.map(category => <label key={category} className="preview-category">
          {!quick && <input type="checkbox" aria-label={category[0].toUpperCase() + category.slice(1)} checked={!skipped.includes(category)}
            disabled={selected.length === 1 && selected[0] === category}
            title={selected.length === 1 && selected[0] === category ? "Choose Quick Launch to skip all categories" : undefined}
            onChange={event => {
              onChange(event.target.checked ? skipped.filter(c => c !== category)
                : [...skipped, category], false, missingOnly);
            }} />} {category[0].toUpperCase() + category.slice(1)}
          <span className="preview-count" title={counts?.[category]?.reason || "Existing generated previews / catalog items. Source validation runs during Update Previews."}>
            {counts?.[category]?.status === "available" ? `${counts[category]!.existing}/${counts[category]!.total}` : "Unavailable"}
          </span>
        </label>)}
    </div>
    <p className="preview-hint">Counts show existing / total previews, excluding throwables and unsupported gear. Launch safety checks always run.</p>
    <p className="preview-hint">Missing images use an installed default preview pack or a placeholder. Default images are not bundled.</p>
  </fieldset>;
}
