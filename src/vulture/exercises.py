from __future__ import annotations

import json
import random
from datetime import timedelta
from pathlib import Path

from pydantic import Field

from vulture.i18n import exercise_catalog_path, tr
from vulture.models import (
    AppData,
    ExercisePreferences,
    InterfaceLanguage,
    ReminderEvent,
    StrictModel,
    utc_now,
)
from vulture.random_cycle import choose_from_shuffle_bag
from vulture.resources import resource_path


class ExerciseSource(StrictModel):
    id: str
    organization: str
    title: str
    url: str
    publication_or_review_date: str | None = None
    supports: str


class Exercise(StrictModel):
    id: str
    title: str
    short_prompt: str
    dose: str
    steps: list[str]
    target_areas: list[str]
    tags: list[str]
    safety: str
    contraindication_flags: list[str] = Field(default_factory=list)
    source_ids: list[str]
    evidence_note: str
    media_path: str | None = None
    media_duration_seconds: float | None = Field(default=None, gt=0)


class ExerciseCatalog(StrictModel):
    version: int
    medical_disclaimer: str
    global_safety: str
    media_provenance: str
    sources: list[ExerciseSource]
    exercises: list[Exercise]

    def source_map(self) -> dict[str, ExerciseSource]:
        return {source.id: source for source in self.sources}


def load_exercise_catalog(
    path: Path | None = None,
    *,
    language: InterfaceLanguage | str | None = None,
) -> ExerciseCatalog:
    try:
        catalog_path = path or exercise_catalog_path(language)
        payload = json.loads(catalog_path.read_text(encoding="utf-8"))
        return ExerciseCatalog.model_validate(payload)
    except (OSError, ValueError) as error:
        raise RuntimeError(
            tr(
                "Could not load the bundled exercise catalog: {error}",
                error=error,
            )
        ) from error


def exercise_media_path(exercise: Exercise) -> Path | None:
    if exercise.media_path is None:
        return None
    candidate = resource_path("exercises").joinpath(exercise.media_path)
    return candidate if candidate.exists() else None


class ExerciseSelector:
    def __init__(
        self,
        catalog: ExerciseCatalog,
        random_source: random.Random | None = None,
    ) -> None:
        self.catalog = catalog
        self.random = random_source or random.SystemRandom()

    def choose(
        self,
        preferences: ExercisePreferences,
        recent_ids: list[str] | None = None,
    ) -> Exercise | None:
        eligible = [
            exercise
            for exercise in self.catalog.exercises
            if self._is_eligible(exercise, preferences)
        ]
        if not eligible:
            return None
        recent = set((recent_ids or [])[-3:])
        fresh = [exercise for exercise in eligible if exercise.id not in recent]
        return self.random.choice(fresh or eligible)

    def choose_from_bag(
        self,
        preferences: ExercisePreferences,
        remaining_ids: list[str],
        last_id: str | None,
    ) -> tuple[Exercise | None, list[str]]:
        eligible = [
            exercise
            for exercise in self.catalog.exercises
            if self._is_eligible(exercise, preferences)
        ]
        if not eligible:
            return None, []
        return choose_from_shuffle_bag(
            eligible,
            item_id=lambda exercise: exercise.id,
            remaining_ids=remaining_ids,
            last_id=last_id,
            random_source=self.random,
        )

    @staticmethod
    def _is_eligible(
        exercise: Exercise, preferences: ExercisePreferences
    ) -> bool:
        if exercise.id in preferences.excluded_exercise_ids:
            return False
        tags = set(exercise.tags)
        if preferences.seated_only and "seated" not in tags:
            return False
        if not preferences.allow_balance_exercises and "balance" in tags:
            return False
        if not preferences.allow_strength_exercises and "strength" in tags:
            return False
        return True


class ReminderEscalator:
    """Applies the user-configurable product policy; it is not medical advice."""

    def register(self, data: AppData, event: ReminderEvent) -> bool:
        data.reminder_history.append(event)
        cutoff = event.occurred_at - timedelta(days=7)
        data.reminder_history = [
            item for item in data.reminder_history if item.occurred_at >= cutoff
        ]

        policy = data.alert_policy
        window_start = event.occurred_at - timedelta(
            minutes=policy.repeated_reminder_window_minutes
        )
        recent_count = sum(
            item.setup_id == event.setup_id
            and item.occurred_at >= window_start
            for item in data.reminder_history
        )
        if recent_count < policy.repeated_reminders_for_break:
            return False

        if data.last_exercise_offer_at is not None:
            cooldown = timedelta(
                minutes=policy.exercise_offer_cooldown_minutes
            )
            if event.occurred_at - data.last_exercise_offer_at < cooldown:
                return False
        data.last_exercise_offer_at = event.occurred_at
        return True

    def mark_exercise_offered(self, data: AppData, exercise_id: str) -> None:
        data.recent_exercise_ids.append(exercise_id)
        data.recent_exercise_ids = data.recent_exercise_ids[-8:]
        data.last_exercise_offer_at = utc_now()
