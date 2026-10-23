from pathlib import Path

import pytest

from app import create_app

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def client(tmp_path):
    app = create_app(
        config={
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{(tmp_path / 'manual_pdf.db').as_posix()}",
            "SQLALCHEMY_ENGINE_OPTIONS": {},
        },
        run_startup=False,
        register_sockets=False,
    )
    return app.test_client()


@pytest.mark.parametrize("url,source", [
    ("/manuals/rulebook.pdf", ROOT / "typst_manual" / "全体マニュアル" / "main.pdf"),
    ("/manuals/guide.pdf", ROOT / "typst_manual" / "操作ガイド" / "main.pdf"),
])
def test_manual_pdf_is_served_as_latest_pdf(client, url, source):
    response = client.get(url)
    assert response.status_code == 200
    assert response.mimetype == "application/pdf"
    assert response.data == source.read_bytes()
    # URLは版が変わっても同じなので、ブラウザに古い版を使い続けさせない
    assert "no-cache" in response.headers["Cache-Control"]
    assert "inline" in response.headers["Content-Disposition"]


def test_unknown_manual_pdf_is_not_found(client):
    assert client.get("/manuals/main.pdf").status_code == 404
    assert client.get("/manuals/../app.py").status_code == 404
