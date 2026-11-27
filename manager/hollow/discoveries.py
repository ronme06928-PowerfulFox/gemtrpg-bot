"""Private, durable discoveries of successful special fusions."""
from sqlalchemy.exc import IntegrityError

from extensions import db
from models import HollowRecipeDiscovery


def discover(user_id, recipe):
    key = (user_id, recipe["id"])
    if db.session.get(HollowRecipeDiscovery, key) is not None:
        return
    snapshot = {field: recipe[field] for field in ("material_ids", "result_id")}
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
