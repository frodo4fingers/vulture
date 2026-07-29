from __future__ import annotations

from pathlib import Path
import tomllib

from vulture import __version__


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = PROJECT_ROOT / "packaging" / "vulture.spec"
WORKFLOW_PATH = (
    PROJECT_ROOT / ".github" / "workflows" / "build-and-release.yml"
)


def test_desktop_spec_contains_all_platform_outputs() -> None:
    spec = SPEC_PATH.read_text(encoding="utf-8")

    assert 'name="Vulture"' in spec
    assert '"console": False' in spec
    assert '"console": True' in spec
    assert '"hide_console": "hide-early"' in spec
    assert 'if sys.platform == "darwin":' in spec
    assert 'name="Vulture.app"' in spec
    assert '"NSCameraUsageDescription"' in spec
    assert '"NSCameraUseContinuityCameraDeviceType"' in spec


def test_desktop_spec_bundles_private_runtime_assets() -> None:
    spec = SPEC_PATH.read_text(encoding="utf-8")

    assert '"vulture/resources"' in spec
    assert 'PROJECT_ROOT / "LICENSE"' in spec
    assert 'PROJECT_ROOT / "README.md"' in spec
    assert 'PROJECT_ROOT / "THIRD_PARTY_NOTICES.md"' in spec
    assert '"mediapipe.tasks.c"' in spec
    assert '"mediapipe.tasks.c.libmediapipe"' in spec


def test_project_and_application_versions_match() -> None:
    with (PROJECT_ROOT / "pyproject.toml").open("rb") as project_file:
        project_version = tomllib.load(project_file)["project"]["version"]

    assert __version__ == project_version


def test_release_workflow_builds_and_checks_every_platform() -> None:
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")

    assert "ubuntu-latest" in workflow
    assert "windows-latest" in workflow
    assert "macos-15" in workflow
    assert "macos-15-intel" in workflow
    assert "dist/Vulture/Vulture --check-runtime" in workflow
    assert r"dist\Vulture\Vulture.exe --check-runtime" in workflow
    assert (
        "dist/Vulture.app/Contents/MacOS/Vulture --check-runtime"
        in workflow
    )
    assert "sha256sum Vulture-* > SHA256SUMS.txt" in workflow
    assert 'gh release create "${GITHUB_REF_NAME}"' in workflow
