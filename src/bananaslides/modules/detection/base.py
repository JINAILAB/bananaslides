from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from bananaslides.domain.models import DetectionBox, SlideSize


class TextDetector(ABC):
    @abstractmethod
    def detect(self, slide_image_path: Path, slide_size: SlideSize) -> list[DetectionBox]:
        """Return text detections in slide pixel coordinates."""

