# Contributing to ALLIN1

Thanks for helping improve ALLIN1. The project supports GTA V Story Mode only;
changes must not add GTA Online behavior, redistribute proprietary game assets,
or weaken package ownership and integrity checks.

## Set up a development checkout

Clone with submodules because the Windows RPF toolchain uses the pinned
CodeWalker source:

```powershell
git clone --recurse-submodules https://github.com/MinionEnjoyer/GTAV-ALLIN1.git
git clone https://github.com/MinionEnjoyer/ALLIN1-SDK.git
cd GTAV-ALLIN1
install.bat
pnpm --dir desktop install --frozen-lockfile
```

CodeWalker is an independently licensed submodule. Keep changes to it in its
own upstream repository; update the pinned commit here only in a reviewed pull
request. Keep the SDK checkout beside this repository when running preview and
cross-product tests; CI pins an exact SDK commit for reproducibility.

## Make a focused change

- Branch from `main` and keep unrelated formatting or generated-output changes
  out of the commit.
- Do not commit local game paths, logs, configuration, credentials, extracted
  game files, or third-party mod archives.
- Preserve the fail-closed installer, receipt ownership, path-containment and
  rollback behavior.
- Keep experimental gameplay and population-injector work off `main`; that work
  belongs on an explicitly experimental branch until it meets release gates.
- Add or update tests and user documentation with behavior changes.

## Validate before opening a pull request

Run the canonical source checks from the repository root:

```powershell
.\test-all.ps1
.\.venv\Scripts\python.exe tools\react_release_harness.py --product launcher
```

The developer guide documents targeted Python, React, Rust, C# and Windows
toolchain commands. A passing source harness is evidence, not live-game or
installer qualification.

## Pull requests

Describe the user-visible behavior, safety boundaries, tests run and anything
not tested. Do not attach copyrighted GTA files or third-party mod payloads.
By contributing, you agree that your contribution is licensed under the
project's GPL-3.0-or-later license.
