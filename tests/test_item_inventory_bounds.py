from types import SimpleNamespace

import pytest

import events.socket_items as socket_items
from manager.items.usage_manager import ItemUsageManager


@pytest.mark.parametrize("inventory", [{}, {"I-TEST": 0}])
def test_use_item_rejects_missing_or_zero_inventory_before_effect(monkeypatch, inventory):
    manager = ItemUsageManager()
    user = {"id": "user-1", "name": "User", "inventory": dict(inventory)}
    target = {"id": "target-1", "name": "Target", "inventory": {}}

    monkeypatch.setattr(
        "manager.items.usage_manager.item_loader.get_item",
        lambda _item_id: pytest.fail("在庫不足時はアイテム定義・効果へ進まない"),
    )

    result = manager.use_item(user, target, "I-TEST", {"room": "room-1"})

    assert result["success"] is False
    assert result["consumed"] is False
    assert user["inventory"] == inventory
    assert "所持していません" in result["logs"][0]["message"]


@pytest.mark.parametrize(
    ("inventory", "remove_qty"),
    [
        ({}, 1),
        ({"I-TEST": 0}, 1),
        ({"I-TEST": 1}, 2),
    ],
)
def test_gm_remove_item_rejects_insufficient_inventory_without_side_effects(
    monkeypatch, inventory, remove_qty
):
    state = {
        "characters": [
            {"id": "target-1", "name": "Target", "inventory": dict(inventory)},
        ]
    }
    emitted = []
    logs = []
    state_updates = []
    saves = []

    monkeypatch.setattr(socket_items, "request", SimpleNamespace(sid="sid-gm"))
    monkeypatch.setattr(socket_items, "is_sid_in_room", lambda _sid, _room: True)
    monkeypatch.setattr(
        socket_items,
        "get_user_info_from_sid",
        lambda _sid: {"username": "GM", "attribute": "GM"},
    )
    monkeypatch.setattr(socket_items, "get_room_state", lambda _room: state)
    monkeypatch.setattr(
        socket_items,
        "item_loader",
        SimpleNamespace(get_item=lambda _item_id: {"id": "I-TEST", "name": "Test Item"}),
    )
    monkeypatch.setattr(
        socket_items,
        "emit",
        lambda event, payload=None, to=None: emitted.append((event, payload or {}, to)),
    )
    monkeypatch.setattr(socket_items, "broadcast_log", lambda *args: logs.append(args))
    monkeypatch.setattr(socket_items, "broadcast_state_update", lambda room: state_updates.append(room))
    monkeypatch.setattr(socket_items, "save_specific_room_state", lambda room: saves.append(room))

    socket_items.handle_gm_adjust_item(
        {"room": "room-1", "target_id": "target-1", "item_id": "I-TEST", "delta": -remove_qty}
    )

    assert state["characters"][0]["inventory"] == inventory
    assert emitted == [
        ("item_adjust_error", {"message": "Insufficient stock: Test Item for Target"}, None)
    ]
    assert logs == []
    assert state_updates == []
    assert saves == []


def test_gm_remove_item_consumes_exact_available_quantity(monkeypatch):
    state = {"characters": [{"id": "target-1", "name": "Target", "inventory": {"I-TEST": 1}}]}
    emitted = []
    logs = []
    state_updates = []
    saves = []

    monkeypatch.setattr(socket_items, "request", SimpleNamespace(sid="sid-gm"))
    monkeypatch.setattr(socket_items, "is_sid_in_room", lambda _sid, _room: True)
    monkeypatch.setattr(
        socket_items,
        "get_user_info_from_sid",
        lambda _sid: {"username": "GM", "attribute": "GM"},
    )
    monkeypatch.setattr(socket_items, "get_room_state", lambda _room: state)
    monkeypatch.setattr(
        socket_items,
        "item_loader",
        SimpleNamespace(get_item=lambda _item_id: {"id": "I-TEST", "name": "Test Item"}),
    )
    monkeypatch.setattr(socket_items, "emit", lambda *args, **kwargs: emitted.append((args, kwargs)))
    monkeypatch.setattr(socket_items, "broadcast_log", lambda *args: logs.append(args))
    monkeypatch.setattr(socket_items, "broadcast_state_update", lambda room: state_updates.append(room))
    monkeypatch.setattr(socket_items, "save_specific_room_state", lambda room: saves.append(room))

    socket_items.handle_gm_adjust_item(
        {"room": "room-1", "target_id": "target-1", "item_id": "I-TEST", "delta": -1}
    )

    assert state["characters"][0]["inventory"] == {}
    assert emitted == []
    assert logs == [("room-1", "GM removed Test Item x1 from Target", "info")]
    assert state_updates == ["room-1"]
    assert saves == ["room-1"]
