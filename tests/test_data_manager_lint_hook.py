"""計画書31 Phase 4: update_all_data() の lint fail-closed フックのテスト。

Google Sheets 取得・DB アクセスを避けるため、スキルデータ以外の更新ステップ
（アイテム/輝化スキル/特殊パッシブ/バフ図鑑/用語辞書/召喚テンプレート）は
それぞれのローダーの refresh をモックして成功させ、
lint フックの成否だけが update_all_data() の戻り値を左右することを確認する。
"""
import manager.data_manager as data_manager


def _stub_other_steps(monkeypatch):
    from manager.items.loader import item_loader
    from manager.radiance.loader import radiance_loader
    from manager.passives.loader import passive_loader
    from manager.buffs.loader import buff_catalog_loader
    from manager.glossary.loader import glossary_catalog_loader
    import manager.summons.loader as summons_loader

    monkeypatch.setattr(item_loader, "refresh", lambda: [{"id": "dummy"}])
    monkeypatch.setattr(radiance_loader, "refresh", lambda: [{"id": "dummy"}])
    monkeypatch.setattr(passive_loader, "refresh", lambda: [{"id": "dummy"}])
    monkeypatch.setattr(buff_catalog_loader, "refresh", lambda: [{"id": "dummy"}])
    monkeypatch.setattr(glossary_catalog_loader, "refresh", lambda: [{"id": "dummy"}])
    monkeypatch.setattr(summons_loader, "refresh_summon_templates", lambda: [{"id": "dummy"}])


def test_update_all_data_fails_when_lint_finds_errors(monkeypatch):
    monkeypatch.setattr(data_manager, "fetch_and_save_sheets_data", lambda: True)
    _stub_other_steps(monkeypatch)

    import scripts.skill_catalog_tool as tool
    monkeypatch.setattr(tool, "load_skills", lambda: {"S-BROKEN": {}})
    monkeypatch.setattr(
        tool, "lint_catalog",
        lambda skills: [{"skill_id": "S-BROKEN", "path": "p", "error": "invalid JSON"}],
    )

    assert data_manager.update_all_data() is False


def test_update_all_data_succeeds_when_lint_is_clean(monkeypatch):
    monkeypatch.setattr(data_manager, "fetch_and_save_sheets_data", lambda: True)
    _stub_other_steps(monkeypatch)

    import scripts.skill_catalog_tool as tool
    monkeypatch.setattr(tool, "load_skills", lambda: {})
    monkeypatch.setattr(tool, "lint_catalog", lambda skills: [])

    assert data_manager.update_all_data() is True


def test_update_all_data_skips_lint_when_skill_fetch_already_failed(monkeypatch):
    monkeypatch.setattr(data_manager, "fetch_and_save_sheets_data", lambda: False)
    _stub_other_steps(monkeypatch)

    import scripts.skill_catalog_tool as tool
    calls = []
    monkeypatch.setattr(tool, "lint_catalog", lambda skills: calls.append(1) or [])

    assert data_manager.update_all_data() is False
    assert calls == [], "スキル取得自体が失敗した場合は lint を実行しない"
