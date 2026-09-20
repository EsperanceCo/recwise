"""Lets `python -m recwise` launch the desktop app -- this is also the
entry point the packaged Windows/macOS/Debian installer runs (see
pyproject.toml's [tool.briefcase] config, main_module = recwise).
"""

from __future__ import annotations

from recwise.desktop_app import main

if __name__ == "__main__":
    raise SystemExit(main())
