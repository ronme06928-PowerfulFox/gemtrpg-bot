"""The shared stage palette preserves the previous CSS values."""
import json
import re
from pathlib import Path

import pytest

from tests.test_management_ui_theme import CSS, _app_theme, _luminance


PALETTE = json.loads(
    (Path(__file__).parent / "fixtures/ui_stage_palette.json").read_text(encoding="utf-8")
)
CSS_COLOR = re.compile(
    r"#[0-9a-f]{3,8}\b|\b(?:rgba?|hsla?|hwb|oklch|oklab|lab|lch)\(|"
    r"(?<![-\w])(?:black|white|red|blue|green|gray|grey|orange|yellow)(?![-\w])",
    re.I,
)


@pytest.mark.parametrize("family", PALETTE)
def test_shared_palette_preserves_legacy_values(family):
    if family == "stage":
        actual = _app_theme("stage")
    else:
        common = (CSS / "common_ui.css").read_text(encoding="utf-8")
        actual = dict(re.findall(r"(--(?:ui|gem)-(?:fx|match)-[\w-]+):\s*([^;]+);", common))
    for name, expected in PALETTE[family].items():
        assert actual["--" + name] == expected, name


@pytest.mark.parametrize("filename", ["visual_battle.css", "motion_fx.css", "visual_duel.css"])
def test_encounter_css_paints_with_shared_tokens(filename):
    source = re.sub(r"/\*.*?\*/", "", (CSS / filename).read_text(encoding="utf-8"), flags=re.S)
    for selectors, declarations in re.findall(r"([^{}]+)\{([^{}]+)\}", source):
        if filename == "visual_battle.css" and "#resolve-flow-panel" not in selectors:
            continue
        values = re.sub(r"""("[^"]*"|'[^']*'|var\(\s*--[\w-]+)""", "", declarations)
        assert not CSS_COLOR.search(values), selectors


def test_stage_text_contrast_matches_the_previous_palette():
    old, actual = PALETTE["stage"], _app_theme("stage")

    def contrast(fg, bg):
        low, high = sorted(_luminance(value[1:]) for value in (fg, bg))
        return (high + .05) / (low + .05)

    for ink in ("ui-text", "ui-sub", "ui-gold"):
        for surface in ("ui-page", "ui-bg", "ui-stage-bg"):
            assert contrast(actual["--" + ink], actual["--" + surface]) == pytest.approx(
                contrast(old[ink], old[surface])
            )
