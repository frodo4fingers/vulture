from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

from vulture.exercises import ExerciseSelector, ReminderEscalator, load_exercise_catalog
from vulture.models import (
    AppData,
    ExercisePreferences,
    PostureCategory,
    ReminderEvent,
    SetupProfile,
    CameraDescriptor,
    utc_now,
)


def test_catalog_sources_and_media_are_complete() -> None:
    catalog = load_exercise_catalog()
    source_ids = {source.id for source in catalog.sources}
    assert len(catalog.exercises) == 8
    for exercise in catalog.exercises:
        assert set(exercise.source_ids) <= source_ids
        assert exercise.media_path is not None
        media = (
            Path(__file__).parents[1]
            / "src"
            / "vulture"
            / "resources"
            / "exercises"
            / exercise.media_path
        )
        assert media.exists()
        assert media.stat().st_size > 10_000


def test_video_prompts_match_exercise_catalog() -> None:
    catalog = load_exercise_catalog()
    prompt_path = (
        Path(__file__).parents[1]
        / "src"
        / "vulture"
        / "resources"
        / "exercises"
        / "video-prompts.json"
    )
    prompt_data = json.loads(prompt_path.read_text(encoding="utf-8"))
    prompts = {item["id"]: item for item in prompt_data["prompts"]}

    assert prompt_data["version"] == 2
    continuity_lock = prompt_data["continuity_lock"]
    for section in (
        "CAMERA:",
        "LENS:",
        "LIGHT:",
        "GRADE:",
        "FIGURE:",
        "FRAMING:",
        "MOTION:",
        "AUDIO:",
        "FORMAT:",
        "NEGATIVE:",
    ):
        assert section in continuity_lock
    for detail in (
        "single pixel across the entire shot",
        "Long telephoto",
        "Extremely shallow depth of field",
        "#968D84",
        "#221E1A",
        "#6B625A",
        "Approximately 28% headroom",
        "1280x720, 24fps, 10 seconds",
        "Quiet natural ambience only",
        "adult human training mannequin",
        "blank unmarked eyes with no irises or pupils",
        "Not a segmented wooden artist mannequin",
        "same plain unbranded dark crew-neck long-sleeve sweatshirt",
    ):
        assert detail in continuity_lock
    serialized = json.dumps(prompt_data)
    for replaced_detail in (
        "UHD 3840x2160",
    ):
        assert replaced_detail not in serialized
    assert "only exception" in prompt_data["usage"]

    assert len(prompts) == len(prompt_data["prompts"]) == 8
    assert set(prompts) == {
        exercise.id for exercise in catalog.exercises
    }
    for exercise in catalog.exercises:
        prompt = prompts[exercise.id]
        assert prompt["title"] == exercise.title
        assert prompt["source_ids"] == exercise.source_ids
        text = prompt["prompt"]
        assert "10-second" in text
        assert "language-neutral" in text
        if exercise.id == "ankle-point-flex":
            assert 2_000 < len(text) < 3_000
        else:
            assert 650 < len(text) < 1_000

    assert "short natural steps" in prompts["easy-walk"]["prompt"]
    assert "draws both shoulders back and down" in prompts[
        "seated-chest-stretch"
    ]["prompt"]
    assert "pause for about three seconds" in prompts["shoulder-shrug"]["prompt"]
    assert "The opposite hand must not push or pull" in prompts[
        "wrist-side-bend"
    ]["prompt"]
    assert "holds both sides of the chair" in prompts[
        "seated-hip-march"
    ]["prompt"]
    ankle_prompt = prompts["ankle-point-flex"]["prompt"]
    for detail in (
        "STARTING POSE AT 0.0 SECONDS",
        "heel about 10-12 cm above the floor",
        "plantar flexion at the ankle",
        "do not curl only the toes",
        "dorsiflexion",
        "From 4.5 to 5.0 seconds, smoothly exchange sides",
        "exact starting pose by 10.0 seconds",
        "no inward roll, outward roll, twisting, or circle",
        "Never lift both feet together",
    ):
        assert detail in ankle_prompt
    assert "leans slightly forward" in prompts[
        "sit-to-stand"
    ]["prompt"]
    assert "keeps both hands securely on its back" in prompts[
        "supported-calf-raise"
    ]["prompt"]

def test_selector_respects_seated_only_filter() -> None:
    catalog = load_exercise_catalog()
    selector = ExerciseSelector(catalog)
    preferences = ExercisePreferences(seated_only=True)
    for _ in range(20):
        selected = selector.choose(preferences)
        assert selected is not None
        assert "standing" not in selected.tags


def test_default_preferences_exclude_balance_and_strength() -> None:
    catalog = load_exercise_catalog()
    selector = ExerciseSelector(catalog)
    preferences = ExercisePreferences()
    for _ in range(20):
        selected = selector.choose(preferences)
        assert selected is not None
        assert "balance" not in selected.tags
        assert "strength" not in selected.tags


def test_fifth_reminder_in_window_offers_break() -> None:
    setup = SetupProfile(
        name="Test",
        camera=CameraDescriptor(
            stable_id="test",
            display_name="Test",
            locator=0,
        ),
    )
    data = AppData(active_setup_id=setup.id, setups=[setup])
    escalator = ReminderEscalator()
    start = utc_now()
    decisions = []
    for index in range(5):
        decisions.append(
            escalator.register(
                data,
                ReminderEvent(
                    occurred_at=start + timedelta(minutes=index * 3),
                    setup_id=setup.id,
                    category=PostureCategory.GENERAL_DEVIATION,
                ),
            )
        )
    assert decisions == [False, False, False, False, True]
