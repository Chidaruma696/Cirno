"""Entrada para PyInstaller (evita los imports relativos de cirno/__main__.py)."""

import sys

from cirno.cli import main

sys.exit(main())
