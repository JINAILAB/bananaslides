from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Sequence

from bananaslides.domain.models import DetectionBox, OCRResult, TextPlacement


class Typesetter(ABC):
    @abstractmethod
    def build_text_placements(
        self,
        detections: Sequence[DetectionBox],
        ocr_results: Sequence[OCRResult],
        *,
        source_image_path: Path | None = None,
        background_image_path: Path | None = None,
    ) -> list[TextPlacement]:
        """Convert detections and OCR output into PPT text box definitions."""
