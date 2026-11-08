"""PR60-10: --updateは未移行の4種類だけ。通信はすべてモックする。"""
import builtins
import pytest
import manager.data_manager as data_manager


def stubs(monkeypatch, failed=None):
    from manager.items.loader import item_loader
    from manager.radiance.loader import radiance_loader
    from manager.passives.loader import passive_loader
    from manager.summons import loader as summons
    calls = []
    for name, loader, method in (("item", item_loader, "refresh"), ("radiance", radiance_loader, "refresh"),
                                 ("passive", passive_loader, "refresh"), ("summon", summons, "refresh_summon_templates")):
        def update(name=name):
            calls.append(name)
            return {} if name == failed else {"example": {}}
        monkeypatch.setattr(loader, method, update)
    return calls


def test_update_four_steps_without_skill_sheets_or_lint(monkeypatch, capsys):
    calls = stubs(monkeypatch)
    original = builtins.__import__
    def guarded(name, *args, **kwargs):
        assert not name.startswith(("scripts", "gspread", "manager.skill_catalog_validation", "manager.catalog"))
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", guarded)
    assert data_manager.update_all_data()
    assert calls == ["item", "radiance", "passive", "summon"]
    output = capsys.readouterr().out
    assert "【4/4】" in output and "【5/" not in output and "lint" not in output
    assert not hasattr(data_manager, "fetch_and_save_sheets_data")


@pytest.mark.parametrize("failed", ["item", "radiance", "passive", "summon"])
def test_update_failure_does_not_skip_remaining_types(monkeypatch, failed):
    calls = stubs(monkeypatch, failed)
    assert not data_manager.update_all_data()
    assert len(calls) == 4
