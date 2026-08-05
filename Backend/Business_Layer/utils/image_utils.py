# Backend/Business_Layer/utils/image_utils.py
"""Image loading and color-space conversion helpers.

Kept separate from ocr_provider.py so the OCR engine never has to
know how an image arrived (uploaded PNG/JPEG/TIFF vs. a rasterized PDF
page) — it only ever receives a ready-to-use OpenCV (BGR) array.
"""
from __future__ import annotations

import io

import numpy as np
from PIL import Image

from Backend.Business_Layer.utils.exceptions import OCRFailure


def load_image(content: bytes) -> Image.Image:
    """Load raw image bytes (PNG/JPEG/TIFF or rasterized PDF page) into a PIL Image."""
    try:
        image = Image.open(io.BytesIO(content))
        image.load()
        return image.convert("RGB")
    except Exception as exc:
        raise OCRFailure(f"Unable to load image: {exc}") from exc


def convert_to_cv(image: Image.Image) -> np.ndarray:
    """Convert a PIL (RGB) image to an OpenCV-style BGR numpy array for OCR."""
    rgb_array = np.array(image)
    return rgb_array[:, :, ::-1].copy()
