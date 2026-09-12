# Launcher development and validation

Target: 0.6.5 — React/Tauri v2, Python domain services, and a separate C# Story
Mode runtime. The source CLI remains; GUI aliases route to Tauri only.

## Setup

Use Windows for native desktop validation. Install the Node/pnpm versions from
`desktop/package.json`, Rust/MSVC, WebView2, Visual Studio Build Tools, and .NET
8 for native/.NET helpers and paired game components.

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -e ".[test]"
pnpm --dir desktop install --frozen-lockfile
pnpm --dir desktop tauri dev
```

The development broker uses this checkout's `.venv/Scripts/python.exe`.
Packaged Launcher services require the verified shared `runtime/` and
`resources/` layout; a development executable is neither distributable nor
installer/lifecycle evidence.

Never exercise write tests against a real GTA/user tree. Use the synthetic
fixtures: they allocate disposable directories, include user-data canaries and
do not execute fixture binaries. An interactive development window is not the
same isolation boundary; use preview state when inspecting it.

## Automated gates

```powershell
.venv/Scripts/python.exe -m pytest tests --cov=allin1
.venv/Scripts/python.exe tools/react_release_harness.py --product launcher
pnpm --dir desktop build
cargo test --locked --manifest-path desktop/src-tauri/Cargo.toml
dotnet test script/tests/ALLIN1.Tests.csproj -c Release
```

The Python suite retains its 91% coverage threshold; a required skip is
untested, not a pass. Native/runtime results do not establish packaged GUI or
live-game behavior. Separate products are outside ALLIN1 qualification.

For the source-only, evidence-producing aggregate check in a prepared checkout:

```powershell
.venv/Scripts/python.exe tools/hardening_harness.py
```

The default profile skips Windows-tool and RpfPatcher key-context tests.
`--real-tools` is only for a prepared Windows runner with those tools; neither
profile builds a public release, runs an installer, or launches GTA. See the
[hardening harness](hardening-harness.md) for its evidence and status rules.

For explicitly selected sibling SDK source:

```powershell
.venv/Scripts/python.exe tools/react_release_harness.py --product both --sdk-source ../ALLIN1-SDK
.venv/Scripts/python.exe tools/verify_sdk_portable_contract.py --sdk-source ../ALLIN1-SDK
```

This is development-only coordination; shipped applications do not import the
sibling checkout. `--full-python` adds each full coverage suite. The [React
harness](react-release-harness.md) defines the source-bound evidence, native
requirements, and limits of its PASS.

## Documentation checks

```powershell
.venv/Scripts/python.exe tools/documentation_audit.py
.venv/Scripts/python.exe tools/documentation_audit.py --product sdk --sdk-source ../ALLIN1-SDK
```

`docs/catalog.json` classifies project-owned docs. The audit checks inventory
coverage, local links/headings, and source-derived references; it neither fetches
external URLs nor approves claims from a link alone. Historical records need a
prominent notice and never qualify new binaries.

Generate reference text for review, then update the checked-in document:

```powershell
.venv/Scripts/python.exe tools/documentation_audit.py --render cli
.venv/Scripts/python.exe tools/documentation_audit.py --render config
```

The generator only inspects the command tree/default configuration: it does not
run install, repair, or launch commands. Update Help and the relevant manual
with behavior changes, and keep the reference inventory current in tests.

## Architecture rules

React owns drafts and presentation; Rust owns fixed native-dialog/process
capabilities; Python owns validation, package semantics, guarded writes, and
receipts. Do not grant the WebView raw shell/file-system access or move
destructive logic into React. The SDK follows the same separation.

Async UI needs loading/error, stale-result, and dirty-state tests; do not reload
the app while work is unresolved. Archive/rollback writers need disposable
containment and outside-root canaries.

The [release guide](release-0.6.5.md) is the current qualification checklist.
