import { useState } from "react";
import { Fields, Field, title } from "./Fields";
import type { RecordData } from "./client";

export default function Characters({
  session,
  draft,
  setDraft,
  review,
  busy,
}: {
  session: RecordData;
  draft: RecordData;
  setDraft: (value: RecordData) => void;
  review: (action: string, data: RecordData) => void;
  busy: boolean;
}) {
  const [character, setCharacter] = useState("michael"),
    [area, setArea] = useState("progress"),
    [query, setQuery] = useState(""),
    [preset, setPreset] = useState("");
  const loadouts = draft.loadouts ?? session.loadouts;
  const garages = draft.garages ?? session.garages;
  const current = loadouts?.[character];
  if (!current)
    return <p>Select a valid installation in Setup to load character data.</p>;
  const edit = (change: (value: RecordData) => void) => {
    const next = structuredClone(loadouts);
    change(next[character]);
    setDraft({ ...draft, loadouts: next, loadouts_base: draft.loadouts_base ?? session.document_sha256.loadouts });
  };
  const garageEdit = (change: (value: RecordData[]) => void) => {
    const next = structuredClone(garages);
    change(next[character]);
    setDraft({ ...draft, garages: next, garages_base: draft.garages_base ?? session.document_sha256.garages });
  };
  const allItems: string[] = [...session.weapons, ...session.gear];
  return (
    <div>
      <div className="toolbar">
        <label>
          Character
          <select
            value={character}
            disabled={busy}
            onChange={(e) => setCharacter(e.target.value)}
          >
            {Object.keys(loadouts).map((key) => (
              <option key={key} value={key}>
                {title(key)}
              </option>
            ))}
          </select>
        </label>
        <nav className="tabs">
          {["progress", "inventory", "outfit", "garages"].map((key) => (
            <button
              key={key}
              aria-current={area === key ? "page" : undefined}
              onClick={() => setArea(key)}
            >
              {title(key)}
            </button>
          ))}
        </nav>
      </div>
      {area === "progress" && (
        <>
          <Field
            name="manage_story_progress"
            value={current.progress.managed}
            disabled={busy}
            change={(value) =>
              edit((row) => {
                row.progress.managed = value;
              })
            }
          />
          <Field
            name="money"
            value={current.progress.money}
            disabled={busy}
            change={(value) =>
              edit((row) => {
                row.progress.money = value;
              })
            }
          />
          <Fields
            values={current.progress.skills}
            disabled={busy}
            change={(key, value) =>
              edit((row) => {
                row.progress.skills[key] = value;
              })
            }
          />
        </>
      )}
      {area === "inventory" && (
        <>
          <label>
            Search weapons and gear
            <input value={query} onChange={(e) => setQuery(e.target.value)} />
          </label>
          <div className="inventory-list">
            {allItems
              .filter((item) =>
                item.toLowerCase().includes(query.toLowerCase()),
              )
              .map((item) => {
                const gear = session.gear.includes(item),
                  owned = current[gear ? "gear" : "weapons"].includes(item);
                return (
                  <div className="inventory-row" key={item}>
                    <span>{item}</span>
                    <button
                      disabled={busy}
                      onClick={() =>
                        edit((row) => {
                          row.managed = true;
                          const key = gear ? "gear" : "weapons";
                          if (owned) {
                            row[key] = row[key].filter(
                              (value: string) => value !== item,
                            );
                            if (gear)
                              row.equipped_gear = row.equipped_gear.filter(
                                (value: string) => value !== item,
                              );
                            else {
                              delete row.weapon_ammo[item];
                              delete row.weapon_customizations[item];
                            }
                          } else {
                            row[key].push(item);
                            if (gear) {
                              if (item.startsWith("ARMOR_")) {
                                row.gear = row.gear.filter(
                                  (value: string) =>
                                    !value.startsWith("ARMOR_") ||
                                    value === item,
                                );
                                row.equipped_gear = row.equipped_gear.filter(
                                  (value: string) =>
                                    !value.startsWith("ARMOR_"),
                                );
                              }
                              row.equipped_gear.push(item);
                            } else row.weapon_ammo[item] = 9999;
                          }
                        })
                      }
                    >
                      {owned ? "Remove" : "Add"} {item}
                    </button>
                    {owned && !gear && (
                      <label>
                        Ammo
                        <input
                          type="number"
                          min="0"
                          value={current.weapon_ammo[item] ?? 0}
                          disabled={busy}
                          onChange={(e) =>
                            edit((row) => {
                              row.weapon_ammo[item] = Number(e.target.value);
                            })
                          }
                        />
                      </label>
                    )}
                  </div>
                );
              })}
          </div>
        </>
      )}
      {area === "outfit" && (
        <>
          <Field
            name="manage_outfit"
            value={current.outfit.managed}
            disabled={busy}
            change={(value) =>
              edit((row) => {
                row.outfit.managed = value;
              })
            }
          />
          <Field
            name="unlock_all"
            value={current.outfit.unlock_all}
            disabled={busy}
            change={(value) =>
              edit((row) => {
                row.outfit.unlock_all = value;
              })
            }
          />
          {["components", "props"].map((group) => (
            <fieldset key={group}>
              <legend>{title(group)}</legend>
              <div className="outfit-grid">
                {current.outfit[group].map(
                  (item: RecordData, index: number) => (
                    <div key={index}>
                      <strong>
                        {title(group)} {index}
                      </strong>
                      {["drawable", "texture"].map((key) => (
                        <Field
                          key={key}
                          name={`${group}_${index}_${key}`}
                          value={item[key]}
                          disabled={busy}
                          change={(value) =>
                            edit((row) => {
                              row.outfit[group][index][key] = value;
                            })
                          }
                        />
                      ))}
                    </div>
                  ),
                )}
              </div>
            </fieldset>
          ))}
          <div className="toolbar">
            <label>
              Preset name
              <input
                value={preset}
                onChange={(e) => setPreset(e.target.value)}
              />
            </label>
            <button
              disabled={busy || !preset.trim()}
              onClick={() =>
                edit((row) => {
                  row.outfit.presets[preset.trim()] = {
                    components: structuredClone(row.outfit.components),
                    props: structuredClone(row.outfit.props),
                  };
                })
              }
            >
              Save outfit preset to draft
            </button>
          </div>
          {Object.keys(current.outfit.presets).map((name) => (
            <button
              key={name}
              disabled={busy}
              onClick={() =>
                edit((row) => {
                  const saved = row.outfit.presets[name];
                  row.outfit.components = structuredClone(saved.components);
                  row.outfit.props = structuredClone(saved.props);
                  row.outfit.managed = true;
                })
              }
            >
              Apply preset {name}
            </button>
          ))}
        </>
      )}
      {area === "garages" && (
        <>
          {session.garage_error && <p role="alert">{session.garage_error}</p>}
          {garages && (
            <>
              <div className="inventory-list">
                {garages[character].map((item: RecordData, index: number) => (
                  <div className="inventory-row" key={index}>
                    <label>
                      Slot
                      <input
                        type="number"
                        min="0"
                        max="9"
                        value={item.slot}
                        disabled={busy}
                        onChange={(e) =>
                          garageEdit((rows) => {
                            rows[index].slot = Number(e.target.value);
                          })
                        }
                      />
                    </label>
                    <label>
                      Vehicle
                      <select
                        value={item.model}
                        disabled={busy}
                        onChange={(e) =>
                          garageEdit((rows) => {
                            rows[index].model = e.target.value;
                          })
                        }
                      >
                        {session.models.map((model: string) => (
                          <option key={model}>{model}</option>
                        ))}
                      </select>
                    </label>
                    <button
                      disabled={busy}
                      onClick={() =>
                        garageEdit((rows) => {
                          rows.splice(index, 1);
                        })
                      }
                    >
                      Remove garage slot {item.slot}
                    </button>
                  </div>
                ))}
              </div>
              <button
                disabled={
                  busy ||
                  garages[character].length >= 10 ||
                  !session.models.length
                }
                onClick={() =>
                  garageEdit((rows) => {
                    const slot = Array.from({ length: 10 }, (_, n) => n).find(
                      (n) => !rows.some((row) => row.slot === n),
                    );
                    rows.push({ model: session.models[0], slot });
                  })
                }
              >
                Add garage vehicle
              </button>
              <button
                disabled={busy || !draft.garages}
                onClick={() =>
                  review("garages_save", {
                    document: garages,
                    expected_document_sha256: draft.garages_base,
                  })
                }
              >
                Review garage save
              </button>
            </>
          )}
          <button disabled={busy} onClick={() => review("garages_repair", {})}>
            Review garage repair
          </button>
        </>
      )}
      {area !== "garages" && (
        <button
          className="primary"
          disabled={busy || !draft.loadouts}
          onClick={() =>
            review("characters_save", {
              document: loadouts,
              expected_document_sha256: draft.loadouts_base,
            })
          }
        >
          Review character save
        </button>
      )}
    </div>
  );
}
