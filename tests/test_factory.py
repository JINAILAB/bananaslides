from __future__ import annotations

import pytest

from bananaslides.config import ModelAssetPaths, PipelineConfig
from bananaslides.pipeline import factory
from bananaslides.utils.ocr_models import ResolvedOcrModelAssets


class _FakeDetector:
    backend_name = "fake_detector"


class _FakeRapidOcrEngine:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs


class _FakeCv2Inpainter:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs


def test_build_ocr_engine_uses_portable_backend_by_default(monkeypatch) -> None:
    monkeypatch.setattr(factory, "RapidOcrEngine", _FakeRapidOcrEngine)

    engine = factory.build_ocr_engine(PipelineConfig())

    assert isinstance(engine, _FakeRapidOcrEngine)


def test_build_text_detector_uses_ocr_backend_by_default(monkeypatch) -> None:
    monkeypatch.setattr(factory, "FullSlideTextDetector", lambda: _FakeDetector())

    detector = factory.build_text_detector(PipelineConfig())

    assert isinstance(detector, _FakeDetector)


def test_build_text_detector_rejects_layout_backend() -> None:
    config = PipelineConfig()
    config.detector_backend = "layout"

    with pytest.raises(ValueError, match="Unsupported detector backend"):
        factory.build_text_detector(config)


def test_build_ocr_engine_auto_uses_portable_backend(monkeypatch) -> None:
    monkeypatch.setattr(factory, "RapidOcrEngine", _FakeRapidOcrEngine)
    config = PipelineConfig()
    config.ocr_backend = "auto"

    engine = factory.build_ocr_engine(config)

    assert isinstance(engine, _FakeRapidOcrEngine)


@pytest.mark.parametrize("backend", ["native", "vision"])
def test_build_ocr_engine_rejects_removed_native_backends(monkeypatch, backend: str) -> None:
    monkeypatch.setattr(factory, "RapidOcrEngine", _FakeRapidOcrEngine)
    config = PipelineConfig()
    config.ocr_backend = backend

    with pytest.raises(ValueError, match="Unsupported OCR backend"):
        factory.build_ocr_engine(config)


def test_build_ocr_engine_rejects_unknown_backend(monkeypatch) -> None:
    monkeypatch.setattr(factory, "RapidOcrEngine", _FakeRapidOcrEngine)
    config = PipelineConfig()
    config.ocr_backend = "bogus"

    with pytest.raises(ValueError, match="Unsupported OCR backend"):
        factory.build_ocr_engine(config)


def test_build_ocr_engine_uses_resolved_model_assets(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(factory, "RapidOcrEngine", _FakeRapidOcrEngine)
    resolved_paths = ModelAssetPaths(
        rapidocr_det_model=tmp_path / "det.onnx",
        rapidocr_cls_model=tmp_path / "cls.onnx",
        rapidocr_rec_model=tmp_path / "rec.onnx",
        rapidocr_keys=tmp_path / "keys.txt",
    )
    monkeypatch.setattr(
        factory,
        "resolve_ocr_model_assets",
        lambda **kwargs: ResolvedOcrModelAssets(
            model_assets=resolved_paths,
            source="preset",
            preset_id="latin",
            model_home=tmp_path,
        ),
    )
    config = PipelineConfig()
    config.ocr_model_home = tmp_path
    config.ocr_preset = "latin"

    engine = factory.build_ocr_engine(config)

    assert isinstance(engine, _FakeRapidOcrEngine)
    assert engine.kwargs["det_model_path"] == resolved_paths.rapidocr_det_model
    assert engine.kwargs["rec_model_path"] == resolved_paths.rapidocr_rec_model


def test_build_inpainter_uses_telea_backend_by_default(monkeypatch) -> None:
    monkeypatch.setattr(factory, "Cv2Inpainter", _FakeCv2Inpainter)

    inpainter = factory.build_inpainter(PipelineConfig())

    assert isinstance(inpainter, _FakeCv2Inpainter)


def test_build_inpainter_rejects_lama_backend() -> None:
    config = PipelineConfig()
    config.inpainting_backend = "lama"

    with pytest.raises(ValueError, match="Unsupported inpainting backend"):
        factory.build_inpainter(config)


def test_build_inpainter_rejects_unknown_backend() -> None:
    config = PipelineConfig()
    config.inpainting_backend = "bogus"

    with pytest.raises(ValueError, match="Unsupported inpainting backend"):
        factory.build_inpainter(config)
