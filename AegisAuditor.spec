# -*- mode: python ; coding: utf-8 -*-

import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules


hiddenimports = collect_submodules("auditor_bola")

datas = collect_data_files("customtkinter") + [
    ("assets/aegis-auditor.svg", "assets"),
    ("assets/aegis-shield.svg", "assets"),
    ("assets/aegis-auditor-logo.png", "assets"),
    ("LICENSE", "."),
    ("NOTICE", "."),
    ("assets/aegis-auditor.png", "assets"),
    ("docs/REQUISITOS_USO.md", "docs"),
    ("docs/REQUISITOS_APLICACION.md", "docs"),
    ("docs/ARQUITECTURA_DOS_PILARES.md", "docs"),
    ("docs/articulo/README.md", "docs/articulo"),
]

if sys.platform == "win32":
    icon_file = "assets/aegis-auditor.ico"
elif sys.platform == "darwin":
    icon_file = "assets/aegis-auditor.icns"
else:
    icon_file = None

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
    upx=(sys.platform == "win32"),
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_file,
    version=("installer/version_info.txt" if sys.platform == "win32" else None),
)

if sys.platform == "darwin":
    app = BUNDLE(
        exe,
        name="AegisAuditor.app",
        icon=icon_file,
        bundle_identifier="com.aegis.auditor",
        info_plist={
            "CFBundleName": "Aegis Auditor",
            "CFBundleDisplayName": "Aegis Auditor",
            "CFBundleShortVersionString": "1.3.2",
            "CFBundleVersion": "1.3.2",
            "NSHighResolutionCapable": True,
        },
    )