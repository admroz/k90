"""Supported image signatures shared by Telegram intake and HTTP validation."""

MAX_IMAGE_BYTES = 5_000_000
IMAGE_EXTENSIONS = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".png": "image/png", ".webp": "image/webp",
}


def image_mime_type(data: bytes) -> str | None:
    """Identify a supported image by its signature, not transport metadata."""
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"
    return None


MAX_BATCH_BYTES = 10_000_000
MAX_BATCH_IMAGES = 4


def validate_batch(images):
    """Strict opaque image validation shared by both trusted intake paths."""
    from k90_memory.privacy import validate_image_url
    if len(images) > MAX_BATCH_IMAGES:
        raise ValueError('Maksymalnie 4 zdjęcia w jednej wiadomości.')
    total = 0
    for url in images:
        if not isinstance(url, str) or not url.startswith("data:"):
            raise ValueError("Zdjęcie musi być lokalnym obrazem base64.")
        validate_image_url(url)
        body = url.partition(",")[2]
        total += len(body) // 4 * 3 - (len(body) - len(body.rstrip("=")))
        if total > MAX_BATCH_BYTES:
            raise ValueError('Zdjęcia mogą mieć łącznie maksymalnie 10 MB.')
    return total
