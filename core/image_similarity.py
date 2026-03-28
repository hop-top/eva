"""Perceptual similarity utilities for image evaluation.

Requires optional extras: uv add --optional image pillow imagehash
Falls back to hash-based similarity when ML embeddings unavailable.
"""
from __future__ import annotations


def compute_phash_similarity(image_path_a: str, image_path_b: str) -> float:
    """Compute perceptual hash similarity between two image files.
    Returns float in [0.0, 1.0] where 1.0 = identical.
    Requires 'pillow' and 'imagehash' packages.
    """
    try:
        import imagehash
        from PIL import Image
        hash_a = imagehash.phash(Image.open(image_path_a))
        hash_b = imagehash.phash(Image.open(image_path_b))
        max_diff = 64  # pHash max hamming distance
        distance = hash_a - hash_b
        return max(0.0, 1.0 - (distance / max_diff))
    except ImportError:
        raise ImportError(
            "Image similarity requires: uv add pillow imagehash"
        )


def similarity_available() -> bool:
    """Check if image similarity packages are installed."""
    try:
        import imagehash  # noqa: F401
        from PIL import Image  # noqa: F401
        return True
    except ImportError:
        return False
