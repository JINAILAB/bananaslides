from __future__ import annotations

from PIL import Image
import pytest
import rapidocr_onnxruntime

from bananaslides.domain.models import DetectionBox, ElementCategory
from bananaslides.modules.ocr.rapidocr_engine import RapidOcrEngine


def test_rapidocr_engine_maps_line_boxes_back_to_slide_coordinates(tmp_path) -> None:
    slide_path = tmp_path / "slide.png"
    Image.new("RGB", (100, 80), "white").save(slide_path)

    def fake_runner(image, **kwargs):
        assert image.shape[:2] == (30, 40)
        assert kwargs["use_det"] and kwargs["use_cls"] and kwargs["use_rec"]
        return (
            [
                [[[1, 1], [11, 1], [11, 6], [1, 6]], "안녕", 0.9],
                [[[2, 10], [18, 10], [18, 16], [2, 16]], "world", 0.8],
            ],
            [0.01, 0.01, 0.01],
        )

    engine = RapidOcrEngine(
        det_model_path=tmp_path / "det.onnx",
        cls_model_path=tmp_path / "cls.onnx",
        rec_model_path=tmp_path / "rec.onnx",
        rec_keys_path=tmp_path / "keys.txt",
        ocr_runner=fake_runner,
    )
    detections = [
        DetectionBox(
            box_id="t0001",
            category=ElementCategory.TEXT,
            x=10,
            y=20,
            width=40,
            height=30,
        )
    ]

    results = engine.recognize(slide_path, detections)

    assert len(results) == 1
    assert results[0].text == "안녕\nworld"
    assert results[0].confidence == pytest.approx(0.85)
    assert results[0].lines[0].bbox[0] == [11.0, 21.0]
    assert results[0].lines[1].bbox[2] == [28.0, 36.0]


def test_rapidocr_engine_passes_model_specific_shapes_to_runner(tmp_path, monkeypatch) -> None:
    det_model = tmp_path / "det.onnx"
    cls_model = tmp_path / "cls.onnx"
    rec_model = tmp_path / "rec.onnx"
    keys = tmp_path / "keys.txt"
    for path in (det_model, cls_model, rec_model, keys):
        path.write_bytes(b"stub")

    captured: dict[str, object] = {}

    class FakeRapidOCR:
        def __init__(self, **kwargs) -> None:
            captured.update(kwargs)

        def __call__(self, *args, **kwargs):
            return None, None

    def fake_shape(path):
        if path == cls_model:
            return [3, 80, 160]
        return None

    monkeypatch.setattr(rapidocr_onnxruntime, "RapidOCR", FakeRapidOCR)
    monkeypatch.setattr(RapidOcrEngine, "_read_static_chw_shape", staticmethod(fake_shape))

    RapidOcrEngine(
        det_model_path=det_model,
        cls_model_path=cls_model,
        rec_model_path=rec_model,
        rec_keys_path=keys,
    )

    assert captured["cls_image_shape"] == [3, 80, 160]
    assert "rec_img_shape" not in captured
