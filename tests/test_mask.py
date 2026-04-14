from __future__ import annotations

import numpy as np

from bananaslides.domain.models import OCRLine, OCRResult, SlideSize
from bananaslides.modules.inpainting.mask import build_text_mask_from_ocr_results


def test_build_text_mask_from_ocr_results_marks_line_boxes() -> None:
    mask = build_text_mask_from_ocr_results(
        slide_size=SlideSize(width_px=200, height_px=100),
        ocr_results=[
            OCRResult(
                box_id="t0001",
                text="Hello",
                lines=[
                    OCRLine(
                        text="Hello",
                        bbox=[[10.0, 20.0], [60.0, 20.0], [60.0, 40.0], [10.0, 40.0]],
                    )
                ],
            )
        ],
        padding_px=0,
    )

    array = np.asarray(mask, dtype=np.uint8)
    assert array[30, 30] == 255
    assert array[5, 5] == 0
