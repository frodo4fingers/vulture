from __future__ import annotations

import random

import pytest
from pydantic import ValidationError

from vulture.breaks import (
    BreakActivitySelector,
    EyeBreakActivity,
    HydrationBreakActivity,
    MovementBreakActivity,
    ResetBreakActivity,
    eye_break_activities,
    eye_break_message,
    hydration_break_activities,
    hydration_break_message,
    movement_break_activities,
    movement_break_message,
    reset_break_activities,
    reset_break_message,
)
from vulture.models import BreakPreferences


def test_default_break_preferences_include_every_lite_channel() -> None:
    preferences = BreakPreferences()

    assert movement_break_activities(preferences) == (
        MovementBreakActivity.POSITION_CHANGE,
        MovementBreakActivity.STAND,
        MovementBreakActivity.WALK,
        MovementBreakActivity.GUIDED_EXERCISE,
    )
    assert eye_break_activities(preferences) == (
        EyeBreakActivity.DISTANCE,
        EyeBreakActivity.NATURE,
        EyeBreakActivity.BLINK,
        EyeBreakActivity.EYES_CLOSED,
    )
    assert hydration_break_activities(preferences) == (
        HydrationBreakActivity.WATER,
    )
    assert reset_break_activities(preferences) == (
        ResetBreakActivity.TEA_OR_COFFEE,
        ResetBreakActivity.WALK,
        ResetBreakActivity.BREATHE,
        ResetBreakActivity.OFFSCREEN,
        ResetBreakActivity.GUIDED_EXERCISE,
    )


def test_break_selector_shuffles_without_replacement() -> None:
    activities = reset_break_activities(BreakPreferences())
    selector = BreakActivitySelector(random.Random(7))
    remaining: list[str] = []
    last_id: str | None = None
    selected_ids: list[str] = []

    for _ in activities:
        selected, remaining = selector.choose(
            activities,
            remaining,
            last_id,
        )
        selected_ids.append(selected.value)
        last_id = selected.value

    assert len(set(selected_ids)) == len(activities)
    selected, _remaining = selector.choose(
        activities,
        remaining,
        last_id,
    )
    assert selected.value != last_id


def test_single_water_activity_is_the_recurring_exception() -> None:
    activities = hydration_break_activities(BreakPreferences())
    selector = BreakActivitySelector(random.Random(3))

    first, remaining = selector.choose(activities, [], None)
    second, _remaining = selector.choose(
        activities,
        remaining,
        first.value,
    )

    assert first is second is HydrationBreakActivity.WATER


def test_020_activity_mix_is_preserved_until_user_opts_in() -> None:
    preferences = BreakPreferences.model_validate(
        {
            "enabled": True,
            "movement_reminders_enabled": True,
            "movement_interval_minutes": 30,
            "movement_duration_minutes": 2,
            "away_reset_minutes": 2,
            "suggest_position_change": True,
            "suggest_standing": True,
            "suggest_walking": True,
            "suggest_guided_exercise": True,
            "eye_reminders_enabled": True,
            "eye_interval_minutes": 20,
            "eye_duration_seconds": 20,
            "suggest_blinking": False,
            "suggest_closed_eye_rest": False,
        }
    )

    assert movement_break_activities(preferences) == (
        MovementBreakActivity.POSITION_CHANGE,
        MovementBreakActivity.STAND,
        MovementBreakActivity.WALK_OR_DRINK,
        MovementBreakActivity.GUIDED_EXERCISE,
    )
    assert eye_break_activities(preferences) == (
        EyeBreakActivity.DISTANCE,
    )
    assert not preferences.hydration_reminders_enabled
    assert not preferences.reset_reminders_enabled


def test_enabled_break_preferences_require_usable_channels() -> None:
    with pytest.raises(ValidationError):
        BreakPreferences(
            movement_reminders_enabled=False,
            eye_reminders_enabled=False,
            hydration_reminders_enabled=False,
            reset_reminders_enabled=False,
        )

    with pytest.raises(ValidationError):
        BreakPreferences(
            suggest_position_change=False,
            suggest_standing=False,
            suggest_walking=False,
            suggest_guided_exercise=False,
        )

    with pytest.raises(ValidationError):
        BreakPreferences(
            suggest_tea_or_coffee=False,
            suggest_reset_walking=False,
            suggest_breathing_reset=False,
            suggest_offscreen_reset=False,
            suggest_reset_guided_exercise=False,
        )

    disabled = BreakPreferences(
        enabled=False,
        movement_reminders_enabled=False,
        eye_reminders_enabled=False,
        hydration_reminders_enabled=False,
        reset_reminders_enabled=False,
        suggest_position_change=False,
        suggest_standing=False,
        suggest_walking=False,
        suggest_guided_exercise=False,
        suggest_tea_or_coffee=False,
        suggest_reset_walking=False,
        suggest_breathing_reset=False,
        suggest_offscreen_reset=False,
        suggest_reset_guided_exercise=False,
    )
    assert not disabled.enabled


def test_break_messages_match_every_imported_pause_type() -> None:
    assert "easy walk" in movement_break_message(
        MovementBreakActivity.WALK,
        3,
    )
    assert "greenery" in eye_break_message(EyeBreakActivity.NATURE, 40)
    assert "five slow, complete blinks" in eye_break_message(
        EyeBreakActivity.BLINK,
        20,
    )
    assert "Do not press or rub" in eye_break_message(
        EyeBreakActivity.EYES_CLOSED,
        20,
    )
    assert "medical guidance" in hydration_break_message(30)
    assert "caffeine is optional" in reset_break_message(
        ResetBreakActivity.TEA_OR_COFFEE,
        5,
    )
    assert "longer than the inhale" in reset_break_message(
        ResetBreakActivity.BREATHE,
        5,
    )
    assert "fully off-screen" in reset_break_message(
        ResetBreakActivity.OFFSCREEN,
        5,
    )
    assert "tea or coffee" in movement_break_message(
        MovementBreakActivity.WALK_OR_DRINK,
        3,
    )
