from dataclasses import dataclass
from pathlib import Path


MAX_IMAGE_UPLOAD_BYTES = 10 * 1024 * 1024
ALLOWED_IMAGE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".gif", ".webp"})
ALLOWED_IMAGE_MIME_TYPES = frozenset({
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/webp",
})

_IMAGE_SIGNATURES = {
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/gif": (b"GIF87a", b"GIF89a"),
    "image/webp": (b"RIFF",),
}


@dataclass(frozen=True)
class ImageUploadValidationResult:
    ok: bool
    error: str | None = None


def validate_image_upload(file_storage) -> ImageUploadValidationResult:
    filename = str(getattr(file_storage, "filename", "") or "")
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_IMAGE_EXTENSIONS:
        return ImageUploadValidationResult(False, "許可されていない画像形式です。")

    mimetype = str(getattr(file_storage, "mimetype", "") or "").lower()
    if mimetype not in ALLOWED_IMAGE_MIME_TYPES:
        return ImageUploadValidationResult(False, "画像のMIMEタイプが不正です。")

    size = _get_stream_size(file_storage)
    if size is None:
        return ImageUploadValidationResult(False, "画像サイズを確認できません。")
    if size > MAX_IMAGE_UPLOAD_BYTES:
        return ImageUploadValidationResult(False, "画像サイズが上限を超えています。")

    header = _read_header(file_storage, 16)
    if not _matches_signature(mimetype, header):
        return ImageUploadValidationResult(False, "画像ファイルの内容が形式と一致しません。")

    return ImageUploadValidationResult(True)


def _get_stream_size(file_storage):
    stream = getattr(file_storage, "stream", None)
    if stream is None:
        return None

    try:
        current = stream.tell()
        stream.seek(0, 2)
        size = stream.tell()
        stream.seek(current)
        return size
    except (OSError, ValueError):
        content_length = getattr(file_storage, "content_length", None)
        return content_length if isinstance(content_length, int) and content_length >= 0 else None


def _read_header(file_storage, length):
    stream = getattr(file_storage, "stream", None)
    if stream is None:
        return b""

    try:
        current = stream.tell()
        stream.seek(0)
        header = stream.read(length)
        stream.seek(current)
        return header
    except (OSError, ValueError):
        return b""


def _matches_signature(mimetype, header):
    signatures = _IMAGE_SIGNATURES.get(mimetype)
    if not signatures:
        return False
    if mimetype == "image/webp":
        return header.startswith(b"RIFF") and header[8:12] == b"WEBP"
    return any(header.startswith(sig) for sig in signatures)
