from html.parser import HTMLParser
from pathlib import Path

from app import create_app

ROOT = Path(__file__).resolve().parents[1]
HELP_URL = "/static/help/master_data.html"


class HelpMarkup(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.ids = set()
        self.anchors = set()
        self.images = []
        self.labels = set()
        self._ui = False
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "id" in attrs:
            self.ids.add(attrs["id"])
        if tag == "a" and attrs.get("href", "").startswith("#"):
            self.anchors.add(attrs["href"][1:])
        if tag == "img":
            self.images.append(attrs["src"])
        if tag == "b":
            self._ui = "ui" in attrs.get("class", "").split()

    def handle_endtag(self, tag):
        if tag == "b":
            self._ui = False

    def handle_data(self, data):
        if self._ui:
            self.labels.add(data.strip())


def test_master_data_help_is_public_and_its_assets_and_links_resolve():
    app = create_app({"TESTING": True}, run_startup=False, register_sockets=False)
    client = app.test_client()
    page = client.get(HELP_URL)
    assert page.status_code == 200
    markup = HelpMarkup(page.get_data(as_text=True))
    assert markup.anchors and markup.anchors <= markup.ids
    assert len(markup.images) == 6
    for src in markup.images:
        response = client.get("/static/help/" + src)
        assert response.status_code == 200, src
        assert response.mimetype == "image/png", src


def test_master_data_help_uses_labels_from_the_workspace():
    html = (ROOT / "static/help/master_data.html").read_text(encoding="utf-8")
    source = "\n".join(path.read_text(encoding="utf-8") for path in (ROOT / "static/js/master_data").glob("*.js"))
    markup = HelpMarkup(html)
    assert markup.labels
    assert not sorted(label for label in markup.labels if label not in source)

