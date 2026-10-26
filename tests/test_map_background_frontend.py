import json
import re
import subprocess
from pathlib import Path


def _apply_sequence(images):
    source = Path("static/js/visual/visual_map.js").read_text(encoding="utf-8")
    match = re.search(r"window\.applyBattleMapBackground = function[\s\S]+?\n\};", source)
    assert match, "applyBattleMapBackground not found"
    script = f"""
const window = {{}};
{match.group(0)}
const mapEl = {{ style: {{ backgroundImage: '', backgroundSize: '', backgroundRepeat: '', backgroundPosition: '' }} }};
const snapshots = {json.dumps(images)}.map((image) => {{
    window.applyBattleMapBackground(mapEl, image);
    return {{ ...mapEl.style }};
}});
process.stdout.write(JSON.stringify(snapshots));
"""
    result = subprocess.run(["node", "-e", script], capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(result.stdout)


def test_background_image_is_shown_contained_and_centered():
    [style] = _apply_sequence(["https://example.com/bg.png"])
    assert style == {
        "backgroundImage": "url('https://example.com/bg.png')",
        "backgroundSize": "contain",
        "backgroundRepeat": "no-repeat",
        "backgroundPosition": "center",
    }


def test_removing_background_clears_all_inline_styles_to_restore_css_grid():
    _, style = _apply_sequence(["https://example.com/bg.png", None])
    assert style == {
        "backgroundImage": "",
        "backgroundSize": "",
        "backgroundRepeat": "",
        "backgroundPosition": "",
    }
