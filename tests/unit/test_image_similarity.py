# tests/unit/test_image_similarity.py
import sys
import pytest
from unittest.mock import patch
from core.image_similarity import similarity_available, compute_phash_similarity


def test_similarity_available_returns_bool():
    result = similarity_available()
    assert isinstance(result, bool)


def test_compute_phash_similarity_raises_import_error_when_missing():
    """When imagehash is not importable, raises ImportError with helpful message."""
    with patch.dict(sys.modules, {"imagehash": None, "PIL": None, "PIL.Image": None}):
        with pytest.raises(ImportError, match="uv add pillow imagehash"):
            compute_phash_similarity("a.png", "b.png")
