from flask import Flask

from extensions import db
from manager.image_manager import get_images, register_image


def _make_app():
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)
    return app


def test_player_cannot_see_own_gm_only_image():
    app = _make_app()
    with app.app_context():
        db.create_all()
        register_image("https://example.com/public.png", "public", "public", "user-1", visibility="public")
        register_image("https://example.com/gm.png", "gm", "gm", "user-1", visibility="gm")

        images = get_images(user_id="user-1", is_gm=False)

        assert [img["name"] for img in images] == ["public"]
        db.session.remove()
        db.drop_all()


def test_gm_can_see_own_gm_only_image():
    app = _make_app()
    with app.app_context():
        db.create_all()
        register_image("https://example.com/public.png", "public", "public", "gm-user", visibility="public")
        register_image("https://example.com/gm.png", "gm", "gm", "gm-user", visibility="gm")

        images = get_images(user_id="gm-user", is_gm=True)
        names = {img["name"] for img in images}

        assert names == {"public", "gm"}
        db.session.remove()
        db.drop_all()


def test_player_can_only_see_public_default_images():
    app = _make_app()
    with app.app_context():
        db.create_all()
        register_image("https://example.com/default-public.png", "default-public", "default public", "system", image_type="default", visibility="public")
        register_image("https://example.com/default-gm.png", "default-gm", "default gm", "system", image_type="default", visibility="gm")

        images = get_images(user_id="user-1", is_gm=False)

        assert [img["name"] for img in images] == ["default public"]
        db.session.remove()
        db.drop_all()
