import copy
import re

import pytest
from flask import Flask

from manager.battle.effect_handlers import (
    EFFECT_HANDLERS,
    EFFECT_SCHEMAS,
    render_effect_summary,
)
from manager.json_rule_v2 import normalize_skill_rule_object
from plugins import CUSTOM_EFFECT_SCHEMAS, EFFECT_REGISTRY


FIELD_TYPES = {
    "int", "number", "string", "bool", "json", "state_ref", "buff_ref",
    "skill_ref", "summon_ref", "glossary_ref",
}


def test_schema_keys_match_registries():
    assert set(EFFECT_SCHEMAS) == set(EFFECT_HANDLERS) | {"CUSTOM_EFFECT"}
    assert set(CUSTOM_EFFECT_SCHEMAS) == set(EFFECT_REGISTRY)
    assert {key for key, schema in EFFECT_SCHEMAS.items() if schema["internal"]} == {
        "FORCE_UNOPPOSED", "APPLY_FISSURE_BUFFED",
    }


def check_fields(fields):
    assert isinstance(fields, dict)
    assert not (set(fields) & {"timing", "type", "target", "condition"})
    for field in fields.values():
        assert field["type"] in FIELD_TYPES
        assert type(field["required"]) is bool
        assert field["label"]


@pytest.mark.parametrize("effect_type,schema", EFFECT_SCHEMAS.items())
def test_effect_schema_contract_and_example(effect_type, schema, buff_catalog_data):
    assert {"label", "description", "internal", "fields", "summary", "example"} <= schema.keys()
    assert schema["label"] and schema["description"] and schema["summary"]
    assert type(schema["internal"]) is bool
    check_fields(schema["fields"])
    assert set(re.findall(r"\{([^{}]+)\}", schema["summary"])) <= set(schema["fields"]) | {"target"}
    example = schema["example"]
    assert example["type"] == effect_type
    for key, field in schema["fields"].items():
        if field["required"]:
            value = example
            for part in key.split("."):
                value = value[part]
            assert value is not None
    before = copy.deepcopy(example)
    normalized = normalize_skill_rule_object({
        "schema": "skill_json_rule_v2", "effects": [example],
    }, strict=True)
    assert normalized["effects"][0]["type"] == effect_type
    assert "?" not in render_effect_summary(example)
    assert example == before


@pytest.mark.parametrize("schema", CUSTOM_EFFECT_SCHEMAS.values())
def test_custom_effect_schema_contract(schema):
    assert schema["label"] and schema["description"]
    check_fields(schema["fields"])


@pytest.mark.parametrize("target,label", [
    ("self", "自分"), ("target", "対象"), ("ALL_ENEMIES", "敵全員"),
])
def test_summary_target_and_missing_values(target, label):
    assert render_effect_summary({"type": "APPLY_STATE", "target": target}) == f"{label}に?を?付与"


def test_summary_nested_values_and_literal_braces(monkeypatch):
    monkeypatch.setitem(EFFECT_SCHEMAS, "TEST", {"summary": "{target}:{data.count}:{value}:{missing}"})
    effect = {"type": "TEST", "target": "self", "data": {"count": 0}, "value": "{target}"}
    assert render_effect_summary(effect) == "自分:0:{target}:?"
    assert render_effect_summary({"type": "UNKNOWN"}) == "?"
    assert render_effect_summary({"type": "TEST", "data": None}) == "?:?:?:?"


def test_effect_schemas_api_is_public_and_returns_both_registries():
    from app import register_http_routes

    app = Flask(__name__)
    register_http_routes(app)
    response = app.test_client().get("/api/effect_schemas")
    assert response.status_code == 200
    assert response.get_json() == {
        "effect_types": EFFECT_SCHEMAS,
        "custom_effects": CUSTOM_EFFECT_SCHEMAS,
    }
