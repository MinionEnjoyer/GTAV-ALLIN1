import type { RecordData } from "./client";
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
  const label = descriptor?.label ?? title(name);
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
    gbay_ui_backend: ["auto", "reactor", "legacy"],
  };
  const choices = descriptor?.choices ?? options[name];
  return (
    <label>
      {label}
      {choices ? (
        <select
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
