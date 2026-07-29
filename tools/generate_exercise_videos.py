#!/usr/bin/env python3
"""Generate original exercise animations with only Python and local FFmpeg."""

from __future__ import annotations

import argparse
import math
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path


WIDTH = 640
HEIGHT = 360
FPS = 12
DURATION_SECONDS = 10
BACKGROUND = (15, 23, 42)
SURFACE = (30, 41, 59)
FIGURE = (226, 232, 240)
ACCENT = (56, 189, 248)
SECONDARY = (74, 222, 128)
CHAIR = (148, 163, 184)


class Canvas:
    def __init__(self) -> None:
        self.pixels = bytearray(BACKGROUND * (WIDTH * HEIGHT))

    def disk(
        self,
        x: float,
        y: float,
        radius: int,
        color: tuple[int, int, int],
    ) -> None:
        center_x = round(x)
        center_y = round(y)
        for py in range(max(0, center_y - radius), min(HEIGHT, center_y + radius + 1)):
            distance_y = py - center_y
            extent = int(math.sqrt(max(0, radius * radius - distance_y * distance_y)))
            start = max(0, center_x - extent)
            end = min(WIDTH - 1, center_x + extent)
            for px in range(start, end + 1):
                offset = (py * WIDTH + px) * 3
                self.pixels[offset : offset + 3] = bytes(color)

    def line(
        self,
        start: tuple[float, float],
        end: tuple[float, float],
        color: tuple[int, int, int] = FIGURE,
        width: int = 5,
    ) -> None:
        delta_x = end[0] - start[0]
        delta_y = end[1] - start[1]
        steps = max(1, math.ceil(max(abs(delta_x), abs(delta_y))))
        for step in range(steps + 1):
            ratio = step / steps
            self.disk(
                start[0] + delta_x * ratio,
                start[1] + delta_y * ratio,
                max(1, width // 2),
                color,
            )

    def rectangle(
        self,
        left: int,
        top: int,
        right: int,
        bottom: int,
        color: tuple[int, int, int],
    ) -> None:
        left = max(0, left)
        right = min(WIDTH, right)
        top = max(0, top)
        bottom = min(HEIGHT, bottom)
        row = bytes(color) * max(0, right - left)
        for y in range(top, bottom):
            offset = (y * WIDTH + left) * 3
            self.pixels[offset : offset + len(row)] = row

    def arrow(
        self,
        start: tuple[float, float],
        end: tuple[float, float],
    ) -> None:
        self.line(start, end, ACCENT, 4)
        angle = math.atan2(end[1] - start[1], end[0] - start[0])
        for offset in (-0.65, 0.65):
            tip = (
                end[0] - math.cos(angle + offset) * 14,
                end[1] - math.sin(angle + offset) * 14,
            )
            self.line(end, tip, ACCENT, 4)

    def frame(self, progress: float) -> bytes:
        self.rectangle(0, 328, WIDTH, HEIGHT, SURFACE)
        self.rectangle(25, 338, WIDTH - 25, 345, (51, 65, 85))
        self.rectangle(25, 338, 25 + round((WIDTH - 50) * progress), 345, SECONDARY)
        return bytes(self.pixels)


def wave(phase: float) -> float:
    return 0.5 - 0.5 * math.cos(2 * math.pi * phase)


def draw_head(canvas: Canvas, x: float, y: float) -> None:
    canvas.disk(x, y, 18, FIGURE)


def draw_chair(canvas: Canvas, x: float = 360, y: float = 244) -> None:
    canvas.line((x - 45, y), (x + 45, y), CHAIR, 8)
    canvas.line((x + 43, y), (x + 43, y - 100), CHAIR, 8)
    canvas.line((x - 34, y), (x - 40, y + 74), CHAIR, 7)
    canvas.line((x + 34, y), (x + 40, y + 74), CHAIR, 7)


def walking(canvas: Canvas, phase: float) -> None:
    travel = wave(phase)
    x = 180 + travel * 280
    step = math.sin(4 * math.pi * phase)
    shoulder = (x, 155)
    hip = (x, 225)
    draw_head(canvas, x, 115)
    canvas.line(shoulder, hip)
    canvas.line(shoulder, (x + 34 * step, 205), ACCENT)
    canvas.line(shoulder, (x - 34 * step, 205), ACCENT)
    canvas.line(hip, (x + 34 * step, 292))
    canvas.line(hip, (x - 34 * step, 292))
    canvas.arrow((160, 305), (480, 305))


def chest_stretch(canvas: Canvas, phase: float) -> None:
    draw_chair(canvas)
    amount = wave(phase)
    hip = (345, 235)
    shoulder = (345 - 6 * amount, 160)
    draw_head(canvas, shoulder[0], 118)
    canvas.line(shoulder, hip)
    canvas.line(hip, (415, 265))
    canvas.line((415, 265), (415, 315))
    reach = 35 + 90 * amount
    hand_y = 210 - 50 * amount
    canvas.line(shoulder, (shoulder[0] - reach, hand_y), ACCENT)
    canvas.line(shoulder, (shoulder[0] + reach, hand_y), ACCENT)
    canvas.arrow((345, 195), (345 - 28 * amount, 185))


def shoulder_shrug(canvas: Canvas, phase: float) -> None:
    amount = wave(phase)
    shoulder_y = 174 - 24 * amount
    draw_head(canvas, 320, 112)
    canvas.line((320, shoulder_y), (320, 250))
    left_shoulder = (276, shoulder_y)
    right_shoulder = (364, shoulder_y)
    canvas.line(left_shoulder, right_shoulder, SECONDARY, 7)
    canvas.line(left_shoulder, (260, 250))
    canvas.line(right_shoulder, (380, 250))
    canvas.arrow((255, 185), (255, 145))
    canvas.arrow((385, 185), (385, 145))


def wrist_side_bend(canvas: Canvas, phase: float) -> None:
    angle = math.radians(28 * math.sin(2 * math.pi * phase))
    elbow = (195, 215)
    wrist = (390, 215)
    hand_end = (
        wrist[0] + math.cos(angle) * 90,
        wrist[1] + math.sin(angle) * 90,
    )
    canvas.line(elbow, wrist, FIGURE, 12)
    canvas.disk(wrist[0], wrist[1], 10, SECONDARY)
    canvas.line(wrist, hand_end, ACCENT, 14)
    for offset in (-12, -4, 4, 12):
        normal = angle + math.pi / 2
        finger_start = (
            hand_end[0] + math.cos(normal) * offset,
            hand_end[1] + math.sin(normal) * offset,
        )
        finger_end = (
            finger_start[0] + math.cos(angle) * 30,
            finger_start[1] + math.sin(angle) * 30,
        )
        canvas.line(finger_start, finger_end, FIGURE, 3)
    canvas.arrow((410, 140), (470, 175))
    canvas.arrow((470, 255), (410, 290))


def hip_march(canvas: Canvas, phase: float) -> None:
    draw_chair(canvas)
    draw_head(canvas, 330, 112)
    shoulder = (330, 155)
    hip = (345, 238)
    canvas.line(shoulder, hip)
    canvas.line(shoulder, (365, 215), ACCENT)
    lift_left = max(0.0, math.sin(2 * math.pi * phase))
    lift_right = max(0.0, -math.sin(2 * math.pi * phase))
    left_knee = (300, 275 - 48 * lift_left)
    right_knee = (405, 275 - 48 * lift_right)
    canvas.line(hip, left_knee)
    canvas.line(left_knee, (300, 318))
    canvas.line(hip, right_knee)
    canvas.line(right_knee, (405, 318))
    canvas.arrow((275, 285), (275, 225))
    canvas.arrow((430, 285), (430, 225))


def ankle_point_flex(canvas: Canvas, phase: float) -> None:
    draw_chair(canvas, 315, 242)
    draw_head(canvas, 285, 110)
    shoulder = (285, 155)
    hip = (300, 235)
    knee = (405, 250)
    ankle = (500, 265)
    canvas.line(shoulder, hip)
    canvas.line(hip, knee)
    canvas.line(knee, ankle, FIGURE, 8)
    angle = math.radians(35 * math.sin(2 * math.pi * phase))
    foot = (
        ankle[0] + math.cos(angle) * 55,
        ankle[1] + math.sin(angle) * 55,
    )
    canvas.line(ankle, foot, ACCENT, 10)
    canvas.arrow((535, 205), (565, 245))
    canvas.arrow((565, 305), (535, 275))


def sit_to_stand(canvas: Canvas, phase: float) -> None:
    draw_chair(canvas, 400, 245)
    amount = wave(phase)
    seated = {
        "head": (350, 125),
        "shoulder": (350, 165),
        "hip": (370, 235),
        "knee": (440, 260),
        "ankle": (440, 316),
    }
    standing = {
        "head": (335, 92),
        "shoulder": (335, 134),
        "hip": (335, 220),
        "knee": (350, 270),
        "ankle": (365, 316),
    }

    def interpolate(name: str) -> tuple[float, float]:
        start = seated[name]
        end = standing[name]
        return (
            start[0] + (end[0] - start[0]) * amount,
            start[1] + (end[1] - start[1]) * amount,
        )

    head = interpolate("head")
    shoulder = interpolate("shoulder")
    hip = interpolate("hip")
    knee = interpolate("knee")
    ankle = interpolate("ankle")
    draw_head(canvas, *head)
    canvas.line(shoulder, hip)
    canvas.line(hip, knee)
    canvas.line(knee, ankle)
    canvas.line(shoulder, (390, 215 - 30 * amount), ACCENT)
    canvas.arrow((270, 255), (270, 140))


def calf_raise(canvas: Canvas, phase: float) -> None:
    amount = wave(phase)
    lift = 16 * amount
    chair_x = 430
    draw_chair(canvas, chair_x, 245)
    head = (330, 92 - lift)
    shoulder = (330, 134 - lift)
    hip = (330, 220 - lift)
    toe = (345, 318)
    heel = (315, 318 - lift)
    draw_head(canvas, *head)
    canvas.line(shoulder, hip)
    canvas.line(hip, (330, 275 - lift))
    canvas.line((330, 275 - lift), heel)
    canvas.line(heel, toe, ACCENT, 8)
    canvas.line(shoulder, (chair_x - 15, 175), SECONDARY)
    canvas.arrow((275, 300), (275, 245))


ANIMATIONS: dict[str, tuple[str, str, Callable[[Canvas, float], None]]] = {
    "easy-walk": ("Easy desk-side walk", "5 minutes at a comfortable pace", walking),
    "seated-chest-stretch": (
        "Seated chest stretch",
        "Hold 5-10 seconds; repeat 5 times",
        chest_stretch,
    ),
    "shoulder-shrug": (
        "Shoulder shrug and release",
        "Hold 3-5 seconds; repeat 2-3 times",
        shoulder_shrug,
    ),
    "wrist-side-bend": (
        "Gentle wrist side-bend",
        "Hold each side 3-5 seconds; 3 cycles",
        wrist_side_bend,
    ),
    "seated-hip-march": (
        "Seated hip marching",
        "5 lifts per leg",
        hip_march,
    ),
    "ankle-point-flex": (
        "Seated ankle point and flex",
        "2 sets of 5 per foot",
        ankle_point_flex,
    ),
    "sit-to-stand": (
        "Sit-to-stand",
        "5 slow repetitions",
        sit_to_stand,
    ),
    "supported-calf-raise": (
        "Supported calf raise",
        "5 slow repetitions",
        calf_raise,
    ),
}


def find_font() -> Path:
    candidates = [
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf"),
        Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
        Path("C:/Windows/Fonts/arialbd.ttf"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise RuntimeError("No supported local TrueType font was found.")


def generate_video(
    output: Path,
    title: str,
    dose: str,
    animation: Callable[[Canvas, float], None],
    overwrite: bool,
) -> None:
    if output.exists() and not overwrite:
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError("FFmpeg is required to generate the bundled videos.")
    font = find_font()
    total_frames = FPS * DURATION_SECONDS

    with tempfile.TemporaryDirectory(prefix="vulture-media-") as directory:
        temporary = Path(directory)
        title_file = temporary / "title.txt"
        dose_file = temporary / "dose.txt"
        title_file.write_text(title, encoding="utf-8")
        dose_file.write_text(dose, encoding="utf-8")
        filter_graph = (
            "drawbox=x=0:y=0:w=iw:h=76:color=0x0b1220@0.94:t=fill,"
            f"drawtext=fontfile='{font}':textfile='{title_file}':"
            "fontcolor=white:fontsize=27:x=24:y=13,"
            f"drawtext=fontfile='{font}':textfile='{dose_file}':"
            "fontcolor=0x7dd3fc:fontsize=18:x=24:y=48"
        )
        command = [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "rawvideo",
            "-pixel_format",
            "rgb24",
            "-video_size",
            f"{WIDTH}x{HEIGHT}",
            "-framerate",
            str(FPS),
            "-i",
            "-",
            "-vf",
            filter_graph,
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "27",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(output),
        ]
        process = subprocess.Popen(command, stdin=subprocess.PIPE)
        if process.stdin is None:
            raise RuntimeError("Could not open FFmpeg input.")
        try:
            for frame_index in range(total_frames):
                progress = frame_index / max(1, total_frames - 1)
                phase = (progress * 2.0) % 1.0
                canvas = Canvas()
                animation(canvas, phase)
                process.stdin.write(canvas.frame(progress))
        finally:
            process.stdin.close()
        exit_code = process.wait()
        if exit_code != 0:
            output.unlink(missing_ok=True)
            raise RuntimeError(f"FFmpeg failed for {output.name}.")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=(
            Path(__file__).resolve().parents[1]
            / "src"
            / "vulture"
            / "resources"
            / "exercises"
            / "videos"
        ),
    )
    parser.add_argument("--overwrite", action="store_true")
    arguments = parser.parse_args()

    for exercise_id, (title, dose, animation) in ANIMATIONS.items():
        output = arguments.output / f"{exercise_id}.mp4"
        generate_video(
            output,
            title,
            dose,
            animation,
            arguments.overwrite,
        )
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
