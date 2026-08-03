from __future__ import annotations

import random
from enum import StrEnum
from typing import TypeVar

from vulture.i18n import tr
from vulture.models import BreakPreferences
from vulture.random_cycle import choose_from_shuffle_bag


class BreakChannel(StrEnum):
    EYE = "eye"
    MOVEMENT = "movement"
    HYDRATION = "hydration"
    RESET = "reset"


class MovementBreakActivity(StrEnum):
    POSITION_CHANGE = "position_change"
    STAND = "stand"
    WALK = "walk"
    WALK_OR_DRINK = "walk_or_drink"
    GUIDED_EXERCISE = "guided_exercise"


class EyeBreakActivity(StrEnum):
    DISTANCE = "distance"
    NATURE = "nature"
    BLINK = "blink"
    EYES_CLOSED = "eyes_closed"


class HydrationBreakActivity(StrEnum):
    WATER = "water"


class ResetBreakActivity(StrEnum):
    TEA_OR_COFFEE = "tea_or_coffee"
    WALK = "walk"
    BREATHE = "breathe"
    OFFSCREEN = "offscreen"
    GUIDED_EXERCISE = "guided_exercise"


BreakActivityT = TypeVar(
    "BreakActivityT",
    MovementBreakActivity,
    EyeBreakActivity,
    HydrationBreakActivity,
    ResetBreakActivity,
)


class BreakActivitySelector:
    def __init__(
        self,
        random_source: random.Random | None = None,
    ) -> None:
        self.random = random_source or random.SystemRandom()

    def choose(
        self,
        activities: tuple[BreakActivityT, ...],
        remaining_ids: list[str],
        last_id: str | None,
    ) -> tuple[BreakActivityT, list[str]]:
        return choose_from_shuffle_bag(
            activities,
            item_id=lambda activity: activity.value,
            remaining_ids=remaining_ids,
            last_id=last_id,
            random_source=self.random,
        )


def movement_break_activities(
    preferences: BreakPreferences,
) -> tuple[MovementBreakActivity, ...]:
    activities: list[MovementBreakActivity] = []
    if preferences.suggest_position_change:
        activities.append(MovementBreakActivity.POSITION_CHANGE)
    if preferences.suggest_standing:
        activities.append(MovementBreakActivity.STAND)
    if preferences.suggest_walking:
        activities.append(
            MovementBreakActivity.WALK_OR_DRINK
            if preferences.legacy_walk_includes_drinks
            else MovementBreakActivity.WALK
        )
    if preferences.suggest_guided_exercise:
        activities.append(MovementBreakActivity.GUIDED_EXERCISE)
    return tuple(activities)


def eye_break_activities(
    preferences: BreakPreferences,
) -> tuple[EyeBreakActivity, ...]:
    activities = [EyeBreakActivity.DISTANCE]
    if preferences.suggest_nature_view:
        activities.append(EyeBreakActivity.NATURE)
    if preferences.suggest_blinking:
        activities.append(EyeBreakActivity.BLINK)
    if preferences.suggest_closed_eye_rest:
        activities.append(EyeBreakActivity.EYES_CLOSED)
    return tuple(activities)


def hydration_break_activities(
    _preferences: BreakPreferences,
) -> tuple[HydrationBreakActivity, ...]:
    return (HydrationBreakActivity.WATER,)


def reset_break_activities(
    preferences: BreakPreferences,
) -> tuple[ResetBreakActivity, ...]:
    activities: list[ResetBreakActivity] = []
    if preferences.suggest_tea_or_coffee:
        activities.append(ResetBreakActivity.TEA_OR_COFFEE)
    if preferences.suggest_reset_walking:
        activities.append(ResetBreakActivity.WALK)
    if preferences.suggest_breathing_reset:
        activities.append(ResetBreakActivity.BREATHE)
    if preferences.suggest_offscreen_reset:
        activities.append(ResetBreakActivity.OFFSCREEN)
    if preferences.suggest_reset_guided_exercise:
        activities.append(ResetBreakActivity.GUIDED_EXERCISE)
    return tuple(activities)


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
    elif activity is MovementBreakActivity.WALK:
        message = tr(
            "Leave the screen and take an easy walk for about {minutes} "
            "minutes. Use a clear route and your usual walking aid if needed.",
            minutes=minutes,
        )
    elif activity is MovementBreakActivity.WALK_OR_DRINK:
        message = tr(
            "Step away for about {minutes} minutes - walk, refill water, or "
            "make tea or coffee.",
            minutes=minutes,
        )
    else:
        raise ValueError("guided exercises use the exercise dialog")
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
    if activity is EyeBreakActivity.NATURE:
        return tr(
            "Look away from the screen toward a distant plant, tree, or "
            "other greenery for about {seconds} seconds. Let the view hold "
            "your attention without searching for detail.",
            seconds=seconds,
        )
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


def hydration_break_message(seconds: int) -> str:
    return tr(
        "Step away from the screen for about {seconds} seconds and refill a "
        "glass or bottle. Drink if you would like, following your own thirst "
        "and any medical guidance.",
        seconds=seconds,
    )


def reset_break_message(
    activity: ResetBreakActivity,
    minutes: int,
) -> str:
    if activity is ResetBreakActivity.TEA_OR_COFFEE:
        return tr(
            "Leave the screen for about {minutes} minutes and make tea, "
            "coffee, or another drink you enjoy. The useful part is stepping "
            "away; caffeine is optional.",
            minutes=minutes,
        )
    if activity is ResetBreakActivity.WALK:
        return tr(
            "Leave the screen and take an easy walk for about {minutes} "
            "minutes. Use a clear route and your usual walking aid if needed.",
            minutes=minutes,
        )
    if activity is ResetBreakActivity.BREATHE:
        return tr(
            "For about {minutes} minutes, breathe comfortably and let each "
            "exhale last a little longer than the inhale. Do not hold or "
            "force the breath; return to normal breathing if uncomfortable.",
            minutes=minutes,
        )
    if activity is ResetBreakActivity.OFFSCREEN:
        return tr(
            "Take about {minutes} minutes fully off-screen. Put the phone "
            "down if practical and choose a quiet pause, a short "
            "conversation, or a few unhurried steps.",
            minutes=minutes,
        )
    raise ValueError("guided exercises use the exercise dialog")


def break_channel_title(channel: BreakChannel) -> str:
    if channel is BreakChannel.EYE:
        return tr("Eye comfort break")
    if channel is BreakChannel.MOVEMENT:
        return tr("Time for a movement break")
    if channel is BreakChannel.HYDRATION:
        return tr("Water break")
    return tr("Time for a longer reset")
