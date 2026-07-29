from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtGui import QImage


def test_calibration_photo_prompts_match_visible_stages() -> None:
    prompt_path = (
        Path(__file__).parents[1]
        / "src"
        / "vulture"
        / "resources"
        / "calibration"
        / "photo-prompts.json"
    )
    data = json.loads(prompt_path.read_text(encoding="utf-8"))

    assert data["version"] == 2
    assert "five separate still images, never a collage" in data["usage"]
    assert "Prepend the shared continuity_lock" in data["usage"]
    assert "sole exception" in data["usage"]
    continuity_lock = data["continuity_lock"]
    assert "\n" not in continuity_lock
    for section in (
        "CAMERA:",
        "LENS:",
        "LIGHT:",
        "GRADE:",
        "FIGURE:",
        "CHAIR:",
        "FRAMING:",
        "FORMAT:",
        "NEGATIVE:",
    ):
        assert section in continuity_lock
    for detail in (
        "Long telephoto",
        "Extremely shallow depth of field",
        "#968D84",
        "#221E1A",
        "#6B625A",
        "adult human training mannequin",
        "blank unmarked eyes with no irises or pupils",
        "Not a segmented wooden artist mannequin",
        "same plain unbranded dark crew-neck long-sleeve sweatshirt",
        "Exactly one stable plain non-wheeled chair",
        "Approximately 28% headroom",
        "high-quality 1280x720 JPEG",
    ):
        assert detail in continuity_lock
    serialized = json.dumps(data)
    for replaced_detail in (
        "medium warm-brown skin",
        "#9A6246",
        "dark espresso-brown hair",
        "UHD 3840x2160",
        "full-frame 50 mm equivalent lens",
        "white balance 5200 K",
    ):
        assert replaced_detail not in serialized
    assert [
        (item["id"], item["title"], item["filename"])
        for item in data["prompts"]
    ] == [
        (
            "good",
            "Comfortable baseline",
            "calibration-01-comfortable-baseline.jpg",
        ),
        (
            "forward_head",
            "Head-forward example",
            "calibration-02-head-forward.jpg",
        ),
        (
            "slouch",
            "Slouch example",
            "calibration-03-slouch.jpg",
        ),
        (
            "shoulders_sunk",
            "Sunk-shoulder example",
            "calibration-04-sunk-shoulders.jpg",
        ),
        (
            "lateral_lean",
            "Side-lean example",
            "calibration-05-side-lean.jpg",
        ),
    ]

    for item in data["prompts"]:
        prompt = item["prompt"]
        image_path = prompt_path.parent / item["filename"]
        assert image_path.is_file()
        assert image_path.stat().st_size > 50_000
        image = QImage(str(image_path))
        assert not image.isNull()
        assert image.size().toTuple() == (1280, 720)
        assert len(prompt) > 900
        assert "Generate exactly one still image" in prompt
        assert "CATEGORY ISOLATION" in prompt
        assert "language-neutral with no text or graphics" in prompt

    prompts = {item["id"]: item["prompt"] for item in data["prompts"]}
    assert "comfortable reference only" in prompts["good"]
    assert "Translate the head and neck forward" in prompts["forward_head"]
    assert "pelvis roll gently backward" in prompts["slouch"]
    assert "both shoulders settle symmetrically" in prompts[
        "shoulders_sunk"
    ]
    assert "approximately 10 to 12 degrees" in prompts["lateral_lean"]
