import { useEffect, useRef, useState } from "react";
import { nativeClient, type Client, type RecordData } from "./client";
import { Fields, Field, title } from "./Fields";
import Characters from "./Characters";
import ContentSettings from "./ContentSettings";
import PackageDraft from "./PackageDraft";
import AssistantSettings from "./AssistantSettings";
import logo from "../../src/allin1/assets/ALLIN1.png";
import { descriptions, EmptyState, ReviewDialog, WorkspaceIcon } from "./WorkspaceChrome";

const NAV = [
  ["setup", "Setup"],
  ["gameplay", "Gameplay"],
  ["content", "Content"],
  ["input", "Input"],
  ["mods", "Packages"],
  ["characters", "Characters"],
  ["sdk", "SDK Manager"],
  ["activity", "Activity"],
  ["help", "Help Center"],
];
const inputField = (key: string) =>
  key.startsWith("controller_") ||
  key.endsWith("_key") ||
  [
    "hold_duration_ms",
    "ui_scale",
    "reduced_motion",
    "colorblind_mode",
  ].includes(key);

export default function App({ client = nativeClient }: { client?: Client }) {
  const [catalog, setCatalog] = useState<RecordData>({}),
    [module, setModule] = useState("setup"),
    [session, setSession] = useState<RecordData>({});
  const [config, setConfig] = useState<RecordData | null>(null),
    [baseline, setBaseline] = useState("");
  const [draft, setDraft] = useState<RecordData>({}),
    [review, setReview] = useState<RecordData | null>(null),
    [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [notice, setNotice] = useState("");
  const [activity, setActivity] = useState<string[]>([]),
    [profile, setProfile] = useState(""),
    [query, setQuery] = useState("");
  const [activityCleared, setActivityCleared] = useState(false);
  const activityText = activityCleared ? "" : activity.length ? activity.join("\n") :
    (session.activity ?? []).map((event: RecordData) => `${new Date(event.time * 1000).toLocaleString()} · ${title(event.action)} completed`).join("\n");
  const [selected, setSelected] = useState(""),
    [reactorConsent, setReactorConsent] = useState(false),
    [rpfConsent, setRpfConsent] = useState(false);
  const [collapsed, setCollapsed] = useState(
    localStorage.getItem("launcher.sidebar") === "collapsed",
  );
  const [theme, setTheme] = useState(
    localStorage.getItem("launcher.theme") || "system",
  );
  const [sdkRelease, setSdkRelease] = useState<RecordData | null>(null),
    [startup, setStartup] = useState<RecordData | null>(null);
  const [launcherRelease, setLauncherRelease] = useState<RecordData | null>(null);
  const [handoff, setHandoff] = useState<RecordData | null>(null);
  const [settingsSearch, setSettingsSearch] = useState("");
  const dirty =
    (!!config && JSON.stringify(config) !== baseline) ||
    Object.keys(draft).length > 0;
  const locked = busy || !!review;
  const live = useRef({ dirty, locked });
  live.current = { dirty, locked };
  const flight = useRef(false),
    mounted = useRef(true),
    generation = useRef(0);
  const run = async (
    operation: string,
    payload: RecordData,
    adopt: (result: RecordData) => void = () => {},
  ) => {
    if (flight.current) return false;
    flight.current = true;
    setBusy(true);
    setError("");
    const version = ++generation.current;
    try {
      const result = await client.request(operation, payload);
      if (mounted.current && version === generation.current) adopt(result);
      return true;
    } catch (reason) {
      if (mounted.current) setError(String(reason));
      return false;
    } finally {
      flight.current = false;
      if (mounted.current) setBusy(false);
    }
  };
  const inspect = (target = module, values = config) =>
    run(
      "inspect",
      { module: target, ...(values ? { config: values } : {}) },
      (loaded) => {
        setSession(loaded);
        if (target === "content") setSelected((current) =>
          loaded.content?.some((item: RecordData) => item.id === current) ? current : loaded.content?.[0]?.id ?? "");
        if (!config) {
          setConfig(loaded.config);
          setBaseline(JSON.stringify(loaded.config));
        }
      },
    );
  const reconnect = async () => {
    if (!await run("reconnect_service", {}, () => {
      setReview(null);
      setConfirmed(false);
      setNotice("Draft kept; previous review invalidated. No action was replayed. Verify files and receipts before repeating an interrupted write.");
    })) return;
    if (await run("catalog", {}, setCatalog) && !config) await inspect("setup", null);
  };
  useEffect(() => {
    mounted.current = true;
    let removeClose: (() => void) | undefined,
      removeProgress: (() => void) | undefined,
      removeHandoff: (() => void) | undefined;
    void client
      .onHandoff((request) => {
        if (mounted.current) setHandoff(request);
      })
      .then((remove) => {
        if (mounted.current) removeHandoff = remove;
        else remove();
      })
      .catch((reason) => setError(String(reason)));
    void client
      .onClose(() => {
        if (live.current.dirty || live.current.locked) {
          setError(
            "Save or reset your draft and finish the current operation before closing.",
          );
          return;
        }
        void client.close().catch((reason) => setError(String(reason)));
      })
      .then((remove) => {
        if (mounted.current) removeClose = remove;
        else remove();
      })
      .catch((reason) => setError(String(reason)));
    void client
      .onProgress((progress) => {
        if (!mounted.current) return;
        setNotice(`${progress.percentage}% · ${progress.message}`);
        setActivity((rows) => [...rows.slice(-199), progress.message]);
        setActivityCleared(false);
      })
      .then((remove) => {
        if (mounted.current) removeProgress = remove;
        else remove();
      })
      .catch((reason) => setError(String(reason)));
    void (async () => {
      try {
        const loaded = await client.request("catalog");
        if (mounted.current) {
          setCatalog(loaded);
          await inspect("setup", null);
        }
      } catch (reason) {
        if (mounted.current) setError(String(reason));
      }
    })();
    const unload = (event: BeforeUnloadEvent) => {
      if (live.current.dirty || live.current.locked) {
        event.preventDefault();
        event.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", unload);
    return () => {
      mounted.current = false;
      generation.current++;
      removeClose?.();
      removeProgress?.();
      removeHandoff?.();
      window.removeEventListener("beforeunload", unload);
    };
  }, [client]);
  useEffect(() => {
    localStorage.setItem("launcher.theme", theme);
    document.documentElement.dataset.theme = theme;
  }, [theme]);
  useEffect(() => {
    localStorage.setItem(
      "launcher.sidebar",
      collapsed ? "collapsed" : "expanded",
    );
  }, [collapsed]);
  useEffect(() => {
    if (!startup?.active) return;
    const timer = window.setInterval(() => {
      if (!flight.current && !review)
        void run("startup_status", {}, setStartup);
    }, 1000);
    return () => window.clearInterval(timer);
  }, [startup?.active, review]);
  const navigate = (target: string) => {
    if (locked || Object.keys(draft).length) {
      setError(
        "Finish or reset the current workspace draft before navigating.",
      );
      return;
    }
    setModule(target);
    setSelected("");
    setQuery("");
    setSettingsSearch("");
    void inspect(target);
  };
  useEffect(() => {
    const keydown = (event: KeyboardEvent) => {
      if (review) return;
      const key = event.key.toLowerCase();
      if (event.ctrlKey && key === "b") {
        event.preventDefault(); setCollapsed((value) => !value); return;
      }
      if (event.ctrlKey && event.key === "Tab") {
        event.preventDefault();
        const index = NAV.findIndex(([key]) => key === module);
        navigate(NAV[(index + (event.shiftKey ? NAV.length - 1 : 1)) % NAV.length][0]);
        return;
      }
      if (event.key === "F5" || (event.ctrlKey && ["s", "l"].includes(key))) {
        event.preventDefault();
        if (locked || Object.keys(draft).length) {
          setError("Finish or reset the workspace draft before using this application shortcut.");
        } else if (event.key === "F5") void inspect();
        else if (config) beginReview(key === "l" ? "launch" : "save_config");
        return;
      }
      if (event.ctrlKey && /^[1-9]$/.test(event.key)) {
        event.preventDefault();
        navigate(NAV[Number(event.key) - 1][0]);
      }
      if (event.key === "F1") {
        event.preventDefault();
        navigate("help");
      }
    };
    window.addEventListener("keydown", keydown);
    return () => window.removeEventListener("keydown", keydown);
  });
  const beginReview = (action: string, values: RecordData = {}) => {
    if (locked) return;
    void run("review", { action, config, ...values }, (loaded) => {
      setReview(loaded);
      setConfirmed(false);
    });
  };
  const apply = async () => {
    if (!review || !confirmed || flight.current) return;
    const current = review;
    let appliedConfig = config;
    const succeeded = await run(
      "apply",
      {
        review_id: current.review_id,
        review_sha256: current.review_sha256,
        confirmed: true,
      },
      (result) => {
        setNotice(result.warning || `${title(result.action)} completed`);
        setActivity((rows) => [
          ...rows.slice(-199),
          `${title(result.action)} completed`,
        ]);
        if (result.saved_config) {
          appliedConfig = result.saved_config;
          setConfig(appliedConfig);
          setBaseline(JSON.stringify(appliedConfig));
        }
        if (result.action === "launch" && result.result?.startup_monitoring)
          setStartup({ active: true, ready: [], milestones: [] });
        const savedDraft = (
          {
            characters_save: "loadouts",
            garages_save: "garages",
            garages_repair: "garages",
            content_settings: "settings",
            save_content_preferences: "settings",
            package_install: "package",
            assistant_save: "assistant",
          } as Record<string, string>
        )[result.action];
        if (savedDraft)
          setDraft((currentDraft) => {
            const next = { ...currentDraft };
            delete next[savedDraft];
            delete next[savedDraft + "_base"];
            return next;
          });
      },
    );
    setReview(null);
    setConfirmed(false);
    if (succeeded) await inspect(module, appliedConfig);
  };
  const choose = async (kind: string, then: (path: string) => void) => {
    if (flight.current || review) return;
    flight.current = true;
    setBusy(true);
    try {
      const path = await client.selectPath(kind);
      flight.current = false;
      setBusy(false);
      if (path) then(path);
    } catch (reason) {
      setError(String(reason));
    } finally {
      flight.current = false;
      setBusy(false);
    }
  };
  const edit = (section: string, key: string, value: any) =>
    setConfig(
      (current) =>
        current && {
          ...current,
          [section]: { ...current[section], [key]: value },
        },
    );
  const reset = () => {
    if (locked) return;
    setDraft({});
    setConfig(JSON.parse(baseline));
    setError("");
  };
  const content = (session.content ?? []) as RecordData[],
    packages = (session.packages ?? []) as RecordData[];
  const topics = (catalog.help_topics ?? []).filter((topic: RecordData) =>
    `${topic.title} ${topic.body}`.toLowerCase().includes(query.toLowerCase()),
  );
  const selectedTopic =
    topics.find((topic: RecordData) => topic.key === selected) ?? topics[0];
  const configSection = (name: string, filter?: (key: string) => boolean) => (
    <fieldset key={name}>
      <legend>{title(name)}</legend>
      <Fields
        values={config?.[name] ?? {}}
        disabled={locked}
        filter={(key) => (!filter || filter(key)) && title(key).toLowerCase().includes(settingsSearch.toLowerCase())}
        change={(key, value) => edit(name, key, value)}
      />
    </fieldset>
  );
  return (
    <div className={`launcher ${collapsed ? "collapsed" : ""}`}>
      <header>
        <div className="brand">
          <img src={logo} alt="" />
          <div>
            <strong>ALLIN1</strong>
            <small>
              Story Mode Launcher · {catalog.desktop_version ?? "0.6.4"}
            </small>
          </div>
        </div>
        <label>
          Theme
          <select
            aria-label="Theme"
            value={theme}
            onChange={(e) => setTheme(e.target.value)}
          >
            <option>system</option>
            <option>dark</option>
            <option>light</option>
          </select>
        </label>
      </header>
      <aside aria-label="Workspace navigation">
        <button
          type="button"
          className="sidebar-toggle"
          onClick={() => setCollapsed((value) => !value)}
          aria-label={collapsed ? "Expand navigation" : "Collapse navigation"}
          aria-expanded={!collapsed}
          aria-controls="launcher-navigation"
          title={`${collapsed ? "Show" : "Hide"} workspace sidebar (Ctrl+B)`}
        >
          <span aria-hidden="true">{collapsed ? "›" : "‹"}</span>
        </button>
        <nav id="launcher-navigation" aria-label="Primary">
          {NAV.map(([key, label], index) => (
            <div key={key}>
            {[0, 4, 6].includes(index) && !collapsed && <p className="nav-label">{index === 0 ? "Configuration" : index === 4 ? "Your content" : "Tools"}</p>}
            <button
              onClick={() => navigate(key)}
              aria-label={label}
              disabled={locked || Object.keys(draft).length > 0}
              aria-current={module === key ? "page" : undefined}
              title={`${label} (Ctrl+${index + 1})`}
            >
              <WorkspaceIcon name={key} />
              {!collapsed && <><span className="nav-copy">{label}</span><kbd>{index + 1}</kbd></>}
            </button>
            </div>
          ))}
        </nav>
        {!collapsed && <div className="sidebar-note">Story Mode only<small>Ctrl+B · collapse navigation</small></div>}
      </aside>
      <main className={`workspace-${module}`}>
        <div className="page-heading">
          <div>
            <p className="eyebrow">
              ALLIN1 /{" "}
              {session.status?.edition ??
                config?.general.target_edition ??
                "Setup"}
            </p>
            <h1>{NAV.find(([key]) => key === module)?.[1]}</h1>
            <p className="page-description">{descriptions[module]}</p>
          </div>
          <div className="toolbar">
            <button disabled={locked || Object.keys(draft).length > 0} onClick={() => void inspect()}>
              Refresh
            </button>
            {dirty && (
              <button disabled={locked} onClick={reset}>
                Reset draft
              </button>
            )}
          </div>
        </div>
        {error && (
          <div className="notice error" role="alert">
            <div><strong>Could not complete this operation</strong><p>{error}</p></div>
            <div className="notice-actions">
            <button disabled={busy} onClick={() => void reconnect()}>Reconnect service</button>
            <button onClick={() => setError("")}>Dismiss</button>
            </div>
          </div>
        )}
        {!config && !error && <EmptyState title="Connecting to the Launcher service">Reading your settings and installation status…</EmptyState>}
        {config && ["gameplay", "input"].includes(module) && <label className="settings-search">Find a setting
          <input type="search" value={settingsSearch} placeholder="Search by name…" onChange={(event) => setSettingsSearch(event.target.value)} />
        </label>}
        {notice && (
          <p className="notice" role="status">
            {notice}
          </p>
        )}
        {handoff && (
          <section className="notice" aria-label="SDK package request">
            <p>
              The SDK requested Packages
              {handoff.package_id ? ` for ${handoff.package_id}` : ""}.
              {handoff.traffic !== null && handoff.traffic !== undefined
                ? ` Requested traffic setting: ${handoff.traffic ? "on" : "off"}; no setting has been changed.`
                : ""}
            </p>
            <button
              disabled={locked || dirty}
              onClick={() => {
                navigate("mods");
                setNotice(
                  `Requested package: ${handoff.package_id ?? "package library"}. Installation and settings still require your review.`,
                );
                setHandoff(null);
              }}
            >
              Open requested package
            </button>
          </section>
        )}
        {startup && (
          <section aria-label="Reactor startup">
            <h2>Reactor startup</h2>
            <p>
              {startup.failure ||
                (startup.active
                  ? "Waiting for fresh startup evidence…"
                  : "Startup monitoring finished")}
            </p>
            <ol>
              {(startup.milestones ?? []).map(
                ([key, label]: [string, string]) => (
                  <li key={key}>
                    {startup.ready?.includes(key) ? "✓" : "…"} {label}
                  </li>
                ),
              )}
            </ol>
          </section>
        )}
        {review && (
          <ReviewDialog busy={busy} cancel={() => { setReview(null); setConfirmed(false); }}>
          <section className="review" aria-label="Review changes">
            <h2>Review {title(review.action)}</h2>
            <p>Target: {review.target}</p>
            {review.preservation && <p>{review.preservation}</p>}
            {review.migration && (
              <div aria-label="Preference import plan">
                <p>Copy {review.migration.copy_count} missing preference files. Preserve {review.migration.preserve_count} existing files. The previous Launcher folder and game files will not change.</p>
                <ul>{review.migration.files.map((file: RecordData) => <li key={file.path}>{file.action === "copy" ? "Copy" : "Preserve existing"}: {file.path}</li>)}</ul>
              </div>
            )}
            {review.assistant_download && <div aria-label="Assistant download plan">
              <p>{review.assistant_download.display_name} · {(review.assistant_download.total_download_bytes / 1024 ** 3).toFixed(2)} GiB. Downloads pinned runtime/model files and their licenses; verifies every SHA-256 before activation.</p>
              <p>No inference runtime will be started. The current assistant mode is preserved.</p>
            </div>}
            {review.assistant_hardware && <ul>{review.assistant_hardware.warnings.map((message: string) => <li key={message}>{message}</li>)}</ul>}
            <p>
              {review.game_write
                ? "This changes the selected installation. GTA V must be closed."
                : "This changes Launcher files or the selected export."}
            </p>
            <details>
              <summary>Requested changes</summary>
              <pre>{JSON.stringify(review.request, null, 2)}</pre>
            </details>
            <label className="check">
              <input
                type="checkbox"
                checked={confirmed}
                disabled={busy}
                onChange={(e) => setConfirmed(e.target.checked)}
              />
              I reviewed these changes
            </label>
            <div className="toolbar">
              <button
                className="primary"
                disabled={!confirmed || busy}
                onClick={() => void apply()}
              >
                Apply reviewed changes
              </button>
              <button
                disabled={busy}
                onClick={() => {
                  setReview(null);
                  setConfirmed(false);
                }}
              >
                Back to draft
              </button>
            </div>
          </section>
          </ReviewDialog>
        )}
        {module === "setup" && config && (
          <>
            <section className="readiness">
              <h2>
                {session.status?.valid_game
                  ? `GTA V ${session.status.edition}`
                  : "Select your game installation"}
              </h2>
              <p>{session.status?.valid_game ? "Dependency availability for the selected installation. This is not an in-game runtime check." : "Choose a Legacy or Enhanced folder below, then refresh to inspect it. Nothing will be installed without your review."}</p>
              <div className="status-grid">
                {[
                  ["mod_installed", "ALLIN1 client"],
                  ["scripthookv_installed", "ScriptHookV"],
                  ["shvdn_installed", "ScriptHookVDotNet"],
                  ["openrpf_installed", "OpenRPF"],
                ].map(([key, label]) => (
                  <div key={key}>
                    <span>{label}</span>
                    <strong className={`status-pill ${session.status?.[key] ? "success" : "warning"}`}>
                      {!session.status?.valid_game ? "Not checked" : session.status?.[key] ? "Installed" : "Missing"}
                    </strong>
                  </div>
                ))}
              </div>
            </section>
            {configSection("general")}
            <div className="toolbar">
              {["legacy", "enhanced"].map((edition) => (
                <button
                  key={edition}
                  disabled={locked}
                  onClick={() =>
                    void choose("game", (path) =>
                      edit("general", `gta_${edition}_path`, path),
                    )
                  }
                >
                  Choose {title(edition)} folder
                </button>
              ))}
              <button
                disabled={locked}
                onClick={() =>
                  void run("health", {}, (result) =>
                    setNotice(JSON.stringify(result)),
                  )
                }
              >
                Check health
              </button>
            </div>
            <fieldset>
              <legend>Configuration profiles</legend>
              <p>Moving from an older Launcher? Import its config.toml and named profiles. Existing preferences are kept.</p>
              <button disabled={locked || dirty} onClick={() => void choose("folder", (source) => beginReview("import_preferences", { source }))}>
                Import previous Launcher preferences
              </button>
              <div className="toolbar">
                <label>
                  Profile name
                  <input
                    list="profiles"
                    value={profile}
                    disabled={locked}
                    onChange={(e) => setProfile(e.target.value)}
                  />
                  <datalist id="profiles">
                    {(session.profiles ?? []).map((name: string) => (
                      <option key={name}>{name}</option>
                    ))}
                  </datalist>
                </label>
                <button
                  disabled={locked || !profile}
                  onClick={() => beginReview("save_profile", { name: profile })}
                >
                  Save profile
                </button>
                <button
                  disabled={locked || dirty || !profile}
                  onClick={() =>
                    void run("load_profile", { name: profile }, (result) =>
                      setConfig(result.config),
                    )
                  }
                >
                  Load profile
                </button>
                <button
                  disabled={locked || !profile}
                  onClick={() =>
                    beginReview("delete_profile", { name: profile })
                  }
                >
                  Delete profile
                </button>
                <button
                  disabled={locked || !profile}
                  onClick={() =>
                    void choose("export_profile", (destination) =>
                      beginReview("export_profile", {
                        name: profile,
                        destination,
                      }),
                    )
                  }
                >
                  Export profile
                </button>
              </div>
            </fieldset>
            <fieldset>
              <legend>Installation options</legend>
              <Field
                name="download_reactor_dependency"
                value={reactorConsent}
                disabled={locked}
                change={setReactorConsent}
              />
              <Field
                name="download_rpf_preview_loader"
                value={rpfConsent}
                disabled={locked}
                change={setRpfConsent}
              />
              <p>
                Optional dependency downloads are included only when selected
                here.
              </p>
            </fieldset>
            <div className="toolbar">
              <button
                disabled={locked || !session.status?.valid_game}
                onClick={() =>
                  beginReview("install", {
                    reactor_consent: reactorConsent,
                    rpf_loader_consent: rpfConsent,
                  })
                }
              >
                Review Install / Repair
              </button>
              <button
                disabled={locked || !session.status?.mod_installed}
                onClick={() => beginReview("uninstall")}
              >
                Review uninstall
              </button>
            </div>
          </>
        )}
        {module === "gameplay" && config && (
          <>
            {configSection("traffic")}
            {configSection("vehicles")}
            {configSection("script", (key) => !inputField(key))}
          </>
        )}
        {module === "input" && config && configSection("script", inputField)}
        {module === "content" && (
          <div className="split">
            <div className="list" aria-label="Content packages">
              {content.map((item) => (
                <button
                  key={item.id}
                  aria-current={selected === item.id ? "page" : undefined}
                  disabled={locked || !!draft.settings}
                  onClick={() => setSelected(item.id)}
                >
                  {item.name}
                  <small>
                    {item.installed ? "Installed" : "Not installed"}
                  </small>
                </button>
              ))}
            </div>
            <section>
              {!selected && <EmptyState title="No content selected">Select an integration from the list to see its settings.</EmptyState>}
              {content
                .filter((item) => item.id === selected)
                .map((item) => (
                  <div key={item.id}>
                    <h2>{item.name}</h2>
                    <p>{item.description}</p>
                    {item.blocked_reason && <p role="status">Blocked: {item.blocked_reason}</p>}
                    <p>{item.source} · API {item.api_version} · {item.installed ? (item.enabled ? "Enabled" : "Disabled") : "Not installed"}</p>
                    <ContentSettings item={item}
                      values={draft.settings ?? item.settings}
                      locked={locked}
                      change={(key, value) =>
                        setDraft({
                          settings: {
                            ...(draft.settings ?? item.settings),
                            [key]: value,
                          },
                        })
                      }
                    />
                    <div className="toolbar">
                      <button
                        disabled={locked || !draft.settings}
                        onClick={() =>
                          beginReview(item.installed ? "content_settings" : "save_content_preferences", {
                            id: item.id,
                            settings: item.installed ? draft.settings : Object.fromEntries(
                              item.schema_settings.filter((setting: RecordData) => setting.config_key)
                                .map((setting: RecordData) => [setting.key, draft.settings[setting.key]])),
                          })
                        }
                      >
                        {item.installed ? "Review content settings" : "Review preinstall preferences"}
                      </button>
                      {["enable", "disable"].map((action) => (
                        <button
                          key={action}
                          disabled={locked || !item.installed}
                          onClick={() =>
                            beginReview(`content_${action}`, { id: item.id })
                          }
                        >
                          Review {action}
                        </button>
                      ))}
                    </div>
                  </div>
                ))}
            </section>
          </div>
        )}
        {module === "mods" && (
          <>
            <button
              disabled={locked || !!draft.package}
              onClick={() =>
                void choose("package", (source) =>
                  void run("inspect", { module: "package", source, config }, (loaded) => setDraft({ package: loaded })),
                )
              }
            >
              Review package import
            </button>
            {draft.package && <PackageDraft draft={draft.package} locked={locked}
              change={(value) => setDraft({ package: value })}
              review={() => beginReview("package_install", {
                source: draft.package.source, settings: draft.package.package.settings,
                expected_state_sha256: draft.package.state_sha256,
              })} />}
            <div className="split">
              <section>
                <h2>Package library</h2>
                {!packages.length && <EmptyState title="Your package library is empty">Use Review package import to inspect a ZIP or mod.toml built with the SDK.</EmptyState>}
                {packages.map((item) => (
                  <div className="inventory-row" key={item.mod_id}>
                    <span>{item.name}</span>
                    <button
                      disabled={locked || !!draft.package}
                      onClick={() =>
                        void run("inspect", { module: "package", source: item.manifest_path, config },
                          (loaded) => setDraft({ package: loaded }))
                      }
                    >
                      Install {item.name}
                    </button>
                  </div>
                ))}
              </section>
              <section>
                <h2>Installed packages</h2>
                {!session.installed?.length && <EmptyState title="No installed packages">Packages for the selected GTA installation will appear here after installation.</EmptyState>}
                {(session.installed ?? []).map((item: RecordData) => (
                  <div className="package" key={item.mod_id}>
                    <strong>{item.name}</strong>
                    <small>
                      {item.version} · {item.enabled ? "Enabled" : "Disabled"}
                    </small>
                    <div className="toolbar">
                      <button
                        disabled={locked || !!draft.package}
                        onClick={() =>
                          beginReview(
                            item.enabled ? "package_disable" : "package_enable",
                            { id: item.mod_id },
                          )
                        }
                      >
                        {item.enabled ? "Disable" : "Enable"} {item.name}
                      </button>
                      <button
                        disabled={locked || !!draft.package}
                        onClick={() =>
                          beginReview("package_uninstall", { id: item.mod_id })
                        }
                      >
                        Uninstall {item.name}
                      </button>
                    </div>
                  </div>
                ))}
              </section>
            </div>
            <div className="split">
              <section>
                <h2>Included content</h2>
                <p>Included content is installed or repaired from Setup. Its settings are available in Content.</p>
                {(session.builtin_packages ?? []).map((item: RecordData) => <div className="package" key={item.id}>
                  <strong>{item.name}</strong>
                  <small>{item.installed ? (item.enabled ? "Enabled" : "Disabled") : "Not installed"}</small>
                  <p>{item.description}</p>
                </div>)}
                <button disabled={locked || !!draft.package} onClick={() => navigate("content")}>Configure included content</button>
              </section>
              <section>
                <h2>SDK examples</h2>
                <p>Authoring examples are not installable packages. Use the SDK to inspect and build them.</p>
                {(session.sdk_examples ?? []).map((item: RecordData) => <div className="package" key={item.id}>
                  <strong>{item.name}</strong><small>{item.editions.join(" / ")}</small><p>{item.summary}</p>
                </div>)}
                <button disabled={locked || !!draft.package} onClick={() => navigate("sdk")}>Open SDK Manager</button>
              </section>
            </div>
          </>
        )}
        {module === "characters" && (
          <>
            <Characters
              session={session}
              draft={draft}
              setDraft={setDraft}
              review={beginReview}
              busy={locked}
            />
            <div className="toolbar">
              <button
                disabled={locked}
                onClick={() =>
                  void choose("json", (source) => {
                    void run("read_garages", { source }, (result) =>
                      setDraft({ ...draft, garages: result.garages, garages_base: draft.garages_base ?? session.document_sha256.garages }),
                    );
                  })
                }
              >
                Import garages into draft
              </button>
              <button
                disabled={locked}
                onClick={() =>
                  void choose("export_json", (destination) =>
                    beginReview("garages_export", { destination }),
                  )
                }
              >
                Export saved garages
              </button>
            </div>
          </>
        )}
        {module === "sdk" && (
          <section>
            <details className="automation-panel"><summary>CLI, API &amp; agent workflows</summary>
              <p>The Launcher exposes the same reviewed operations as this UI. Start with the catalog; inspect an SDK-built package before requesting any installation.</p>
              <pre>allin1 launcher catalog{"\n"}allin1 launcher inspect --module package --source "path/to/package.zip"{"\n"}allin1 launcher agent-api</pre>
              <p>Portable build: run <code>sidecar/ALLIN1-Launcher-Sidecar.exe --cli catalog</code> or <code>--agent-api</code>. Agents default to read-only; writes require process authority, a current review, and explicit confirmation.</p>
            </details>
            <h2>ALLIN1 SDK</h2>
            <p>
              {session.sdk?.detail ?? "Refresh to inspect the SDK installation"}
            </p>
            <p className="path">{session.sdk?.root}</p>
            <div className="toolbar">
              <button
                disabled={locked}
                onClick={() =>
                  void choose("package", (source) =>
                    beginReview("sdk_install", { source }),
                  )
                }
              >
                Install SDK archive
              </button>
              <button
                disabled={locked}
                onClick={() => void run("check_sdk_update", {}, setSdkRelease)}
              >
                Check SDK releases
              </button>
              <button
                disabled={locked || !session.sdk?.healthy}
                onClick={() => beginReview("sdk_open")}
              >
                Open SDK
              </button>
              <button
                disabled={locked || !session.sdk?.executable}
                onClick={() => beginReview("sdk_uninstall")}
              >
                Uninstall SDK
              </button>
            </div>
            {sdkRelease && (
              <p>
                Latest: {sdkRelease.version} · {sdkRelease.archive_size} bytes{" "}
                <button
                  disabled={locked}
                  onClick={() => beginReview("sdk_install_release")}
                >
                  Review download and install SDK
                </button>
              </p>
            )}
            <p>
              Removal keeps a recoverable SDK.uninstalled-* directory beside the
              managed installation.
            </p>
            <h3>SDK tools</h3>
            <div className="toolbar">
              {[
                ["assets", "Asset Viewer"],
                ["rpf", "RPF Explorer"],
                ["assistant", "Qwen assistant"],
              ].map(([workspace, label]) => (
                <button
                  key={workspace}
                  disabled={locked || !session.sdk?.healthy}
                  onClick={() => beginReview("sdk_open", { workspace })}
                >
                  Open {label}
                </button>
              ))}
            </div>
            <AssistantSettings session={session.assistant ?? {}} draft={draft.assistant}
              setDraft={(value) => setDraft({ ...draft, assistant: value })} locked={locked}
              review={beginReview} choose={choose}
              inspect={(payload, adopt) => { void run("inspect", payload, adopt); }} />
          </section>
        )}
        {module === "activity" && (
          <>
            <div className="toolbar">
              <button
                disabled={locked}
                onClick={() =>
                  void choose("diagnostics", (destination) =>
                    beginReview("diagnostics", { destination }),
                  )
                }
              >
                Export diagnostics
              </button>
              <button disabled={locked || !activityText} onClick={() => {
                void navigator.clipboard.writeText(activityText).then(() => setNotice("Activity copied"), (error) => setError(`Could not copy activity: ${error}`));
              }}>Copy activity</button>
              <button disabled={locked} onClick={() => void run("open_activity_folder", {}, () => setNotice("Activity folder opened"))}>Open log folder</button>
              <button onClick={() => { setActivity([]); setActivityCleared(true); }}>
                Clear visible activity
              </button>
              <button
                disabled={locked}
                onClick={() =>
                  void run("check_update", {}, setLauncherRelease)
                }
              >
                Check for updates
              </button>
            </div>
            {launcherRelease && <section aria-label="Launcher release information">
              <h2>{launcherRelease.update_available ? "Update available" : "No newer Launcher release"}</h2>
              <p>Current {catalog.desktop_version} · Latest {launcherRelease.version}</p>
              <p>{launcherRelease.name}</p>
              <p>0.6.4 uses unsigned manual downloads. Review the release notes, build identity and checksums before installing. This action opens the official release page; it does not install or roll back anything.</p>
              <button disabled={locked} onClick={() => void run("open_launcher_release", {}, () => setNotice("Official Launcher release page opened"))}>Open official release page</button>
            </section>}
            <pre className="activity" aria-label="Activity log">
              {activityText || "No activity in this session."}
            </pre>
          </>
        )}
        {module === "help" && (
          <>
            <label>
              Search help
              <input value={query} onChange={(e) => setQuery(e.target.value)} />
            </label>
            <div className="help-layout">
              <nav className="help-topics" aria-label="Help topics">
                {topics.map((topic: RecordData) => (
                  <button
                    key={topic.key}
                    aria-current={
                      selectedTopic?.key === topic.key ? "page" : undefined
                    }
                    onClick={() => setSelected(topic.key)}
                  >
                    {topic.title}
                  </button>
                ))}
              </nav>
              <article>
                {selectedTopic && (
                  <>
                    <h2>{selectedTopic.title}</h2>
                    <p>{selectedTopic.summary}</p>
                    <div className="help-body">{selectedTopic.body}</div>
                  </>
                )}
              </article>
            </div>
          </>
        )}
      </main>
      <footer>
        <span className="footer-status"><i className={`activity-dot ${error ? "error" : busy ? "busy" : config ? "ready" : ""}`} />{busy ? "Working…" : dirty ? "Unsaved changes" : error ? "Needs attention" : !config ? "Connecting…" : "Ready"}</span>
        <div className="toolbar">
          <button
            disabled={locked || !config || !dirty || Object.keys(draft).length > 0}
            onClick={() => beginReview("save_config")}
          >
            Review save settings
          </button>
          <button
            disabled={locked || !config || Object.keys(draft).length > 0}
            onClick={() => beginReview("sync_config")}
          >
            Sync settings to game
          </button>
          <button
            className="primary"
            disabled={locked || !config || Object.keys(draft).length > 0}
            onClick={() => beginReview("launch")}
          >
            Launch Story Mode
          </button>
        </div>
      </footer>
    </div>
  );
}
