from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from bananaslides.domain.models import SlideSize


def infer_slide_size(image_path: Path) -> SlideSize:
    with Image.open(image_path) as image:
        width, height = image.size
    return SlideSize(width_px=width, height_px=height)


def load_rgb_array(image_path: Path) -> np.ndarray:
    return np.asarray(Image.open(image_path).convert("RGB"), dtype=np.uint8)
