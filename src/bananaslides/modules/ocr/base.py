from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Sequence

from bananaslides.domain.models import DetectionBox, OCRResult


class OcrEngine(ABC):
    @abstractmethod
    def recognize(self, slide_image_path: Path, detections: Sequence[DetectionBox]) -> list[OCRResult]:
        """Run OCR on detected text boxes."""

