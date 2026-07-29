# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
import sys
import tomllib

from PyInstaller.utils.hooks import collect_dynamic_libs


PROJECT_ROOT = Path(SPEC).resolve().parent.parent
SOURCE_ROOT = PROJECT_ROOT / "src"
RESOURCE_ROOT = SOURCE_ROOT / "vulture" / "resources"
PUBLIC_DOCUMENTS = [
    PROJECT_ROOT / "LICENSE",
    PROJECT_ROOT / "README.md",
    PROJECT_ROOT / "THIRD_PARTY_NOTICES.md",
]
with (PROJECT_ROOT / "pyproject.toml").open("rb") as project_file:
    VERSION = tomllib.load(project_file)["project"]["version"]

mediapipe_binaries = collect_dynamic_libs("mediapipe")

a = Analysis(
    [str(SOURCE_ROOT / "vulture" / "__main__.py")],
    pathex=[str(SOURCE_ROOT)],
    binaries=mediapipe_binaries,
    datas=[
        (str(RESOURCE_ROOT), "vulture/resources"),
        *((str(document), ".") for document in PUBLIC_DOCUMENTS),
    ],
    hiddenimports=[
        "mediapipe.tasks.c",
        "mediapipe.tasks.c.libmediapipe",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

executable_options = {
    "console": False,
}
if sys.platform == "win32":
    executable_options = {
        "console": True,
        "hide_console": "hide-early",
    }

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Vulture",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    **executable_options,
)
bundle = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Vulture",
)

if sys.platform == "darwin":
    app = BUNDLE(
        bundle,
        name="Vulture.app",
        bundle_identifier="org.vulture.posture",
        version=VERSION,
        info_plist={
            "CFBundleDisplayName": "Vulture",
            "CFBundleName": "Vulture",
            "NSCameraUsageDescription": (
                "Vulture analyzes posture locally and immediately discards "
                "camera frames."
            ),
            "NSCameraUseContinuityCameraDeviceType": True,
            "NSHighResolutionCapable": True,
        },
    )
