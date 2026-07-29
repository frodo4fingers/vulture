from __future__ import annotations

import json
from pathlib import Path

from vulture.models import InterfaceLanguage
from vulture.resources import resource_path


LANGUAGE_NAMES = {
    InterfaceLanguage.ENGLISH: "English",
    InterfaceLanguage.GERMAN: "Deutsch",
    InterfaceLanguage.SPANISH: "Español",
}

_current_language = InterfaceLanguage.ENGLISH
_translations: dict[str, str] = {}
_qt_translator = None


def current_language() -> InterfaceLanguage:
    return _current_language


def set_language(language: InterfaceLanguage | str) -> InterfaceLanguage:
    global _current_language, _translations
    selected = InterfaceLanguage(language)
    _translations = _load_translations(selected)
    _current_language = selected
    return selected


def tr(message: str, /, **values) -> str:
    translated = _translations.get(message, message)
    return translated.format(**values) if values else translated


def exercise_catalog_path(
    language: InterfaceLanguage | str | None = None,
) -> Path:
    selected = InterfaceLanguage(language or _current_language)
    suffix = "" if selected is InterfaceLanguage.ENGLISH else f".{selected.value}"
    return resource_path("exercises", f"catalog{suffix}.json")


def configure_qt_translations(application) -> None:
    global _qt_translator

    from PySide6.QtCore import QLibraryInfo, QLocale, QTranslator

    if _qt_translator is not None:
        application.removeTranslator(_qt_translator)
        _qt_translator.deleteLater()
        _qt_translator = None

    locale_names = {
        InterfaceLanguage.ENGLISH: "en_US",
        InterfaceLanguage.GERMAN: "de_DE",
        InterfaceLanguage.SPANISH: "es_ES",
    }
    QLocale.setDefault(QLocale(locale_names[_current_language]))
    if _current_language is InterfaceLanguage.ENGLISH:
        return

    translator = QTranslator(application)
    translations_path = QLibraryInfo.path(
        QLibraryInfo.LibraryPath.TranslationsPath
    )
    if translator.load(
        f"qtbase_{_current_language.value}",
        translations_path,
    ):
        application.installTranslator(translator)
        _qt_translator = translator
    else:
        translator.deleteLater()
        raise RuntimeError(
            tr(
                "Could not load Qt interface translations for {language}.",
                language=LANGUAGE_NAMES[_current_language],
            )
        )


def validate_qt_translations(
    language: InterfaceLanguage | str,
) -> None:
    selected = InterfaceLanguage(language)
    if selected is InterfaceLanguage.ENGLISH:
        return

    from PySide6.QtCore import QLibraryInfo, QTranslator

    translator = QTranslator()
    translations_path = QLibraryInfo.path(
        QLibraryInfo.LibraryPath.TranslationsPath
    )
    if not translator.load(
        f"qtbase_{selected.value}",
        translations_path,
    ):
        raise RuntimeError(
            tr(
                "Could not load Qt interface translations for {language}.",
                language=LANGUAGE_NAMES[selected],
            )
        )


def translation_messages(
    language: InterfaceLanguage | str,
) -> dict[str, str]:
    return dict(_load_translations(InterfaceLanguage(language)))


def _load_translations(
    language: InterfaceLanguage,
) -> dict[str, str]:
    if language is InterfaceLanguage.ENGLISH:
        return {}
    relative_path = Path("i18n", f"{language.value}.json")
    try:
        path = resource_path(*relative_path.parts)
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise RuntimeError(
            tr(
                "Could not load interface translations from {path}: {error}",
                path=relative_path,
                error=error,
            )
        ) from error
    if not isinstance(payload, dict) or not all(
        isinstance(key, str) and isinstance(value, str)
        for key, value in payload.items()
    ):
        raise RuntimeError(
            tr(
                "Interface translation file must contain string pairs: {path}",
                path=path,
            )
        )
    return payload
