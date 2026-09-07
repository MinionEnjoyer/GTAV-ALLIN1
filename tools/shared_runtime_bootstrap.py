"""Isolated shared-runtime entrypoint. No pip, user site, or checkout imports.

The manifest detects damage/build mixing; it is not a publisher signature.
Interpreter and native extensions are unmodified upstream distributions.
"""
from pathlib import Path
import hashlib
import json
import sys


def verify(runtime):
    if not sys.flags.isolated or not sys.dont_write_bytecode:
        raise ValueError("Shared runtime requires isolated, read-only Python flags")
    manifest_path = runtime / "runtime-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (type(manifest.get("schema_version")) is not int or manifest["schema_version"] != 1
            or not isinstance(manifest.get("files"), dict) or not manifest['files']):
        raise ValueError("Invalid shared runtime manifest")
    files = {}
    for path in runtime.rglob("*"):
        if path.is_symlink() or path.is_junction():
            raise ValueError("Links are not allowed in the shared runtime")
        if path.is_file() and path != manifest_path:
            if path.stat().st_nlink > 1:
                raise ValueError("Hard links are not allowed in the shared runtime")
            files[path.relative_to(runtime).as_posix()] = path
    if set(files) != set(manifest["files"]):
        raise ValueError("Shared runtime files do not exactly match this build")
    for name, path in files.items():
        with path.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != manifest["files"][name]:
                raise ValueError("Shared runtime checksum mismatch: " + name)


def main():
    runtime = Path(__file__).absolute().parent
    for path in (runtime, *runtime.parents):
        if path.is_symlink() or path.is_junction():
            raise ValueError("Shared runtime cannot be loaded through a link")
    verify(runtime)
    if not Path(sys.executable).samefile(runtime / "python.exe"):
        raise ValueError("Shared runtime requires its bundled interpreter")
    sys._allin1_packaged_root = str(runtime.parent)
    mode = sys.argv.pop(1)
    if mode == "service":
        from allin1.desktop_host import main as service
        service()
    elif mode == "preview":
        from allin1.weapon_preview_worker import main as preview
        preview(sys.argv[1])
    elif mode == "cli":
        from allin1.launcher_cli import main as cli
        raise SystemExit(cli(sys.argv[1:]))
    else:
        raise ValueError("Unknown shared-runtime operation")


if __name__ == "__main__":
    main()
