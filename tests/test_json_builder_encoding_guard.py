from pathlib import Path


def test_json_builder_html_utf8_and_key_labels_are_intact():
    path = Path("CharaCreator/json_definition_builder.html")
    raw = path.read_bytes()

    # Guard against BOM or accidental re-encoding side effects.
    assert not raw.startswith(b"\xef\xbb\xbf")

    text = raw.decode("utf-8")
    assert "<!doctype html>" in text
    assert "JSON定義ビルダー（rule_data / v2 strict）" in text
    assert "自然言語入力（3列）" in text
    assert "if(body.includes(\"血漿転化\"))" in text
    assert "if(body.includes(\"爆破誘導\") || body.includes(\"W-81\"))" in text

