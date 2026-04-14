from __future__ import annotations

from pathlib import Path
from typing import Iterable

from PIL import Image, ImageDraw

from bananaslides.domain.models import DetectionBox, ElementCategory, OCRResult, SlideSize


def build_text_mask(
    slide_size: SlideSize,
    detections: Iterable[DetectionBox],
    padding_px: int = 2,
) -> Image.Image:
    """Build a binary mask from text detection boxes."""

    mask = Image.new("L", slide_size.as_tuple(), 0)
    draw = ImageDraw.Draw(mask)

    for detection in detections:
        if detection.category is not ElementCategory.TEXT:
            continue

        x0 = max(0, round(detection.x) - padding_px)
        y0 = max(0, round(detection.y) - padding_px)
        x1 = min(slide_size.width_px, round(detection.right) + padding_px)
        y1 = min(slide_size.height_px, round(detection.bottom) + padding_px)
        draw.rectangle((x0, y0, x1, y1), fill=255)

    return mask


def save_text_mask(
    slide_size: SlideSize,
    detections: Iterable[DetectionBox],
    output_path: Path,
    padding_px: int = 2,
) -> Path:
    mask = build_text_mask(slide_size=slide_size, detections=detections, padding_px=padding_px)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    mask.save(output_path)
    return output_path


def build_text_mask_from_ocr_results(
    slide_size: SlideSize,
    ocr_results: Iterable[OCRResult],
    padding_px: int = 2,
) -> Image.Image:
    """Build a binary mask from OCR line polygons."""

    mask = Image.new("L", slide_size.as_tuple(), 0)
    draw = ImageDraw.Draw(mask)

    for result in ocr_results:
        for line in result.lines:
            if not line.bbox:
                continue
            xs = [point[0] for point in line.bbox]
            ys = [point[1] for point in line.bbox]
            x0 = max(0, round(min(xs)) - padding_px)
            y0 = max(0, round(min(ys)) - padding_px)
            x1 = min(slide_size.width_px, round(max(xs)) + padding_px)
            y1 = min(slide_size.height_px, round(max(ys)) + padding_px)
            draw.rectangle((x0, y0, x1, y1), fill=255)

    return mask


def save_text_mask_from_ocr_results(
    slide_size: SlideSize,
    ocr_results: Iterable[OCRResult],
    output_path: Path,
    padding_px: int = 2,
) -> Path:
    mask = build_text_mask_from_ocr_results(
        slide_size=slide_size,
        ocr_results=ocr_results,
        padding_px=padding_px,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    mask.save(output_path)
    return output_path
