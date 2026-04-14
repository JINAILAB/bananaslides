from __future__ import annotations

from pathlib import Path

from bananaslides.domain.models import DetectionBox, ElementCategory, SlideSize
from bananaslides.modules.detection.base import TextDetector


class FullSlideTextDetector(TextDetector):
    """Treat the whole slide as one OCR region and let OCR detection find text lines."""

    backend_name = "full_slide_text_detector"

    def detect(self, slide_image_path: Path, slide_size: SlideSize) -> list[DetectionBox]:
        if not slide_image_path.exists():
            raise FileNotFoundError(f"Slide image not found: {slide_image_path}")
        return [
            DetectionBox(
                box_id="t0001",
                category=ElementCategory.TEXT,
                x=0.0,
                y=0.0,
                width=float(slide_size.width_px),
                height=float(slide_size.height_px),
                confidence=1.0,
                label="full slide",
            )
        ]
