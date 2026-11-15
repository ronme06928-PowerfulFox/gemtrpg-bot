"""Paper theme contract for both management workspaces."""
from pathlib import Path
import re

import pytest


CSS = Path(__file__).resolve().parents[1] / "static" / "css" / "modules"


@pytest.mark.parametrize("filename", ["master_data.css", "unit_management.css"])
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


def test_paper_text_and_control_contrast():
    colors = dict(re.findall(r"--ui-([\w-]+):\s*#([a-f0-9]{6})\b", (CSS / "common_ui.css").read_text(encoding="utf-8")))
    assert "input-bg" in colors
    for foreground, background, minimum in [
        ("text", "bg", 4.5), ("sub", "soft", 4.5), ("sub", "primary-soft", 4.5),
        ("on-primary", "primary", 4.5), ("danger", "danger-soft", 4.5),
        ("warn", "warn-soft", 4.5), ("add", "add-soft", 4.5),
        ("ally", "ally-soft", 4.5), ("enemy", "enemy-soft", 4.5),
        ("control", "bg", 3), ("control", "soft", 3), ("control", "input-bg", 3),
        ("gold-strong", "bg", 3), ("gold-strong", "soft", 3),
    ]:
        dark, light = sorted(_luminance(colors[key]) for key in (foreground, background))
        assert (light + .05) / (dark + .05) >= minimum, (foreground, background)
