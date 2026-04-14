from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class ElementCategory(str, Enum):
    TEXT = "text"
    FIGURE = "figure"
    TABLE = "table"
    CHART = "chart"
    ICON = "icon"
    SHAPE = "shape"
    DECORATION = "decoration"


@dataclass(slots=True)
class SlideSize:
    width_px: int
    height_px: int

    def as_tuple(self) -> tuple[int, int]:
        return self.width_px, self.height_px


@dataclass(slots=True)
class RGBColor:
    r: int
    g: int
    b: int

    def as_tuple(self) -> tuple[int, int, int]:
        return self.r, self.g, self.b


@dataclass(slots=True)
class DetectionBox:
    box_id: str
    category: ElementCategory
    x: float
    y: float
    width: float
    height: float
    confidence: float = 1.0
    label: str | None = None

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def bottom(self) -> float:
        return self.y + self.height


@dataclass(slots=True)
class OCRLine:
    text: str
    bbox: list[list[float]] = field(default_factory=list)
    confidence: float | None = None


@dataclass(slots=True)
class OCRResult:
    box_id: str
    text: str
    lines: list[OCRLine] = field(default_factory=list)
    language: str | None = None
    confidence: float | None = None


@dataclass(slots=True)
class TextPlacement:
    box_id: str
    text: str
    x: float
    y: float
    width: float
    height: float
    font_name: str
    font_size_pt: float
    color: RGBColor = field(default_factory=lambda: RGBColor(0, 0, 0))
    bold: bool = False
    italic: bool = False
    align: str = "left"
    language: str | None = None
    word_wrap: bool = False
    auto_fit: bool = False
    font_file: str | None = None


@dataclass(slots=True)
class ImagePlacement:
    box_id: str
    image_path: Path
    x: float
    y: float
    width: float
    height: float


@dataclass(slots=True)
class SlideRenderSpec:
    slide_size: SlideSize
    background_image_path: Path | None = None
    image_placements: list[ImagePlacement] = field(default_factory=list)
    text_placements: list[TextPlacement] = field(default_factory=list)


@dataclass(slots=True)
class PresentationRenderSpec:
    slides: list[SlideRenderSpec]
    dpi: int = 96
