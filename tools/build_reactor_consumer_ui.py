"""Build ALLIN1's UI composition from the pinned, MIT-licensed Reactor source.

This never copies native/browser dependencies. Run using a clean checkout:
python tools/build_reactor_consumer_ui.py --reactor-root <ReactorV>
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

SOURCE_COMMIT = "ecf49a38a6361a29c0b2b9c97f365f149d3d8149"
RELEASE = "v0.2.0-preview.2"


def build(root: Path, output: Path) -> None:
    def run(*args: str, cwd: Path = root) -> str:
        return subprocess.check_output(args, cwd=cwd, text=True).strip()

    if run("git", "rev-parse", "HEAD") != SOURCE_COMMIT or run("git", "status", "--porcelain", "--untracked-files=no"):
        raise ValueError("Reactor source must be the clean pinned Preview 2 commit")
    pnpm = shutil.which("pnpm")
    if not pnpm:
        raise ValueError("pnpm is required to build ALLIN1's browser UI")
    web = root / "web"
    subprocess.run([pnpm, "install", "--frozen-lockfile"], cwd=web, check=True)
    subprocess.run([pnpm, "run", "build:allin1"], cwd=web, check=True)
    with tempfile.TemporaryDirectory(prefix="allin1-ui-") as temporary:
        stage = Path(temporary)
        for file in (web / "dist-allin1").rglob("*"):
            if not file.is_file():
                continue
            if file.suffix.lower() not in {".html", ".js", ".css", ".png", ".ttf", ".txt"} or file.stat().st_size > 4 * 1024 * 1024:
                raise ValueError(f"Unexpected consumer build output: {file.name}")
            dest = stage / file.relative_to(web / "dist-allin1")
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(file, dest)
        shutil.copyfile(root / "LICENSE", stage / "LICENSE")
        # Resolve licenses from the same restored packages used by this build.
        js = ('const p=require("node:path");const base=p.dirname(require.resolve("react-dom/package.json"));'
              'console.log(JSON.stringify(["react","react-dom","scheduler"].map(name=>'
              '({name,root:p.dirname(require.resolve(name+"/package.json",{paths:[base]}))}))));')
        packages = json.loads(run("node", "-e", js, cwd=web))
        for package in packages:
            shutil.copyfile(Path(package["root"]) / "LICENSE", stage / (package["name"] + "-LICENSE.txt"))
        (stage / "THIRD_PARTY_NOTICES.txt").write_text(
            "ALLIN1 presentation composition, built from GTAV-REACTOR-V " + SOURCE_COMMIT + ".\n"
            "Original Reactor V code: MIT, copyright (c) 2026 MinionEnjoyer; see LICENSE.\n"
            "React, React DOM and Scheduler retain their included MIT notices.\n"
            "Bebas Neue and Oswald retain their SIL Open Font License notices in fonts/.\n"
            "Game artwork and logos are not relicensed by these code licenses.\n", encoding="utf-8")
        (stage / "reactor-ui.json").write_text(json.dumps({
            "schema_version": 1, "profile": "allin1-composition", "owner": "allin1",
            "contains_consumer_content": True, "reactor_release": RELEASE,
        }, indent=2) + "\n", encoding="utf-8")
        files = {path.relative_to(stage).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                 for path in sorted(stage.rglob("*")) if path.is_file()}
        manifest = dict(schema_version=1, profile="allin1-composition", reactor_release=RELEASE,
                        source_repository="https://github.com/MinionEnjoyer/GTAV-REACTOR-V",
                        source_commit=SOURCE_COMMIT, files=files)
        (stage / "allin1-ui.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        # Remove only previously generated files; refuse to clobber untracked extras.
        if output.exists():
            previous = json.loads((output / "allin1-ui.json").read_text(encoding="utf-8"))
            allowed = {*previous["files"], "allin1-ui.json"}
            for file in output.rglob("*"):
                if file.is_file() and file.relative_to(output).as_posix() not in allowed:
                    raise ValueError(f"Unexpected file in generated UI directory: {file}")
            for relative in previous["files"]:
                path = output / relative
                if path.is_file() and relative not in files:
                    path.unlink()
        shutil.copytree(stage, output, dirs_exist_ok=True)
    print(f"Built {len(files)} UI files; no Reactor binaries bundled")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reactor-root", type=Path, required=True)
    options = parser.parse_args()
    build(options.reactor_root.resolve(), Path(__file__).resolve().parents[1] / "data/reactor/allin1-ui")
