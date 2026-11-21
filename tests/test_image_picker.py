import subprocess
from io import BytesIO
from pathlib import Path
from unittest.mock import Mock

from extensions import db
from models import ImageRegistry, User


ROOT = Path(__file__).resolve().parents[1]


def test_picker_prepares_files_and_uploads_cropped_webp():
    script = r'''
import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';

const drawn = [], encoded = [], forms = [], notices = [], revoked = [];
const nodes = new Map();
const node = () => ({style: {}, addEventListener() {}, remove() {}});
const modal = {...node(), querySelector(selector) {
  if (!nodes.has(selector)) nodes.set(selector, node());
  return nodes.get(selector);
}};
let failUpload = false, releaseUpload;
let nextSize = [4000, 2000];
class Image {
  set src(url) {
    if (!url.startsWith('blob:')) assert.equal(this.crossOrigin, 'anonymous');
    [this.naturalWidth, this.naturalHeight] = nextSize;
    this.onload?.();
  }
  async decode() {}
}
const window = {
  addEventListener() {}, removeEventListener() {}, showAppNotice(message) { notices.push(message); }
};
const document = {
  body: {appendChild() {}}, getElementById() { return null; },
  createElement(tag) {
    if (tag !== 'canvas') return modal;
    return {
      getContext() { return {drawImage(...args) { drawn.push(args.slice(1)); }}; },
      toBlob(done, type, quality) {
        encoded.push([this.width, this.height, type, quality]);
        done(new Blob(['encoded'], {type}));
      }
    };
  }
};
const context = vm.createContext({
  window, document, Image, FormData, console: {error() {}}, applySystemWindow() {},
  URL: {createObjectURL: () => 'blob:upload', revokeObjectURL: url => revoked.push(url)},
  async fetch(path, options) {
    assert.equal(path, '/api/upload_image');
    assert.equal(options.method, 'POST');
    forms.push(options.body);
    if (failUpload) return {ok: false, json: async () => ({error: 'rejected'})};
    await new Promise(resolve => { releaseUpload = resolve; });
    return {ok: true, json: async () => ({url: 'https://example.test/crop.webp', id: 'crop-id'})};
  }
});
vm.runInContext(fs.readFileSync('static/js/image_picker.js', 'utf8'), context);

const png = {type: 'image/png', name: 'upload.png'};
assert.equal((await context.preparePickerUpload(png, 'character')).type, 'image/webp');
assert.deepEqual(encoded.at(-1), [1024, 512, 'image/webp', 0.8]);
assert.equal((await context.preparePickerUpload(png, 'background')).type, 'image/webp');
assert.deepEqual(encoded.at(-1), [1920, 960, 'image/webp', 0.8]);
nextSize = [32, 120];
await context.preparePickerUpload(png, 'character');
assert.deepEqual(encoded.at(-1), [32, 120, 'image/webp', 0.8]);
const gif = {type: 'image/gif', name: 'animated.gif'};
assert.equal(await context.preparePickerUpload(gif, 'character'), gif);
await assert.rejects(context.preparePickerUpload({type: 'image/svg+xml', name: 'image.svg'}, 'character'));
assert.equal(encoded.length, 3);
assert.equal(revoked.length, 3);

nextSize = [800, 1600];
const original = {url: 'https://example.test/original.webp', name: 'original', visibility: 'gm'};
const selection = context.openImageCropperModal(original);
const click = nodes.get('#crop-apply-btn').onclick;
const upload = click();
await click();
releaseUpload();
await upload;
const result = await selection;
assert.equal(result.url, 'https://example.test/crop.webp');
assert.equal(result.croppedUrl, result.url);
assert.equal(result.originalUrl, original.url);
assert.deepEqual(encoded.at(-1), [512, 512, 'image/webp', 0.8]);
assert.deepEqual(drawn.at(-1), [0, 400, 800, 800, 0, 0, 512, 512]);
assert.equal(forms.length, 1);
assert.equal(forms[0].get('type'), 'crop');
assert.equal(forms[0].get('file').name.endsWith('.webp'), true);
assert.equal(forms[0].get('visibility'), 'gm');

failUpload = true;
const fallback = context.openImageCropperModal(original);
await nodes.get('#crop-apply-btn').onclick();
assert.equal((await fallback).croppedUrl, original.url);
assert.match(notices[0], /元画像を使用します/);
'''
    result = subprocess.run(
        ['node', '--input-type=module', '-e', script], cwd=ROOT,
        capture_output=True, text=True, encoding='utf-8', timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_crop_upload_uses_registry_type_and_stays_out_of_gallery(tmp_path, monkeypatch):
    monkeypatch.setenv('GEMTRPG_SKIP_IMPORT_STARTUP', '1')
    import app as app_module

    app = app_module.create_app(
        config={'SQLALCHEMY_DATABASE_URI': f"sqlite:///{(tmp_path / 'images.db').as_posix()}"},
        run_startup=False, register_sockets=False,
    )
    uploader = Mock(side_effect=[
        {'secure_url': 'https://example.test/original.webp', 'public_id': 'original'},
        {'secure_url': 'https://example.test/crop.webp', 'public_id': 'crop'},
    ])
    monkeypatch.setattr(app_module.cloudinary.uploader, 'upload', uploader)
    with app.app_context():
        db.create_all()
        db.session.add(User(id='image-gm', name='gm'))
        db.session.commit()
    with app.test_client() as client:
        with client.session_transaction() as session:
            session.update(user_id='image-gm', username='gm', auth_version=1, attribute='GM')
        for kind in ('character', 'crop'):
            response = client.post('/api/upload_image', data={
                'type': kind, 'name': kind, 'visibility': 'gm',
                'file': (BytesIO(b'RIFF\x04\x00\x00\x00WEBP'), f'{kind}.webp', 'image/webp'),
            })
            assert response.status_code == 200
        assert response.json['url'] == 'https://example.test/crop.webp'
        assert response.json['visibility'] == 'gm'
        for query in ({}, {'type': 'user'}, {'q': 'char'}):
            assert [item['name'] for item in client.get('/api/images', query_string=query).json] == ['character']
        assert client.get('/api/images?type=crop').json == []
        with app.app_context():
            assert db.session.get(ImageRegistry, response.json['id']).type == 'crop'
    assert [call.kwargs for call in uploader.call_args_list] == [{'folder': 'gemtrpg/characters'}] * 2
