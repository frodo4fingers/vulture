from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

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
    assert not data.break_preferences.hydration_reminders_enabled
    assert not data.break_preferences.reset_reminders_enabled
    assert not data.break_preferences.suggest_nature_view
    assert not data.break_preferences.legacy_walk_includes_drinks


def test_existing_break_settings_do_not_enable_new_channels() -> None:
    data = AppData.model_validate(
        {
            "schema_version": 1,
            "break_preferences": {
                "movement_interval_minutes": 30,
                "eye_interval_minutes": 20,
            },
        }
    )

    assert not data.break_preferences.hydration_reminders_enabled
    assert not data.break_preferences.reset_reminders_enabled
    assert not data.break_preferences.suggest_nature_view
    assert data.break_preferences.legacy_walk_includes_drinks


def test_recent_exercise_seeds_non_repeating_upgrade_state() -> None:
    data = AppData.model_validate(
        {
            "schema_version": 1,
            "recent_exercise_ids": [
                "shoulder-shrug",
                "wrist-side-bend",
            ],
        }
    )

    assert data.last_exercise_id == "wrist-side-bend"


def test_settings_from_a_newer_version_still_load(tmp_path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "interface_language": "en",
                "notification_position": "bottom_center",
                "break_preferences": {
                    "movement_interval_minutes": 45,
                    "notification_sound": "chime",
                },
            }
        ),
        encoding="utf-8",
    )

    data = AppDataStore(path).load()

    assert data.interface_language == "en"
    assert data.break_preferences.movement_interval_minutes == 45


def test_unknown_settings_are_dropped_on_the_next_save(tmp_path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps({"schema_version": 1, "notification_position": "bottom_center"}),
        encoding="utf-8",
    )
    store = AppDataStore(path)

    store.save(store.load())

    assert "notification_position" not in json.loads(path.read_text(encoding="utf-8"))


def test_unknown_fields_remain_rejected_outside_stored_settings() -> None:
    with pytest.raises(ValidationError):
        AppData.model_validate(
            {"schema_version": 1, "notification_position": "bottom_center"}
        )
