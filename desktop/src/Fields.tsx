import { useEffect, useId, useState } from "react";
import type { RecordData } from "./client";
const bounded: Record<string, [number, number, number]> = {
  max_driven: [0, 100, 1], replacement_chance: [0, 1, 0.01], minimum_fps: [20, 120, 1],
  ui_scale: [0.75, 1.5, 0.05], hold_duration_ms: [100, 2000, 50],
};
const hints: Record<string, string> = {
  max_driven: "Maximum replacement vehicles active at once.", replacement_chance: "0 disables replacement; 1 replaces every eligible vehicle.",
  ui_scale: "In-game menu scale. Launcher text follows Windows display scaling.", minimum_fps: "Adaptive traffic pauses replacements below this frame rate.",
  hold_duration_ms: "How long a shortcut must be held, in milliseconds.",
  speedometer_provider: "Auto uses a loaded Rex/LeFix display; otherwise ALLIN1. External mods are installed separately and keep their own settings.",
  speedometer_units: "ALLIN1 HUD units. Numpad decimal toggles for the session; external displays use their own units settings.",
  driving_telemetry: "Local 5 Hz test log: towing only, all driving, or off. Bounded to four 8 MiB files; no uploads.",
  shift_controls_enabled: "Starts automatic. Numpad * toggles experimental forward-gear hold; +/− shift. Disabled in safe mode or with a detected transmission controller.",
  gta_path: "Optional shared path. Use edition-specific folders when both editions are installed.",
  gta_legacy_path: "Folder containing GTA5.exe.", gta_enhanced_path: "Folder containing GTA5_Enhanced.exe.",
};

function NumberField({ label, value, change, disabled, descriptor, name }: { label: string; value: number; change: (value: number) => void; disabled: boolean; descriptor?: RecordData; name: string }) {
  const [text, setText] = useState(String(value));
  const id = useId();
  useEffect(() => setText(String(value)), [value]);
  const limits = bounded[name];
  return <div className="number-field"><label htmlFor={id}>{label}</label>
    <div className={limits ? "range-input" : ""}>
      {limits && <input type="range" aria-label={`${label} slider`} min={limits[0]} max={limits[1]} step={limits[2]} value={value} disabled={disabled} onChange={(e) => change(Number(e.target.value))} />}
      <input id={id} type="number" value={text} disabled={disabled} min={descriptor?.minimum ?? limits?.[0]} max={descriptor?.maximum ?? limits?.[1]} step={descriptor?.step ?? limits?.[2] ?? "any"}
        onChange={(e) => { setText(e.target.value); if (e.target.value.trim() && Number.isFinite(Number(e.target.value))) change(Number(e.target.value)); }}
        onBlur={() => { if (!text.trim() || !Number.isFinite(Number(text))) setText(String(value)); }} />
    </div>{hints[name] && <small>{hints[name]}</small>}
  </div>;
}
export const title = (key: string) =>
  key
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase())
    .replace(/Gbay/g, "GBAY")
    .replace(/Gta/g, "GTA")
    .replace(/Rpf/g, "RPF");

export function Field({
  name,
  value,
  change,
  disabled = false,
  descriptor,
}: {
  name: string;
  value: any;
  change: (value: any) => void;
  disabled?: boolean;
  descriptor?: RecordData;
}) {
  const hintId = useId();
  const label = descriptor?.label ?? title(name);
  if (typeof value === "number") return <NumberField {...{label, value, change, disabled, descriptor, name}} />;
  if (typeof value === "boolean")
    return (
      <label className="check">
        <input
          type="checkbox"
          checked={value}
          onChange={(e) => change(e.target.checked)}
          disabled={disabled}
        />
        {label}
        {hints[name] && <small>{hints[name]}</small>}
      </label>
    );
  if (Array.isArray(value))
    return (
      <label>
        {label}
        <input
          value={value.join(", ")}
          onChange={(e) =>
            change(
              e.target.value
                .split(",")
                .map((s) => s.trim())
                .filter(Boolean),
            )
          }
          disabled={disabled}
        />
        <small>Separate values with commas</small>
      </label>
    );
  const options: Record<string, string[]> = {
    target_edition: ["auto", "legacy", "enhanced"],
    speedometer_provider: ["auto", "builtin", "rex", "lefix", "off"],
    speedometer_units: ["kmh", "mph"],
    driving_telemetry: ["off", "towing", "all"],
  };
  const choices = descriptor?.choices ?? options[name];
  return (
    <label>
      {label}
      {choices ? (
        <select
          aria-label={label}
          aria-describedby={hints[name] ? hintId : undefined}
          value={value}
          onChange={(e) => change(e.target.value)}
          disabled={disabled}
        >
          {choices.map((option: string) => (
            <option key={option}>{option}</option>
          ))}
        </select>
      ) : (
        <input
          aria-label={label}
          aria-describedby={hints[name] ? hintId : undefined}
          type={typeof value === "number" ? "number" : "text"}
          step={descriptor?.step ?? (descriptor?.type === "integer" ? 1 : "any")}
          min={descriptor?.minimum}
          max={descriptor?.maximum}
          value={value ?? ""}
          disabled={disabled}
          onChange={(e) =>
            change(
              typeof value === "number"
                ? Number(e.target.value)
                : e.target.value,
            )
          }
        />
      )}
      {hints[name] && <small id={hintId}>{hints[name]}</small>}
    </label>
  );
}
export function Fields({
  values,
  change,
  disabled = false,
  filter = () => true,
}: {
  values: RecordData;
  change: (key: string, value: any) => void;
  disabled?: boolean;
  filter?: (key: string) => boolean;
}) {
  return (
    <div className="fields">
      {Object.entries(values)
        .filter(([key]) => filter(key))
        .map(([key, value]) => (
          <Field
            key={key}
            name={key}
            value={value}
            disabled={disabled}
            change={(value) => change(key, value)}
          />
        ))}
    </div>
  );
}
