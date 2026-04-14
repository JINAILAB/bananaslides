from __future__ import annotations

from bananaslides.config import PipelineConfig
from bananaslides.modules.detection.full_slide_text_detector import FullSlideTextDetector
from bananaslides.modules.inpainting.base import Inpainter
from bananaslides.modules.inpainting.cv2_inpainter import Cv2Inpainter
from bananaslides.modules.ocr.base import OcrEngine
from bananaslides.modules.ocr.rapidocr_engine import RapidOcrEngine
from bananaslides.modules.ppt.render import PowerPointRenderer
from bananaslides.modules.typesetting.fixed_font_typesetter import FixedFontTypesetter
from bananaslides.pipeline.orchestrator import PipelineComponents
from bananaslides.utils.ocr_models import resolve_ocr_model_assets

_OCR_DETECTOR_ALIASES = {"ocr", "full-slide", "full_slide"}
_PORTABLE_ALIASES = {"portable", "rapidocr"}
_AUTO_ALIASES = {"auto"}
_CV2_ALIASES = {"cv2", "telea", "opencv", "opencv_telea"}


def build_default_components(config: PipelineConfig) -> PipelineComponents:
    return PipelineComponents(
        detector=build_text_detector(config),
        ocr_engine=build_ocr_engine(config),
        inpainter=build_inpainter(config),
        typesetter=FixedFontTypesetter(font_policy=config.fonts, dpi=config.default_dpi),
        renderer=PowerPointRenderer(),
    )


def build_text_detector(config: PipelineConfig):
    requested = config.detector_backend.lower().strip()
    if requested in _OCR_DETECTOR_ALIASES:
        return FullSlideTextDetector()
    raise ValueError(f"Unsupported detector backend: {config.detector_backend}")


def build_ocr_engine(config: PipelineConfig) -> OcrEngine:
    requested = config.ocr_backend.lower().strip()
    if requested not in _PORTABLE_ALIASES | _AUTO_ALIASES:
        raise ValueError(f"Unsupported OCR backend: {config.ocr_backend}")

    return _build_portable_ocr_engine(config)


def _build_portable_ocr_engine(config: PipelineConfig) -> RapidOcrEngine:
    resolved_models = resolve_ocr_model_assets(
        model_home=config.ocr_model_home,
        preset_id=config.ocr_preset,
        fallback_assets=config.model_assets,
    )
    return RapidOcrEngine(
        det_model_path=resolved_models.model_assets.rapidocr_det_model,
        cls_model_path=resolved_models.model_assets.rapidocr_cls_model,
        rec_model_path=resolved_models.model_assets.rapidocr_rec_model,
        rec_keys_path=resolved_models.model_assets.rapidocr_keys,
    )


def build_inpainter(config: PipelineConfig) -> Inpainter:
    requested = config.inpainting_backend.lower().strip()
    if requested in _CV2_ALIASES:
        return Cv2Inpainter(radius=config.cv2_inpaint_radius)
    raise ValueError(f"Unsupported inpainting backend: {config.inpainting_backend}")
