from __future__ import annotations

import json
import platform
import sys
from pathlib import Path

from bananaslides.domain.models import DetectionBox, ElementCategory, OCRLine, OCRResult, SlideSize
from bananaslides.utils.correction import TextCorrection


def write_detection_artifact(
    output_path: Path,
    *,
    image_path: Path,
    slide_size: SlideSize,
    backend: str,
    detections: list[DetectionBox],
    pipeline: dict[str, str] | None = None,
) -> Path:
    payload = {
        "image_path": str(image_path),
        "slide_size": {
            "width_px": slide_size.width_px,
            "height_px": slide_size.height_px,
        },
        "backend": backend,
        "runtime": build_runtime_metadata(),
        "detections": [
            {
                "box_id": detection.box_id,
                "category": detection.category.value,
                "label": detection.label,
                "confidence": detection.confidence,
                "x": detection.x,
                "y": detection.y,
                "width": detection.width,
                "height": detection.height,
            }
            for detection in detections
        ],
    }
    if pipeline is not None:
        payload["pipeline"] = pipeline
    return _write_json(output_path, payload)


def write_ocr_artifact(
    output_path: Path,
    *,
    image_path: Path,
    backend: str,
    language: str,
    results: list[OCRResult],
    pipeline: dict[str, str] | None = None,
) -> Path:
    payload = {
        "image_path": str(image_path),
        "backend": backend,
        "language": language,
        "runtime": build_runtime_metadata(),
        "results": [
            {
                "box_id": result.box_id,
                "text": result.text,
                "confidence": result.confidence,
                "language": result.language,
                "lines": [
                    {
                        "text": line.text,
                        "confidence": line.confidence,
                        "bbox": line.bbox,
                    }
                    for line in result.lines
                ],
            }
            for result in results
        ],
    }
    if pipeline is not None:
        payload["pipeline"] = pipeline
    return _write_json(output_path, payload)


def build_runtime_metadata() -> dict[str, str]:
    return {
        "platform": sys.platform,
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "python_version": platform.python_version(),
    }


def build_pipeline_metadata(
    *,
    detector_backend: str,
    ocr_backend: str,
    inpainting_backend: str,
) -> dict[str, str]:
    return {
        "detector_backend": detector_backend,
        "ocr_backend": ocr_backend,
        "inpainting_backend": inpainting_backend,
    }


def read_detection_artifact(path: Path) -> tuple[SlideSize, list[DetectionBox]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    slide_size = SlideSize(
        width_px=int(payload["slide_size"]["width_px"]),
        height_px=int(payload["slide_size"]["height_px"]),
    )
    detections = [
        DetectionBox(
            box_id=item["box_id"],
            category=ElementCategory(item["category"]),
            x=float(item["x"]),
            y=float(item["y"]),
            width=float(item["width"]),
            height=float(item["height"]),
            confidence=float(item.get("confidence", 1.0)),
            label=item.get("label"),
        )
        for item in payload.get("detections", [])
    ]
    return slide_size, detections


def read_ocr_artifact(path: Path) -> list[OCRResult]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    results: list[OCRResult] = []
    for item in payload.get("results", []):
        lines = [
            OCRLine(
                text=line["text"],
                bbox=[[float(point[0]), float(point[1])] for point in line.get("bbox", [])],
                confidence=float(line["confidence"]) if line.get("confidence") is not None else None,
            )
            for line in item.get("lines", [])
        ]
        results.append(
            OCRResult(
                box_id=item["box_id"],
                text=item.get("text", ""),
                lines=lines,
                language=item.get("language"),
                confidence=float(item["confidence"]) if item.get("confidence") is not None else None,
            )
        )
    return results


def write_correction_artifact(
    output_path: Path,
    *,
    ocr_json_path: Path,
    expected_texts: list[str],
    corrections: list[TextCorrection],
) -> Path:
    payload = {
        "ocr_json_path": str(ocr_json_path),
        "expected_texts": expected_texts,
        "corrections": [
            {
                "box_id": item.box_id,
                "original_text": item.original_text,
                "corrected_text": item.corrected_text,
                "expected_text": item.expected_text,
                "match_score": item.match_score,
                "applied": item.applied,
            }
            for item in corrections
        ],
    }
    return _write_json(output_path, payload)


def _write_json(output_path: Path, payload: dict) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output_path
