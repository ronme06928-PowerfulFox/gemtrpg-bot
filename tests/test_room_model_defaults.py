from flask import Flask

from extensions import db
from models import Room


def test_room_data_default_uses_callable_dict():
    default = Room.__table__.c.data.default

    assert default is not None
    assert default.is_callable
    assert default.arg(None) == {}


def test_room_data_default_creates_independent_empty_dicts():
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)

    with app.app_context():
        db.create_all()
        room_a = Room(name="room-a")
        room_b = Room(name="room-b")
        db.session.add_all([room_a, room_b])
        db.session.commit()

        assert room_a.data == {}
        assert room_b.data == {}
        assert room_a.data is not room_b.data

        db.session.remove()
        db.drop_all()
