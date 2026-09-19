# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_submodules


hiddenimports = collect_submodules("auditor_bola")

datas = [
    ("assets/aegis-auditor.ico", "assets"),
    ("assets/aegis-auditor.svg", "assets"),
    ("config/plantilla.json", "config"),
    ("docs/REQUISITOS_USO.md", "docs"),
    ("docs/ARQUITECTURA_DOS_PILARES.md", "docs"),
    ("docs/articulo/README.md", "docs/articulo"),
]

a = Analysis(
    ["aegis_auditor.py"],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="AegisAuditor",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="assets/aegis-auditor.ico",
    version="installer/version_info.txt",
)
