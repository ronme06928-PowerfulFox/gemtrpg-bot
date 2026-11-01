"""Cache reads use the current location without migrating old local files."""

import importlib
import json

import pytest

from manager import cache_paths


@pytest.mark.parametrize(
    "module_name, loader_class, cache_symbol, legacy_symbol",
    [
        ("manager.items.loader", "ItemLoader", "ITEMS_CACHE_FILE", "LEGACY_ITEMS_CACHE_FILE"),
        ("manager.passives.loader", "PassiveLoader", "PASSIVES_CACHE_FILE", "LEGACY_PASSIVES_CACHE_FILE"),
    ],
)
def test_loader_does_not_import_or_copy_old_root_cache(
    tmp_path, monkeypatch, module_name, loader_class, cache_symbol, legacy_symbol
):
    module = importlib.import_module(module_name)
    current = tmp_path / "data" / "cache" / "catalog.json"
    old = tmp_path / "catalog.json"
    old.write_text('{"obsolete": {"name": "旧配置"}}', encoding="utf-8")
    original = old.read_bytes()
    monkeypatch.setattr(cache_paths, "CACHE_DIR", current.parent)
    monkeypatch.setattr(module, cache_symbol, current)
    # Inject a former-location file even after the old constant is removed.
    monkeypatch.setattr(module, legacy_symbol, old, raising=False)

    assert getattr(module, loader_class)()._load_cache() is None
    assert old.read_bytes() == original
    assert not current.parent.exists()


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
