from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from bananaslides.domain.models import RGBColor


@dataclass(slots=True)
class FontPolicy:
    korean_font: str = "Pretendard"
    latin_font: str = "Pretendard"
    default_text_color: RGBColor = field(default_factory=lambda: RGBColor(0, 0, 0))
    min_font_size_pt: float = 10.0
    max_font_size_pt: float = 44.0


@dataclass(slots=True)
class ModelAssetPaths:
    rapidocr_det_model: Path = Path("assets/models/rapidocr/ch_PP-OCRv5_det_mobile.onnx")
    rapidocr_cls_model: Path = Path(
        "assets/models/rapidocr/ch_PP-LCNet_x0_25_textline_ori_cls_mobile.onnx"
    )
    rapidocr_rec_model: Path = Path("assets/models/rapidocr/korean_PP-OCRv5_rec_mobile.onnx")
    rapidocr_keys: Path = Path("assets/models/rapidocr/ppocrv5_korean_dict.txt")

    def all_exist(self) -> bool:
        return all(
            path.exists()
            for path in (
                self.rapidocr_det_model,
                self.rapidocr_cls_model,
                self.rapidocr_rec_model,
                self.rapidocr_keys,
            )
        )


def default_ocr_model_home() -> Path:
    from bananaslides.utils.ocr_models import default_ocr_model_home as resolve_default_ocr_model_home

    return resolve_default_ocr_model_home()


@dataclass(slots=True)
class PipelineConfig:
    fonts: FontPolicy = field(default_factory=FontPolicy)
    model_assets: ModelAssetPaths = field(default_factory=ModelAssetPaths)
    ocr_model_home: Path = field(default_factory=default_ocr_model_home)
    ocr_preset: str | None = None
    default_dpi: int = 96
    default_output_dir: Path = Path("artifacts")
    detector_backend: str = "ocr"
    ocr_backend: str = "portable"
    inpainting_backend: str = "telea"
    text_confidence_threshold: float = 0.25
    ocr_language: str = "ko+en"
    cv2_inpaint_radius: float = 3.0
