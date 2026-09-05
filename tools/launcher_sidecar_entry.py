"""Frozen service entrypoint; a Tk import is a packaging defect, not a fallback."""
import importlib.abc
import sys


class NoTk(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in {"tkinter", "_tkinter"} or fullname == "PIL.ImageTk":
            raise ImportError("Tkinter is not part of the React Launcher")


sys.meta_path.insert(0, NoTk())

from allin1.desktop_host import main

if __name__ == "__main__":
    main()
