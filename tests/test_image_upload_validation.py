from io import BytesIO

from werkzeug.datastructures import FileStorage

from manager.image_upload_validation import MAX_IMAGE_UPLOAD_BYTES, validate_image_upload


def _file_storage(filename, mimetype, payload):
    return FileStorage(
        stream=BytesIO(payload),
        filename=filename,
        content_type=mimetype,
    )


def test_validate_image_upload_accepts_png():
    file = _file_storage("token.png", "image/png", b"\x89PNG\r\n\x1a\n" + b"0" * 32)

    result = validate_image_upload(file)

    assert result.ok is True


def test_validate_image_upload_rejects_disallowed_extension():
    file = _file_storage("token.svg", "image/svg+xml", b"<svg></svg>")

    result = validate_image_upload(file)

    assert result.ok is False
    assert "形式" in result.error


def test_validate_image_upload_rejects_mimetype_mismatch():
    file = _file_storage("token.png", "text/plain", b"\x89PNG\r\n\x1a\n" + b"0" * 32)

    result = validate_image_upload(file)

    assert result.ok is False
    assert "MIME" in result.error


def test_validate_image_upload_rejects_signature_mismatch():
    file = _file_storage("token.png", "image/png", b"not actually an image")

    result = validate_image_upload(file)

    assert result.ok is False
    assert "内容" in result.error


def test_validate_image_upload_rejects_oversized_payload():
    file = _file_storage("token.jpg", "image/jpeg", b"\xff\xd8\xff" + b"0" * MAX_IMAGE_UPLOAD_BYTES)

    result = validate_image_upload(file)

    assert result.ok is False
    assert "上限" in result.error


def test_validate_image_upload_accepts_webp_signature():
    file = _file_storage("token.webp", "image/webp", b"RIFF1234WEBP" + b"0" * 32)

    result = validate_image_upload(file)

    assert result.ok is True
