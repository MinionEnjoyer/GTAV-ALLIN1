"""Searchable, task-oriented help for the ALLIN1 desktop application."""

from __future__ import annotations

from dataclasses import dataclass
import tkinter as tk
from tkinter import ttk

from allin1 import __version__
from allin1.ui_theme import apply_current_theme


@dataclass(frozen=True)
class HelpTopic:
    """One concise help-center article."""

    key: str
    category: str
    title: str
    summary: str
    body: str
    keywords: tuple[str, ...] = ()


HELP_TOPICS: tuple[HelpTopic, ...] = (
    HelpTopic(
        "getting-started", "Start here", "Getting started",
        "Connect a game installation, check readiness, and launch safely.",
        """1. Open the Setup workspace and select your GTA V Legacy and/or Enhanced folders.
2. Choose the active edition. All install, launch, health, and package actions use it.
3. Review the readiness card. Install / Repair resolves the ALLIN1 client and can offer the optional RPF preview dependency when needed.
4. Save settings, then launch GTA V from the persistent action bar.

ALLIN1 is for Story Mode. Do not use a modified installation with GTA Online.""",
        ("setup", "first run", "game path", "story mode"),
    ),
    HelpTopic(
        "editions", "Start here", "Legacy and Enhanced installations",
        "Keep independent paths for both GTA V editions and choose an active target.",
        """Legacy and Enhanced can be installed on the same PC. Store each path separately in Setup, then select Auto, Legacy, or Enhanced as the active target.

Auto uses the best detected installation. A specific target is recommended while authoring or testing edition-sensitive packages. Package scans label compatibility but never silently convert native assets between editions.""",
        ("gen9", "path", "target", "compatibility"),
    ),
    HelpTopic(
        "install-repair", "Game management", "Install, repair, and launch",
        "Understand the safe game-management workflow.",
        """Install / Repair synchronizes the ALLIN1 Story Mode client and required files. It preserves configured backups and reports progress in the bottom status bar.

Health Check performs a deeper validation. Diagnostics creates a shareable report. Launch saves the current settings before handing off to Steam or Rockstar Games Launcher.

The retired offline-launch experiment is not part of 0.5.0. The launcher uses the normal Rockstar authentication flow and automatically removes only an old offline argument carrying ALLIN1's ownership record. Other commandline.txt options remain untouched.

If preview artwork is enabled but no compatible RPF loader is ready, Install / Repair asks before downloading anything. The pinned RageOpenV release is downloaded directly from its official project and checked before installation. If an ASI loader is also needed, the same rules apply to the pinned Ultimate ASI Loader release. Declining keeps placeholder artwork available.

ALLIN1 does not bundle these third-party binaries or overwrite an existing loader. If launch is blocked by an RPF safety warning, run Health Check before repairing. The warning is designed to prevent a known-bad package from hanging Story Mode.""",
        ("repair", "health", "launch", "dependencies", "blocked"),
    ),
    HelpTopic(
        "gameplay", "Configuration", "Launcher host behavior",
        "Configure shared recovery, previews, and diagnostics.",
        """Gameplay contains settings owned by the launcher host: managed backups, recovery safe mode, archive-backed previews, and detailed logging.

Gameplay supplied by a package belongs in Content. This keeps the launcher usable as a stable shell instead of hardcoding every installed system into this page.""",
        ("backup", "safe mode", "previews", "logging", "host"),
    ),
    HelpTopic(
        "content", "Configuration", "Content packages and systems",
        "Review installed systems and configure package-owned settings.",
        """Content is generated from versioned descriptors. ALLIN1 Online Content supplies the official GBAY, vehicle, weapon, gear, garage, property, traffic, and character systems. ALLIN1 Experimental Gameplay contains opt-in police and NPC-physics work.

Select a package to review its version, status, capabilities, and owner. Select one of its systems to change typed settings. Apply settings writes only that package's namespace; built-in compatibility settings are also synchronized to the current runtime configuration.

Package state enables or disables the whole selected package. The launcher refuses a state change when another enabled package requires it. A blocked package has failed its receipt or runtime-file integrity check.""",
        ("systems", "extension", "api", "registry", "gbay", "typed settings"),
    ),
    HelpTopic(
        "input", "Configuration", "Keyboard and controller input",
        "Assign shortcuts, controller actions, and vehicle filters.",
        """The Input workspace separates keyboard shortcuts from controller navigation. Avoid assigning one keyboard key to multiple launcher actions.

Controller shortcut actions may combine a modifier with an action button. Menu navigation bindings apply while GBAY menus are open. Vehicle class and model filters accept comma-separated values.""",
        ("controls", "keys", "gamepad", "bindings", "filter"),
    ),
    HelpTopic(
        "characters", "Configuration", "Characters and saved content",
        "Manage garages, loadouts, story progress, traffic tuning, and outfits.",
        """The Characters workspace operates on the scripts folder belonging to the active GTA V installation. Choose the correct Legacy or Enhanced target in Setup first.

Garage, loadout, progress, and outfit changes update ALLIN1's managed save data. GBAY purchases still become permanent only when the character saves the game. Use the repair and export controls before experimenting with a valuable save.""",
        ("garage", "weapons", "gear", "money", "outfit", "save"),
    ),
    HelpTopic(
        "packages", "Mods & SDK", "Package library",
        "Import, inspect, install, enable, disable, and remove optional content.",
        """Use Add package to import supported content. Select a package in the library, then use Package actions for installation and lifecycle commands.

ALLIN1 validates manifests, records installed files, and backs up replaced files when backup support is enabled. Only install content you trust. Edition tags describe the package's declared or detected compatibility.""",
        ("mods", "install", "manifest", "receipt", "enable", "uninstall"),
    ),
    HelpTopic(
        "sdk", "Mods & SDK", "Add-on SDK",
        "Trace game-facing fields and audit add-on integration before installation.",
        """Use SDK → Install / Manage SDK to install the optional, self-contained developer application. Managed releases are verified against both their public SHA-256 and internal file manifest, install per-user, and never modify GTA V. The panel can update, repair, open, or uninstall the SDK; Install from package supports the same verified archive while offline.

The Add-on SDK links authored package fields to metadata, native UI text, animations, runtime behavior, packaging, and rollback expectations.

Import a DLC folder or archive, inspect its integration graph, then select nodes and fields for explanations. Package Intelligence contains OIV preview, DLC inventory, and vehicle-data compilation tools.

The Optional assistant tab configures local-first help for installation and diagnostics. It is disabled by default, runs separately from GTA V, and can be uninstalled without removing the SDK. Before downloading Qwen, ALLIN1 checks 64-bit Windows support, RAM, free disk space, CPU threads, and CPU acceleration, then recommends the Qwen3.5 4B or 9B profile. Qwen and llama.cpp are downloaded separately from revision-pinned upstream sources and verified by exact size and SHA-256 before installation; they are not bundled with ALLIN1. The official Qwen base model and license are recorded separately from the GGUF conversion. A dedicated GPU is not required. Existing GGUF runtimes/models and compatible local APIs are also supported; API keys are referenced only through environment-variable names.

After saving an enabled mode, use assistant prompt followed by a question in the SDK's bottom console. assistant context shows the exact repository, manifest, game path, policy, and live command evidence without starting the model. Responses are structured and deterministically screened for invented operations, manual-copy instructions, and destructive guidance. assistant status inspects the provider without starting it, and assistant stop closes a local model server. Prompts are read-only and cannot approve or perform an installation.""",
        ("authoring", "addon", "dlc", "audit", "linker", "developer", "install", "update", "assistant", "model", "hardware"),
    ),
    HelpTopic(
        "asset-viewer", "Inspectors", "Native Asset Viewer",
        "Browse package files and preview supported native resources without executing code.",
        """Open a package folder or supported archive, search its inventory, and select an asset. Images and text preview directly. Supported Rockstar resources receive header analysis, structured CodeWalker XML, and texture contact sheets when possible.

The viewer is read-only. Compiled DLL, ASI, and script payloads are never executed.""",
        ("ytd", "ydr", "yft", "texture", "model", "preview", "codewalker"),
    ),
    HelpTopic(
        "rpf-explorer", "Inspectors", "RPF Explorer",
        "Search nested archives, inspect metadata, extract entries, and create safe plans.",
        """Select the matching GTA V installation before opening an RPF so the correct encryption keys and resource decoder are used.

Search and filter the archive tree, then use Entry actions to preview or extract the selected entry. Replacement planning creates an inert JSON review plan with hashes, backup requirements, verification steps, and rollback information. It does not modify the archive.""",
        ("archive", "nested", "extract", "replacement", "rpf", "metadata"),
    ),
    HelpTopic(
        "recovery", "Safety & recovery", "Backups and recovery",
        "Understand what ALLIN1 changes and how to recover it.",
        """Keep Back up game changes enabled for normal use. Package receipts identify installed files; uninstall uses those receipts and backups to restore replaced content.

Never manually delete a partially installed package before collecting diagnostics. Use Health Check, then Install / Repair or the package's Uninstall action. RPF replacement remains plan-only in the explorer because archive mutation requires stronger transactional guarantees.

Optional RPF dependencies installed by ALLIN1 have their own receipt. Uninstall removes only files that still match that receipt; pre-existing or modified loader files are preserved.""",
        ("backup", "rollback", "restore", "safety", "receipt"),
    ),
    HelpTopic(
        "troubleshooting", "Safety & recovery", "Troubleshooting and logs",
        "Collect useful evidence when installation, launch, or gameplay fails.",
        """Open Activity to review the current launcher session. Use Activity actions to copy it or open the persistent log folder.

For installation and startup failures, run Health Check and create a diagnostics bundle. For in-game behavior, reproduce the issue once with only the relevant diagnostic setting enabled, then retain the newest ScriptHookVDotNet and ALLIN1 logs.

Keyboard shortcuts: Ctrl+1–9 changes workspaces, Ctrl+B folds or restores the Player Workspaces sidebar, Ctrl+Tab and Ctrl+Shift+Tab cycle workspaces, Ctrl+S saves, Ctrl+L launches, F5 refreshes, and F1 opens this embedded help workspace.""",
        ("logs", "crash", "hang", "diagnostics", "shortcuts", "fatal"),
    ),
    HelpTopic(
        "about", "About", "About ALLIN1",
        "Version, project scope, support, and release information.",
        f"""ALLIN1 Launcher {__version__}

ALLIN1 is a GTA V Story Mode content launcher, package manager, and safety-focused companion to the standalone ALLIN1 SDK. Official gameplay is supplied by the ALLIN1 Online Content pack. The launcher owns installation, configuration, package lifecycle, profiles, diagnostics, and game launch. The SDK owns add-on linking, archive inspection, native assets, and developer automation.

Created and maintained by MinionEnjoyer. Use the Check for updates action in Setup for current release status. Project support: https://buymeacoffee.com/minionenjoyer""",
        ("version", "credits", "support", "updates", "release"),
    ),
)


def search_help_topics(query: str) -> tuple[HelpTopic, ...]:
    """Return help topics ranked by a simple, predictable text match."""
    words = tuple(part.casefold() for part in query.split() if part.strip())
    if not words:
        return HELP_TOPICS

    scored: list[tuple[int, HelpTopic]] = []
    for topic in HELP_TOPICS:
        title = topic.title.casefold()
        category = topic.category.casefold()
        summary = topic.summary.casefold()
        body = topic.body.casefold()
        keywords = " ".join(topic.keywords).casefold()
        haystack = " ".join((title, category, summary, body, keywords))
        if not all(word in haystack for word in words):
            continue
        score = sum(
            8 if word in title else 4 if word in keywords else 2 if word in summary else 1
            for word in words
        )
        scored.append((score, topic))
    return tuple(topic for _score, topic in sorted(
        scored, key=lambda item: (-item[0], item[1].category, item[1].title),
    ))


class HelpCenterDialog(ttk.Frame):
    """Searchable help center that embeds in the launcher shell."""

    def __init__(
        self, parent: tk.Misc, initial_topic: str | None = None,
        *, embedded: bool = False,
    ) -> None:
        self._window: tk.Toplevel | None = None
        host = parent
        if not embedded:
            self._window = tk.Toplevel(parent)
            self._window.title("ALLIN1 Help Center")
            self._window.geometry("1040x700")
            self._window.minsize(780, 540)
            self._window.transient(parent.winfo_toplevel())
            host = self._window
        super().__init__(host)
        self.pack(fill="both", expand=True)
        self.initial_topic = initial_topic
        self.visible_topics: tuple[HelpTopic, ...] = ()
        self.topic_items: dict[str, HelpTopic] = {}
        self._build()
        self._populate()
        if self._window is not None:
            self.bind("<Escape>", lambda _event: self._window.destroy())
        apply_current_theme(self._window or self)

    def _build(self) -> None:
        outer = ttk.Frame(self, padding=20)
        outer.pack(fill="both", expand=True)
        header = ttk.Frame(outer)
        header.pack(fill="x", pady=(0, 16))
        ttk.Label(
            header, text="Help Center", font=("Segoe UI Semibold", 20),
            foreground="#173d32",
        ).pack(anchor="w")
        ttk.Label(
            header,
            text="Guidance for setup, package authoring, native assets, and recovery.",
            foreground="#52635c",
        ).pack(anchor="w", pady=(3, 0))

        body = ttk.Panedwindow(outer, orient="horizontal")
        body.pack(fill="both", expand=True)
        navigation = ttk.Frame(body, padding=(0, 0, 14, 0))
        article = ttk.Frame(body, padding=(18, 4, 4, 4))
        body.add(navigation, weight=2)
        body.add(article, weight=5)

        ttk.Label(navigation, text="Search help", style="FieldLabel.TLabel").pack(
            anchor="w",
        )
        self.query = tk.StringVar()
        search = ttk.Entry(navigation, textvariable=self.query)
        search.pack(fill="x", pady=(6, 12))
        self.query.trace_add("write", lambda *_args: self._populate())
        self.results = tk.Listbox(
            navigation, exportselection=False, activestyle="none", borderwidth=0,
            highlightthickness=1, highlightbackground="#d7e0dc",
            selectbackground="#dcefe3", selectforeground="#173d32",
            font=("Segoe UI", 10),
        )
        result_scroll = ttk.Scrollbar(
            navigation, orient="vertical", command=self.results.yview,
        )
        self.results.configure(yscrollcommand=result_scroll.set)
        self.results.pack(side="left", fill="both", expand=True)
        result_scroll.pack(side="right", fill="y")
        self.results.bind("<<ListboxSelect>>", self._select_topic)

        self.category = tk.StringVar(value="START HERE")
        self.heading = tk.StringVar(value="Select a help topic")
        self.summary = tk.StringVar(value="")
        ttk.Label(
            article, textvariable=self.category, foreground="#1f7f42",
            font=("Segoe UI Semibold", 9),
        ).pack(anchor="w")
        ttk.Label(
            article, textvariable=self.heading, font=("Segoe UI Semibold", 18),
            foreground="#173d32",
        ).pack(anchor="w", pady=(4, 2))
        ttk.Label(
            article, textvariable=self.summary, foreground="#52635c",
            wraplength=650, justify="left",
        ).pack(anchor="w", pady=(0, 12))
        ttk.Separator(article).pack(fill="x", pady=(0, 12))
        article_frame = ttk.Frame(article)
        article_frame.pack(fill="both", expand=True)
        self.body = tk.Text(
            article_frame, wrap="word", relief="flat", borderwidth=0,
            background="#ffffff", foreground="#24332d", font=("Segoe UI", 10),
            padx=4, pady=4, spacing1=3, spacing3=8, state="disabled",
        )
        article_scroll = ttk.Scrollbar(
            article_frame, orient="vertical", command=self.body.yview,
        )
        self.body.configure(yscrollcommand=article_scroll.set)
        self.body.pack(side="left", fill="both", expand=True)
        article_scroll.pack(side="right", fill="y")

    def _populate(self) -> None:
        self.visible_topics = search_help_topics(self.query.get())
        self.results.delete(0, "end")
        self.topic_items.clear()
        for index, topic in enumerate(self.visible_topics):
            label = f"{topic.category}\n   {topic.title}"
            self.results.insert("end", label)
            self.topic_items[str(index)] = topic
        if not self.visible_topics:
            self.category.set("NO RESULTS")
            self.heading.set("No matching help topics")
            self.summary.set("Try a shorter search such as ‘RPF’, ‘install’, or ‘logs’.")
            self._set_body("")
            return
        selected_index = 0
        if self.initial_topic:
            for index, topic in enumerate(self.visible_topics):
                if topic.key == self.initial_topic:
                    selected_index = index
                    break
            self.initial_topic = None
        self.results.selection_set(selected_index)
        self.results.see(selected_index)
        self._show_topic(self.visible_topics[selected_index])

    def show_topic(self, key: str) -> None:
        """Navigate an existing embedded help center to a known article."""
        self.initial_topic = key
        self.query.set("")
        self._populate()

    def _select_topic(self, _event: object | None = None) -> None:
        selection = self.results.curselection()
        if selection and selection[0] < len(self.visible_topics):
            self._show_topic(self.visible_topics[selection[0]])

    def _show_topic(self, topic: HelpTopic) -> None:
        self.category.set(topic.category.upper())
        self.heading.set(topic.title)
        self.summary.set(topic.summary)
        self._set_body(topic.body)

    def _set_body(self, value: str) -> None:
        self.body.configure(state="normal")
        self.body.delete("1.0", "end")
        self.body.insert("1.0", value)
        self.body.configure(state="disabled")
