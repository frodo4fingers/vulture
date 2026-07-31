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


def test_legacy_sedentary_break_settings_keep_prior_behavior() -> None:
    data = AppData.model_validate(
        {
            "schema_version": 1,
            "alert_policy": {
                "sedentary_break_minutes": 75,
            },
        }
    )

    assert data.break_preferences.movement_interval_minutes == 75
    assert not data.break_preferences.eye_reminders_enabled
    assert not data.break_preferences.suggest_position_change
    assert not data.break_preferences.suggest_standing
    assert not data.break_preferences.suggest_walking
    assert data.break_preferences.suggest_guided_exercise
