import type { RecordData } from "./client";
import { Field } from "./Fields";

export default function ContentSettings({ item, values, locked, change }: {
  item: RecordData; values: RecordData; locked: boolean;
  change: (key: string, value: unknown) => void;
}) {
  return <>{(item.systems ?? []).map((system: RecordData) => (
    <fieldset key={system.id}>
      <legend>{system.name}{system.experimental ? " · Experimental" : ""}</legend>
      {system.description && <p>{system.description}</p>}
      {system.experimental && <p role="note">Experimental controls can change between package versions. Review the package notes before applying them.</p>}
      <div className="fields">{system.settings.map((setting: RecordData) => (
        <div key={setting.key}>
          <Field name={setting.key} descriptor={setting} value={values[setting.key] ?? setting.default}
            disabled={locked || (!item.installed && !setting.config_key)}
            change={(value) => change(setting.key, value)} />
          {setting.description && <small>{setting.description}</small>}
          {!item.installed && !setting.config_key && <small role="note">Available after this package is installed.</small>}
        </div>
      ))}</div>
    </fieldset>
  ))}</>;
}
