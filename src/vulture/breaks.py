from __future__ import annotations

from enum import StrEnum

from vulture.i18n import tr
from vulture.models import BreakPreferences


class MovementBreakActivity(StrEnum):
    POSITION_CHANGE = "position_change"
    STAND = "stand"
    WALK = "walk"
    GUIDED_EXERCISE = "guided_exercise"


class EyeBreakActivity(StrEnum):
    DISTANCE = "distance"
    BLINK = "blink"
    EYES_CLOSED = "eyes_closed"


def movement_break_activities(
    preferences: BreakPreferences,
) -> tuple[MovementBreakActivity, ...]:
    activities: list[MovementBreakActivity] = []
    if preferences.suggest_position_change:
        activities.append(MovementBreakActivity.POSITION_CHANGE)
    if preferences.suggest_standing:
        activities.append(MovementBreakActivity.STAND)
    if preferences.suggest_walking:
        activities.append(MovementBreakActivity.WALK)
    if preferences.suggest_guided_exercise:
        activities.append(MovementBreakActivity.GUIDED_EXERCISE)
    return tuple(activities)


def eye_break_activities(
    preferences: BreakPreferences,
) -> tuple[EyeBreakActivity, ...]:
    activities = [EyeBreakActivity.DISTANCE]
    if preferences.suggest_blinking:
        activities.append(EyeBreakActivity.BLINK)
    if preferences.suggest_closed_eye_rest:
        activities.append(EyeBreakActivity.EYES_CLOSED)
    return tuple(activities)


def next_movement_break_activity(
    preferences: BreakPreferences,
    index: int,
) -> MovementBreakActivity:
    activities = movement_break_activities(preferences)
    return activities[index % len(activities)]


def next_eye_break_activity(
    preferences: BreakPreferences,
    index: int,
) -> EyeBreakActivity:
    activities = eye_break_activities(preferences)
    return activities[index % len(activities)]


def movement_break_message(
    activity: MovementBreakActivity,
    minutes: int,
    *,
    eye_message: str | None = None,
) -> str:
    if activity is MovementBreakActivity.POSITION_CHANGE:
        message = tr(
            "Change how you are sitting for about {minutes} minutes: move "
            "your feet, shift where you are supported, and let your "
            "shoulders relax.",
            minutes=minutes,
        )
    elif activity is MovementBreakActivity.STAND:
        message = tr(
            "Stand for about {minutes} minutes. Shift your weight or take a "
            "few easy steps if that feels comfortable.",
            minutes=minutes,
        )
    else:
        message = tr(
            "Step away for about {minutes} minutes - walk, refill water, or "
            "make tea or coffee.",
            minutes=minutes,
        )
    if eye_message is not None:
        return tr(
            "{message} For your eyes: {eye_message}",
            message=message,
            eye_message=eye_message,
        )
    return message


def eye_break_message(
    activity: EyeBreakActivity,
    seconds: int,
) -> str:
    if activity is EyeBreakActivity.BLINK:
        return tr(
            "Look away from the screen, then make five slow, complete blinks "
            "over about {seconds} seconds.",
            seconds=seconds,
        )
    if activity is EyeBreakActivity.EYES_CLOSED:
        return tr(
            "Look away from the screen. If it is comfortable, close your "
            "eyes gently for about {seconds} seconds. Do not press or rub "
            "them.",
            seconds=seconds,
        )
    return tr(
        "Look at something about 6 m (20 ft) away for {seconds} seconds and "
        "let your focus relax.",
        seconds=seconds,
    )
