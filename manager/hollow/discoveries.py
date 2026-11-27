"""Private, durable discoveries of successful special fusions."""
from sqlalchemy.exc import IntegrityError

from extensions import db
from models import HollowRecipeDiscovery


def _names(row, definitions):
    def name(key):
        return definitions.get(key, {}).get("name") or key

    return {"material_names": [name(key) for key in row["material_ids"]], "result_name": name(row["result_id"])}


def discover(user_id, recipe):
    from manager.hollow.runtime import prepare_rewards

    key = (user_id, recipe["id"])
    if db.session.get(HollowRecipeDiscovery, key) is not None:
        return
    snapshot = {field: recipe[field] for field in ("material_ids", "result_id")}
    snapshot.update(_names(snapshot, prepare_rewards().get("relic", {})))
    db.session.add(HollowRecipeDiscovery(user_id=user_id, recipe_id=key[1], recipe=snapshot))
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        if db.session.get(HollowRecipeDiscovery, key) is None:
            raise


def discovered(user_id):
    return [{"recipe_id": row.recipe_id, **row.recipe}
            for row in HollowRecipeDiscovery.query.filter_by(user_id=user_id)
            .order_by(HollowRecipeDiscovery.recipe_id)]


def named_discoveries(user_id):
    from manager.hollow.runtime import prepare_rewards

    definitions = prepare_rewards().get("relic", {})

    return [row if "material_names" in row else {**row, **_names(row, definitions)}
            for row in discovered(user_id)]
