from __future__ import annotations

import pytest
from PySide6.QtGui import QColor, QFont, QKeySequence
from PySide6.QtWidgets import QApplication, QLabel, QPushButton

from vulture.models import AppData, BreakPreferences
from vulture.ui.common import set_tooltip_with_shortcut, shortcut_hint
from vulture.ui.settings import SettingsDialog
from vulture.ui.theme import (
    PRIMARY_BUTTON_COLORS,
    STATE_COLOR_VALUES,
    STATE_FOREGROUND_LIGHT,
    SUMMARY_POSTURE_PALETTES,
    TextRole,
    flat_action_style,
    primary_button_style,
    role_font,
)


@pytest.fixture(scope="module")
def application() -> QApplication:
    return QApplication.instance() or QApplication([])


def _luminance(color: str) -> float:
    qcolor = QColor(color)
    channels = []
    for value in (qcolor.redF(), qcolor.greenF(), qcolor.blueF()):
        channels.append(
            value / 12.92
            if value <= 0.03928
            else ((value + 0.055) / 1.055) ** 2.4
        )
    red, green, blue = channels
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def _contrast(first: str, second: str) -> float:
    lighter, darker = sorted((_luminance(first), _luminance(second)))[::-1]
    return (lighter + 0.05) / (darker + 0.05)


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_primary_button_pair_meets_aa(scheme: str) -> None:
    fill, text, hover, pressed = PRIMARY_BUTTON_COLORS[scheme]
    for background in (fill, hover, pressed):
        assert _contrast(background, text) >= 4.5, (scheme, background)


def test_primary_and_flat_styles_cover_every_state(
    application: QApplication,
) -> None:
    for style in (primary_button_style(), flat_action_style()):
        for state in (":hover", ":pressed", ":focus", ":disabled"):
            assert f"QPushButton{state}" in style
            assert f"QToolButton{state}" in style
        assert "border-radius: 4px" in style
        assert "min-height" in style
    button = QPushButton("Start")
    button.setStyleSheet(primary_button_style())
    assert button.sizeHint().height() >= 28


def test_alert_state_reads_as_attention_not_danger() -> None:
    alert = STATE_COLOR_VALUES["alert"]
    assert 30 <= QColor(alert).hue() <= 60
    assert _contrast(alert, STATE_FOREGROUND_LIGHT) >= 4.5
    assert alert != STATE_COLOR_VALUES["warning"]


def test_summary_palette_has_no_red_and_separates_neighbours() -> None:
    for scheme, palette in SUMMARY_POSTURE_PALETTES.items():
        assert len(set(palette.values())) == len(palette), scheme
        for color in palette.values():
            assert 15 <= QColor(color).hue() <= 345, (scheme, color)
        assert (
            QColor(palette["general_deviation"]).hue()
            != QColor(palette["slouch"]).hue()
        )
        assert (
            abs(
                QColor(palette["forward_head"]).hue()
                - QColor(palette["shoulders_sunk"]).hue()
            )
            >= 30
        )


def test_display_font_is_ui_family_with_tabular_figures(
    application: QApplication,
) -> None:
    font = role_font(TextRole.DISPLAY)
    assert font.isFeatureSet(QFont.Tag("tnum"))
    assert font.styleHint() != QFont.StyleHint.Monospace
    assert not font.fixedPitch()
    assert font.families() == QApplication.font().families()


def test_shortcut_hint_uses_native_text(application: QApplication) -> None:
    sequence = QKeySequence("Ctrl+,")
    native = sequence.toString(QKeySequence.SequenceFormat.NativeText)
    assert shortcut_hint("Settings", sequence) == f"Settings ({native})"
    assert shortcut_hint("Settings", QKeySequence()) == "Settings"
    label = QLabel()
    set_tooltip_with_shortcut(label, "Settings", "Ctrl+,")
    assert label.toolTip() == f"Settings ({native})"


def test_settings_posture_tone_and_unique_mnemonics(
    application: QApplication,
) -> None:
    data = AppData()
    dialog = SettingsDialog(
        data.alert_policy,
        data.exercise_preferences,
        data.history_preferences,
        data.interface_language,
        break_preferences=BreakPreferences(),
    )
    page = dialog.tabs.widget(0)
    texts = [label.text() for label in page.findChildren(QLabel)]
    joined = " ".join(texts + [w.toolTip() for w in page.findChildren(QLabel)])
    assert "&Nudge me after" in texts
    for old in ("Warn me", "warning", "bad posture"):
        assert old not in joined
    mnemonics = [
        QKeySequence.mnemonic(text).toString()
        for text in texts
        if "&" in text
    ]
    assert len(mnemonics) == len(set(mnemonics)) >= 4
