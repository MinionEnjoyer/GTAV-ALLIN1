# Launcher development and validation

Target: 0.6.4, React in Tauri v2, Python domain services and a separate C# Story
Mode runtime. The source CLI remains; GUI aliases route to Tauri only.

## Setup

Use Windows for native desktop validation. Install the Node/pnpm versions in
`desktop/package.json`, Rust/MSVC, WebView2 and Visual Studio Build Tools; .NET 8
is needed to rebuild native/.NET helpers and the paired game components.

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -e ".[test]"
pnpm --dir desktop install --frozen-lockfile
pnpm --dir desktop tauri dev
```

The development broker currently uses `.venv/Scripts/python.exe` under this
checkout. The release-side broker expects a frozen service, but the Launcher
bundle pipeline is not complete. Do not publish its bare development executable.

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

Coverage remains 91% and skipped required tests are untested. `tests/` contains
the ALLIN1 product suite, including generic package and weapon integration.
Suppressors Enhanced, the weapon pack bundle, GTA VR and FPV are separate
projects, not ALLIN1 release components. Their results cannot qualify ALLIN1.
Native runtime tests are not evidence that GTA was launched or rendered correctly.

The repository-hosted Suppressors Enhanced checks are retained independently:

```powershell
.venv/Scripts/python.exe -m pytest mods/realistic-suppressors/tests/test_package_contract.py
dotnet test mods/realistic-suppressors/tests/RealisticSuppressors.Tests.csproj -c Release
```

These checks run in their own CI workflow and are not prerequisites for an
ALLIN1 build. Separating ownership does not resolve the mod's stale 1.1.0 archive
versus staged-DLL mismatch; that remains work for its independent 1.2.1 release.

For explicitly selected sibling SDK source:

```powershell
.venv/Scripts/python.exe tools/react_release_harness.py --product both --sdk-source ../ALLIN1-SDK
.venv/Scripts/python.exe tools/verify_sdk_portable_contract.py --sdk-source ../ALLIN1-SDK
```

This is development-only coordination; neither shipped application imports the
sibling checkout. The harness enables SDK native React cases, requires pinned
Blender and records fresh source-bound reports. `--full-python` adds each full
coverage suite. Read [harness scope](react-release-harness.md) before interpreting
a PASS. The source-retirement check is separate from packaged/live qualification.

## Documentation checks

```powershell
.venv/Scripts/python.exe tools/documentation_audit.py
.venv/Scripts/python.exe tools/documentation_audit.py --product sdk --sdk-source ../ALLIN1-SDK
```

`docs/catalog.json` classifies project-owned docs. The audit checks coverage of
the inventory, local links/headings and source-derived references. It does not
fetch external URLs or approve factual claims merely because a link exists.
Historical records require a prominent notice and never qualify new binaries.

Generate reference text for review, then update the checked-in document:

```powershell
.venv/Scripts/python.exe tools/documentation_audit.py --render cli
.venv/Scripts/python.exe tools/documentation_audit.py --render config
```

The generator only inspects the command tree/default configuration. It does not
run install/repair/launch commands. Update user-facing Help and the relevant
manual when behavior changes; tests must keep the reference inventory current.

## Architecture rules

React owns drafts and presentation. Rust owns fixed native-dialog/process
capabilities. Python owns validation, package semantics, guarded writes and
receipts. Do not add raw shell/file-system WebView privileges or move destructive
logic into React. The SDK keeps the same separation independently.

New asynchronous UI code needs loading/error states, stale-result and dirty-state
tests, and no automatic whole-app reload during unresolved work. New archive or
rollback writers need disposable containment and outside-root canary tests.

The [release guide](release-0.6.4.md) is the current qualification checklist.
