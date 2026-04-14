from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw

from bananaslides.modules.inpainting.cv2_inpainter import Cv2Inpainter


def test_cv2_inpainter_fills_masked_region(tmp_path) -> None:
    slide_path = tmp_path / "slide.png"
    mask_path = tmp_path / "mask.png"
    output_path = tmp_path / "background.png"

    image = Image.new("RGB", (40, 20), "black")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 39, 19), fill=(32, 32, 32))
    draw.rectangle((2, 2, 7, 7), fill=(255, 255, 255))
    image.save(slide_path)

    mask = Image.new("L", (40, 20), 0)
    draw_mask = ImageDraw.Draw(mask)
    draw_mask.rectangle((2, 2, 7, 7), fill=255)
    mask.save(mask_path)

    inpainter = Cv2Inpainter(radius=3.0, feather_px=0)
    inpainter.inpaint(slide_path, mask_path, output_path)
    output = np.asarray(Image.open(output_path).convert("RGB"))

    assert tuple(output[0, 0]) == (32, 32, 32)
    assert tuple(output[4, 4]) != (255, 255, 255)
