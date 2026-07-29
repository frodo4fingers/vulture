from __future__ import annotations

from vulture.models import AppData, CameraDescriptor, SetupProfile
from vulture.storage import AppDataStore


def test_settings_round_trip(tmp_path) -> None:
    path = tmp_path / "settings.json"
    store = AppDataStore(path)
    setup = SetupProfile(
        name="Laptop",
        camera=CameraDescriptor(
            stable_id="/dev/video0",
            display_name="Laptop camera",
            locator="/dev/video0",
        ),
    )
    data = AppData(active_setup_id=setup.id, setups=[setup])

    store.save(data)
    loaded = store.load()
    assert loaded == data
