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
