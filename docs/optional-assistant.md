# Optional SDK assistant

The ALLIN1 assistant is a separate, opt-in component for natural-language package installation
and diagnostics. It is not part of GTA V, never runs inside ScriptHookVDotNet, and is disabled
until a user explicitly selects and saves an assistant mode.

## Modes

| Mode | Files managed by ALLIN1 | Intended use |
|---|---:|---|
| Disabled | None in use | Default state |
| Managed Qwen install | Runtime and one model under `%LOCALAPPDATA%\ALLIN1\Assistant\component` | Simplest offline setup |
| Existing local GGUF model | None | Advanced users who already have a Windows runtime and model |
| Compatible model API | None | A local server or user-selected provider |

ALLIN1 stores only an API-key **environment-variable name**, never the secret itself. Removing a
managed install removes only managed component data and runtime logs. Configuration and user-owned model
files are preserved.

## Hardware preflight

Managed packs target a CPU-capable x64 Windows runtime; a dedicated GPU is not required. Before a
download or package install, ALLIN1 checks:

- 64-bit Windows architecture;
- total physical memory against the pack manifest;
- free disk space for the archive, extracted component, and verification/rollback headroom;
- logical CPU threads;
- AVX and AVX2 acceleration when Windows exposes those processor features.

Architecture, minimum RAM, and disk failures block installation. Lower recommended RAM/thread
counts and missing acceleration are shown as cautions. The UI recommends the low pack unless the
PC has at least 24 GB RAM and eight logical threads.

Planning defaults are 8 GB minimum/12 GB recommended for `low`, and 16 GB minimum/24 GB
recommended for `recommended`. A verified package manifest can raise or lower its own RAM values.

## Managed upstream install

Qwen is not packaged in the ALLIN1 launcher, SDK, repository, or release ZIP. The optional installer
downloads two independent, revision-pinned upstream artifacts:

- the official llama.cpp Windows x64 CPU runtime from its GitHub release;
- a Qwen3.5 Q4_K_M GGUF conversion pinned by revision, size, and SHA-256, with the
  official Qwen base-model repository and license recorded separately.

The `low` choice installs Qwen3.5 4B; `recommended` installs Qwen3.5 9B. Exact byte sizes and SHA-256
digests are pinned in the launcher. Runtime and model licenses are fetched from the same pinned
upstream revisions and retained with the install. Redirected or mutated content cannot activate
because every file must match its expected size and digest.

Downloads stage under the managed assistant root rather than the Windows temporary directory. A
new install is fully validated before an existing working component is moved aside, and the old
component is restored if activation fails. The installed layout is:

```text
assistant-package.json
checksums.json
runtime/llama-server.exe
runtime/<required llama.cpp DLLs>
models/Qwen3.5-<size>-Q4_K_M.gguf
licenses/llama.cpp-LICENSE.txt
licenses/Qwen-LICENSE.txt
```

`assistant-package.json` records source URLs, revisions, and digests. `checksums.json` covers every
installed file. Routine status checks validate the layout and executable/GGUF headers; the Verify
command streams and hashes the complete install. Advanced users may still import a separately
obtained checksum-complete assistant package, but ALLIN1 does not distribute Qwen that way.

## Console/API lifecycle

```text
allin1 assistant status
allin1 assistant hardware-check --profile low
allin1 assistant install-qwen --profile low --yes
allin1 assistant install-package <archive.zip> --yes
allin1 assistant configure --mode managed_local --profile low --yes
allin1 assistant prompt How should I inspect this vehicle package?
allin1 assistant verify
allin1 assistant uninstall --yes
```

Every command accepts `--root` for testing or managed deployments. Installation does not enable
the component automatically. In the standalone SDK's persistent bottom console, use:

```text
assistant status
assistant context How should I inspect this vehicle package?
assistant prompt How should I inspect this vehicle package?
assistant stop
```

Managed/custom local modes start a llama.cpp-compatible server on a random loopback-only port and
retain it for later prompts in the same SDK process. Compatible API mode sends the same chat
request to the configured endpoint. Prompts are capped, time-limited, and read-only. The host
automatically supplies the current repository role and dirty state, available launcher/SDK/package
roots, validated manifest metadata, verified GTA path, allowed advisory/planning mode, and a focused
set of exact live SDK command contracts. `assistant context` displays this evidence without starting
the model.

The permanent policy forbids manual copying for managed packages and prevents request-specific
guidance from removing that rule. Responses must use the structured advisory schema. Deterministic
SDK code rejects invented operations and withholds manual-copy or destructive guidance, corrects
operation risk from the live Agent API catalog, and marks every recommendation as unexecuted.
Qwen still receives no filesystem or install authority; separately acknowledged typed SDK commands
remain responsible for validation, receipts, ownership, backups, writes, and rollback.
