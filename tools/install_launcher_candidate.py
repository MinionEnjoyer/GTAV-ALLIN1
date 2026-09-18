"""Install one checksum-verified Launcher candidate without launching it."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from allin1.launcher_installation import install_launcher_archive


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True, type=Path,
                        help="Explicit Launcher portable ZIP to install.")
    parser.add_argument("--destination", required=True, type=Path,
                        help="Explicit dedicated Launcher installation directory.")
    args = parser.parse_args()
    result = install_launcher_archive(args.archive, args.destination)
    print(json.dumps({"root": str(result.root),
                      "backup": None if result.backup is None else str(result.backup),
                      "deployed": list(result.deployed),
                      "preserved": list(result.preserved)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
