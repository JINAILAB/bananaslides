from __future__ import annotations

from pathlib import Path
from typing import Callable, Sequence

import numpy as np
from PIL import Image

from bananaslides.domain.models import DetectionBox, ElementCategory, OCRLine, OCRResult
from bananaslides.modules.ocr.base import OcrEngine


class RapidOcrEngine(OcrEngine):
    """RapidOCR adapter that keeps all OCR assets local and explicit."""

    backend_name = "rapidocr_onnxruntime"

    def __init__(
        self,
        det_model_path: Path,
        cls_model_path: Path,
        rec_model_path: Path,
        rec_keys_path: Path | None = None,
        *,
        text_score: float = 0.5,
        min_height: int = 30,
        width_height_ratio: int = 8,
        ocr_runner: Callable[..., tuple[list[list[object]] | None, list[float] | None]] | None = None,
    ) -> None:
        self.det_model_path = det_model_path
        self.cls_model_path = cls_model_path
        self.rec_model_path = rec_model_path
        self.rec_keys_path = rec_keys_path
        self.text_score = text_score
        self.min_height = min_height
        self.width_height_ratio = width_height_ratio
        self._ocr_runner = ocr_runner or self._build_runner()

    def recognize(self, slide_image_path: Path, detections: Sequence[DetectionBox]) -> list[OCRResult]:
        image = Image.open(slide_image_path).convert("RGB")
        results: list[OCRResult] = []

        for detection in detections:
            if detection.category is not ElementCategory.TEXT:
                continue

            crop, offset_x, offset_y = self._crop_detection(image, detection)
            ocr_res, _ = self._ocr_runner(
                crop,
                use_det=True,
                use_cls=True,
                use_rec=True,
            )
            lines = self._parse_lines(ocr_res, offset_x=offset_x, offset_y=offset_y)
            merged_text = "\n".join(line.text for line in lines if line.text)
            confidences = [line.confidence for line in lines if line.confidence is not None]
            confidence = sum(confidences) / len(confidences) if confidences else None
            results.append(
                OCRResult(
                    box_id=detection.box_id,
                    text=merged_text,
                    lines=lines,
                    language="ko+en",
                    confidence=confidence,
                )
            )

        return results

    def _build_runner(self) -> Callable[..., tuple[list[list[object]] | None, list[float] | None]]:
        self._validate_assets()
        from rapidocr_onnxruntime import RapidOCR

        kwargs: dict[str, object] = {
            "det_model_path": str(self.det_model_path),
            "cls_model_path": str(self.cls_model_path),
            "rec_model_path": str(self.rec_model_path),
            "text_score": self.text_score,
            "min_height": self.min_height,
            "width_height_ratio": self.width_height_ratio,
        }
        cls_image_shape = self._read_static_chw_shape(self.cls_model_path)
        if cls_image_shape is not None:
            kwargs["cls_image_shape"] = cls_image_shape
        rec_image_shape = self._read_static_chw_shape(self.rec_model_path)
        if rec_image_shape is not None:
            kwargs["rec_img_shape"] = rec_image_shape
        if self.rec_keys_path is not None and self.rec_keys_path.exists():
            kwargs["rec_keys_path"] = str(self.rec_keys_path)
        return RapidOCR(**kwargs)

    def _validate_assets(self) -> None:
        required = [self.det_model_path, self.cls_model_path, self.rec_model_path]
        if self.rec_keys_path is not None and self.rec_keys_path.exists():
            required.append(self.rec_keys_path)
        missing = [str(path) for path in required if not path.exists()]
        if missing:
            raise FileNotFoundError(f"RapidOCR assets not found: {', '.join(missing)}")

    @staticmethod
    def _read_static_chw_shape(model_path: Path) -> list[int] | None:
        import onnxruntime as ort

        session = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
        input_shape = session.get_inputs()[0].shape
        if len(input_shape) != 4:
            return None
        chw = input_shape[1:]
        if not all(isinstance(dim, int) for dim in chw):
            return None
        return [int(dim) for dim in chw]

    @staticmethod
    def _crop_detection(image: Image.Image, detection: DetectionBox) -> tuple[np.ndarray, int, int]:
        left = max(0, round(detection.x))
        top = max(0, round(detection.y))
        right = min(image.width, round(detection.right))
        bottom = min(image.height, round(detection.bottom))
        crop = np.asarray(image.crop((left, top, right, bottom)).convert("RGB"), dtype=np.uint8)
        return crop[:, :, ::-1], left, top

    @staticmethod
    def _parse_lines(
        ocr_res: list[list[object]] | None,
        *,
        offset_x: int,
        offset_y: int,
    ) -> list[OCRLine]:
        if not ocr_res:
            return []

        lines: list[OCRLine] = []
        for item in ocr_res:
            if len(item) < 3:
                continue
            polygon = item[0]
            text = str(item[1]).strip()
            score = float(item[2]) if item[2] is not None else None
            if not text:
                continue
            bbox = [
                [float(point[0]) + offset_x, float(point[1]) + offset_y]
                for point in polygon
            ]
            lines.append(OCRLine(text=text, bbox=bbox, confidence=score))

        lines.sort(key=lambda line: (min(point[1] for point in line.bbox), min(point[0] for point in line.bbox)))
        return lines
