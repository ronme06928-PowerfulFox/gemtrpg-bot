from types import SimpleNamespace

from manager.auth import (
    hash_gm_pin,
    is_valid_gm_pin,
    is_valid_master_key,
    verify_gm_pin,
    verify_master_key,
)


def test_gm_pin_accepts_exactly_four_digits():
    assert is_valid_gm_pin("1234")
    assert not is_valid_gm_pin("123")
    assert not is_valid_gm_pin("12345")
    assert not is_valid_gm_pin("abcd")


def test_gm_pin_is_verified_against_hash():
    room = SimpleNamespace(gm_pin_hash=hash_gm_pin("2468"))

    assert verify_gm_pin(room, "2468")
    assert not verify_gm_pin(room, "1357")
    assert not verify_gm_pin(room, "24680")


def test_master_key_requires_configured_eight_digit_match(monkeypatch):
    monkeypatch.setenv("GM_MASTER_KEY", "12345678")

    assert is_valid_master_key("12345678")
    assert verify_master_key("12345678")
    assert not verify_master_key("87654321")
    assert not verify_master_key("1234")


def test_master_key_is_disabled_when_env_is_missing(monkeypatch):
    monkeypatch.delenv("GM_MASTER_KEY", raising=False)

    assert not verify_master_key("12345678")

