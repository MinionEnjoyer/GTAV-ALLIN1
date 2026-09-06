"""Frozen worker entry point (no game or desktop startup)."""
import sys
from allin1.weapon_preview_worker import main

if __name__ == '__main__':
    main(sys.argv[1])
