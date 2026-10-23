# -*- mode: python ; coding: utf-8 -*-
# PyInstaller: carpeta dist/Cirno con Cirno.exe (sin consola) y los recursos.

a = Analysis(
    ["launcher.py"],
    pathex=["."],
    binaries=[],
    datas=[("cirno/assets", "cirno/assets")],
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "numpy", "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickWidgets", "PySide6.QtNetwork",
              "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets", "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtXml",
              "PySide6.QtDBus", "PySide6.QtConcurrent", "PySide6.QtPrintSupport", "PySide6.QtSvg", "PySide6.QtSvgWidgets",
              "PySide6.QtQuick3D", "PySide6.QtQuickControls2", "PySide6.QtQuickTest"],
    noarchive=False,
)


def _sobra(destino: str) -> bool:
    """Lastre de Qt que una app de widgets no usa: OpenGL por software (20 MB) y traducciones."""
    d = destino.replace("\\", "/").lower()
    return "opengl32sw" in d or "/translations/" in d or d.startswith("numpy")


a.binaries = [b for b in a.binaries if not _sobra(b[0])]
a.datas = [d for d in a.datas if not _sobra(d[0])]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Cirno",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon="cirno/assets/cirno.ico",
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="Cirno",
)
