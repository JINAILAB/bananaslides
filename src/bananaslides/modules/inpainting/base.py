from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class Inpainter(ABC):
    @abstractmethod
    def inpaint(self, slide_image_path: Path, mask_path: Path, output_path: Path) -> Path:
        """Remove masked regions from the slide image and write a background image."""

