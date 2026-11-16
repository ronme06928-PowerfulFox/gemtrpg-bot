"""Paper theme contract for both management workspaces."""
from pathlib import Path
import re

import pytest


CSS = Path(__file__).resolve().parents[1] / "static" / "css" / "modules"


@pytest.mark.parametrize("filename", ["master_data.css", "unit_management.css", "main_menu.css", "paper_screens.css"])
def test_workspace_colors_use_tokens(filename):
    source = re.sub(r"/\*.*?\*/", "", (CSS / filename).read_text(encoding="utf-8"), flags=re.S)
    values = re.findall(r"(?:[;{])\s*[\w-]+\s*:\s*([^;}]+)", source)
    color = re.compile(r"#[0-9a-f]{3,8}\b|\b(?:rgba?|hsla?|hwb|oklch|oklab|lab|lch)\(|\b(?:white|black|red|blue|gold)\b", re.I)
    literals = [value for value in values if color.search(re.sub(r"var\(\s*--[\w-]+", "var(", value))]
    assert not literals


def _luminance(rgb):
    channels = [int(rgb[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return sum(c * w for c, w in zip(linear, (0.2126, 0.7152, 0.0722)))


def _theme_tokens(source, theme):
    block = re.search(r'\[data-theme="' + theme + r'"\]\s*\{([^}]+)\}', source)[1]
    return {name: value.strip() for name, value in re.findall(r"(--(?:ui|gem)-[\w-]+):\s*([^;]+)", block)}


def _app_theme(theme):
    return _theme_tokens((CSS / "common_ui.css").read_text(encoding="utf-8"), theme)


@pytest.mark.parametrize("theme", ["paper", "night"])
def test_theme_text_and_control_contrast(theme):
    tokens = _app_theme(theme)
    for foreground, background, minimum in [
        ("text", "bg", 4.5), ("sub", "bg", 4.5), ("sub", "soft", 4.5),
        ("text", "primary-soft", 4.5), ("on-primary", "primary", 4.5),
        ("primary", "bg", 4.5), ("danger", "danger-soft", 4.5),
        ("warn", "warn-soft", 4.5), ("add", "add-soft", 4.5),
        ("ally", "ally-soft", 4.5), ("enemy", "enemy-soft", 4.5),
        ("control", "bg", 3), ("control", "soft", 3), ("control", "input-bg", 3),
        ("gold-strong", "bg", 3), ("gold-strong", "soft", 3),
    ]:
        dark, light = sorted(_luminance(tokens["--ui-" + key][1:]) for key in (foreground, background))
        assert (light + .05) / (dark + .05) >= minimum, (theme, foreground, background)


def test_night_tokens_match_template_and_paper_names():
    root = CSS.parents[2]
    template = root / "manuals/projects/app_foundation/ui/ui_template.html"
    reference = _theme_tokens(template.read_text(encoding="utf-8"), "night")
    night = _app_theme("night")
    assert {name: night[name] for name in reference} == reference
    assert night.keys() == _app_theme("paper").keys()


def test_encounter_queue_uses_night_tokens():
    assert "--rq-" not in (CSS / "preset_deployment.css").read_text(encoding="utf-8")
    modals = CSS.parents[1] / "js/modals"
    for filename in ("preset_deployment_browser.js", "encounter_placement.js"):
        source = (modals / filename).read_text(encoding="utf-8")
        assert ".dataset.theme = 'night'" in source
