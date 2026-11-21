import re
from pathlib import Path
from types import SimpleNamespace

from manager import practice_rooms


ROOT = Path(__file__).resolve().parents[1]
CAVE = '/static/images/backgrounds/暗い遺跡洞窟.webp'
OBSOLETE_CAVE = Path(CAVE).stem + '.png'


def test_practice_room_background_points_to_a_bundled_webp(monkeypatch):
    monkeypatch.setattr(practice_rooms, '_reaper_running', True)
    name, state = practice_rooms.create(SimpleNamespace(id='test-cave', name='GM'), {}, [])
    try:
        assert state['battle_map_data']['background_image'] == CAVE
        assert (ROOT / CAVE.lstrip('/')).is_file()
    finally:
        practice_rooms.drop(name)


def test_deleted_background_has_no_code_references():
    assert not (ROOT / 'static/images/backgrounds' / OBSOLETE_CAVE).exists()
    for folder in ('manager', 'scripts', 'static/js'):
        for source in (ROOT / folder).rglob('*'):
            if source.suffix in ('.py', '.js', '.mjs', '.html', '.css'):
                assert OBSOLETE_CAVE not in source.read_text(encoding='utf-8'), source


def test_bundled_image_urls_and_cache_headers(monkeypatch):
    monkeypatch.setenv('GEMTRPG_SKIP_IMPORT_STARTUP', '1')
    from app import create_app

    app = create_app(
        config={'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:', 'SQLALCHEMY_ENGINE_OPTIONS': {}},
        run_startup=False,
        register_sockets=False,
    )
    with app.test_client() as client:
        for image_type in ('character', 'background'):
            images = client.get('/api/local_images', query_string={'type': image_type}).get_json()
            assert images and all(image['url'].startswith('/static/images/') for image in images)
        assert CAVE in {image['url'] for image in images}

        for url in ('/static/images/bleed.png', '/images/bleed.png'):
            response = client.get(url)
            assert response.status_code == 200
            assert response.cache_control.public
            assert response.cache_control.max_age == 86400
            cached = client.get(url, headers={'If-None-Match': response.headers['ETag']})
            assert cached.status_code == 304
            assert cached.data == b''

        cave = client.get(CAVE)
        assert cave.status_code == 200
        assert cave.mimetype == 'image/webp'
        assert cave.cache_control.max_age == 86400


def test_status_icon_templates_generate_canonical_image_urls():
    for filename, expected_count in (
        ('visual/visual_map.js', 2),
        ('battle/components/resolve_flow_fx.js', 2),
        ('battle/components/resolve_stacks.js', 1),
    ):
        source = (ROOT / 'static/js' / filename).read_text(encoding='utf-8')
        prefixes = re.findall(r'((?:[\w-]+/|/)*images/)\$\{[^}]*icon[^}]*\}', source)
        assert prefixes == ['/static/images/'] * expected_count
