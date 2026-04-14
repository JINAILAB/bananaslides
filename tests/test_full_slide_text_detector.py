from __future__ import annotations

from pathlib import Path

from PIL import Image

from bananaslides.domain.models import ElementCategory, SlideSize
from bananaslides.modules.detection.full_slide_text_detector import FullSlideTextDetector


def test_full_slide_text_detector_returns_one_detection_covering_slide(tmp_path: Path) -> None:
    slide_path = tmp_path / "slide.png"
    Image.new("RGB", (1200, 800), "white").save(slide_path)

    detector = FullSlideTextDetector()
    detections = detector.detect(slide_path, SlideSize(width_px=1200, height_px=800))

    assert len(detections) == 1
    detection = detections[0]
    assert detection.box_id == "t0001"
    assert detection.category is ElementCategory.TEXT
    assert detection.x == 0.0
    assert detection.y == 0.0
    assert detection.width == 1200.0
    assert detection.height == 800.0
    assert detection.label == "full slide"
