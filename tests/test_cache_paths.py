"""Cache reads use the current location without migrating old local files."""

import importlib
import json

import pytest

from manager import cache_paths


@pytest.mark.parametrize("module_name,reader,memory", [
    ("manager.items.loader", "load_items", "all_item_data"),
    ("manager.passives.loader", "load_passives", "all_passive_data"),
    ("manager.radiance.loader", "load_skills", "all_radiance_data"),
    ("manager.summons.loader", "load_summon_templates", "all_summon_template_data"),
])
def test_readers_use_public_dictionary_without_any_file_access(monkeypatch, module_name, reader, memory):
    import extensions
    module = importlib.import_module(module_name)
    records = {"current": {"name": "DB公開版"}}
    monkeypatch.setattr(extensions, memory, records)
    monkeypatch.setattr(cache_paths, "load_json_cache", lambda _: pytest.fail("辞書の読み出しでファイルを読まない"))
    instance = {"load_items": "item_loader", "load_passives": "passive_loader", "load_skills": "radiance_loader"}.get(reader)
    read = getattr(getattr(module, instance), reader) if instance else getattr(module, reader)
    assert read() is records
    replacement = {"next": {"name": "公開後"}}
    monkeypatch.setattr(extensions, memory, replacement)
    assert read() is replacement


def test_cache_read_returns_data_without_rewriting_file(tmp_path):
    path = tmp_path / "catalog.json"
    path.write_text('{"name":"宝石"}', encoding="utf-8")
    original = path.read_bytes()
    assert cache_paths.load_json_cache(path) == {"name": "宝石"}
    assert path.read_bytes() == original


def test_missing_cache_read_does_not_create_directory(tmp_path):
    assert cache_paths.load_json_cache(tmp_path / "missing" / "catalog.json") is None
    assert list(tmp_path.iterdir()) == []


def test_invalid_json_is_reported_without_rewriting_file(tmp_path):
    path = tmp_path / "catalog.json"
    path.write_text('{"broken":', encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        cache_paths.load_json_cache(path)
    assert path.read_text(encoding="utf-8") == '{"broken":'


def test_explicit_cache_save_creates_directory_and_roundtrips(tmp_path, monkeypatch):
    directory = tmp_path / "data" / "cache"
    monkeypatch.setattr(cache_paths, "CACHE_DIR", directory)
    path = directory / "catalog.json"
    data = {"name": "宝石", "effects": []}
    cache_paths.save_json_cache(path, data)
    assert cache_paths.load_json_cache(path) == data
    assert "宝石" in path.read_text(encoding="utf-8")
