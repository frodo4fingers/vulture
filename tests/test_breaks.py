from __future__ import annotations

import pytest
from pydantic import ValidationError

from vulture.breaks import (
    EyeBreakActivity,
    MovementBreakActivity,
    eye_break_activities,
    eye_break_message,
    movement_break_activities,
    movement_break_message,
    next_eye_break_activity,
    next_movement_break_activity,
)
from vulture.models import BreakPreferences


def test_default_break_preferences_offer_varied_prompts() -> None:
    preferences = BreakPreferences()

    assert movement_break_activities(preferences) == (
        MovementBreakActivity.POSITION_CHANGE,
        MovementBreakActivity.STAND,
        MovementBreakActivity.WALK,
        MovementBreakActivity.GUIDED_EXERCISE,
    )
    assert eye_break_activities(preferences) == (
        EyeBreakActivity.DISTANCE,
        EyeBreakActivity.BLINK,
        EyeBreakActivity.EYES_CLOSED,
    )
    assert (
        next_movement_break_activity(preferences, 4)
        is MovementBreakActivity.POSITION_CHANGE
    )
    assert (
        next_eye_break_activity(preferences, 3)
        is EyeBreakActivity.DISTANCE
    )


def test_enabled_break_preferences_require_a_usable_channel() -> None:
    with pytest.raises(ValidationError):
        BreakPreferences(
            movement_reminders_enabled=False,
            eye_reminders_enabled=False,
        )

    with pytest.raises(ValidationError):
        BreakPreferences(
            suggest_position_change=False,
            suggest_standing=False,
            suggest_walking=False,
            suggest_guided_exercise=False,
        )

    disabled = BreakPreferences(
        enabled=False,
        movement_reminders_enabled=False,
        eye_reminders_enabled=False,
        suggest_position_change=False,
        suggest_standing=False,
        suggest_walking=False,
        suggest_guided_exercise=False,
    )
    assert not disabled.enabled


def test_break_messages_match_the_selected_activity() -> None:
    movement = movement_break_message(
        MovementBreakActivity.WALK,
        3,
        eye_message="Look into the distance.",
    )
    assert "tea or coffee" in movement
    assert "Look into the distance" in movement

    assert "five slow, complete blinks" in eye_break_message(
        EyeBreakActivity.BLINK,
        20,
    )
    assert "Do not press or rub" in eye_break_message(
        EyeBreakActivity.EYES_CLOSED,
        20,
    )
