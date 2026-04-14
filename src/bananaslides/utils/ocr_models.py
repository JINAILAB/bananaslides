from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.request import urlopen

from bananaslides.config import ModelAssetPaths

DEFAULT_OCR_PRESET_ID = "ko-en"
_PADDLE_DICT_BASE_URL = "https://raw.githubusercontent.com/PaddlePaddle/PaddleOCR/main/ppocr/utils/dict"
_RAPIDOCR_CATALOG_URL = "https://raw.githubusercontent.com/RapidAI/RapidOCR/main/python/rapidocr/default_models.yaml"
_APACHE_LICENSE = "Apache-2.0"


class OcrModelError(RuntimeError):
    """Base error for OCR model bootstrap failures."""


class MissingOcrModelsError(FileNotFoundError, OcrModelError):
    """Raised when no usable OCR model assets are configured."""


class UnknownOcrPresetError(OcrModelError):
    """Raised when a preset id is not part of the built-in catalog."""


class OcrModelDownloadError(OcrModelError):
    """Raised when a model asset download fails or does not match the expected hash."""


@dataclass(frozen=True, slots=True)
class ModelFileSpec:
    filename: str
    urls: tuple[str, ...]
    sha256: str
    source_url: str
    license_name: str
    bundled_paths: tuple[Path, ...] = ()


@dataclass(frozen=True, slots=True)
class OcrPresetSpec:
    preset_id: str
    display_name: str
    description: str
    detector: ModelFileSpec
    classifier: ModelFileSpec
    recognizer: ModelFileSpec
    dictionary: ModelFileSpec

    def model_files(self) -> tuple[ModelFileSpec, ...]:
        return (
            self.detector,
            self.classifier,
            self.recognizer,
            self.dictionary,
        )


@dataclass(frozen=True, slots=True)
class ResolvedOcrModelAssets:
    model_assets: ModelAssetPaths
    source: str
    preset_id: str | None
    model_home: Path


def default_ocr_model_home() -> Path:
    env_home = os.environ.get("BANANASLIDES_MODEL_HOME")
    if env_home:
        return Path(env_home).expanduser()

    home = Path.home()
    if sys.platform.startswith("win"):
        base = Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local"))
    elif sys.platform.startswith("darwin"):
        base = home / "Library" / "Caches"
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME", home / ".cache"))

    model_home = base / "bananaslides" / "ocr_models"
    legacy_model_home = base / "banana2pptx" / "ocr_models"
    if not model_home.exists() and legacy_model_home.exists():
        model_home.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(legacy_model_home), str(model_home))
    return model_home


def list_ocr_presets() -> tuple[OcrPresetSpec, ...]:
    return tuple(OCR_PRESET_CATALOG.values())


def get_ocr_preset_spec(preset_id: str) -> OcrPresetSpec:
    try:
        return OCR_PRESET_CATALOG[preset_id]
    except KeyError as exc:
        raise UnknownOcrPresetError(f"Unknown OCR preset: {preset_id}") from exc


def get_active_ocr_preset_id(model_home: Path | None = None) -> str | None:
    path = _active_preset_path(_coerce_model_home(model_home))
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    preset_id = payload.get("preset_id")
    return str(preset_id) if preset_id else None


def list_installed_ocr_presets(model_home: Path | None = None) -> tuple[str, ...]:
    home = _coerce_model_home(model_home)
    presets_dir = _presets_root(home)
    if not presets_dir.exists():
        return ()
    installed: list[str] = []
    for child in sorted(presets_dir.iterdir()):
        if child.is_dir() and (child / "manifest.json").exists():
            installed.append(child.name)
    return tuple(installed)


def is_ocr_preset_installed(preset_id: str, model_home: Path | None = None) -> bool:
    try:
        preset = get_ocr_preset_spec(preset_id)
    except UnknownOcrPresetError:
        return False
    preset_dir = _preset_directory(_coerce_model_home(model_home), preset_id)
    if not preset_dir.exists():
        return False
    return _all_model_files_exist(_model_asset_paths_for_preset(preset_dir, preset))


def install_ocr_preset(
    preset_id: str,
    model_home: Path | None = None,
    *,
    activate: bool = True,
    force: bool = False,
    downloader: Callable[[str, Path], None] | None = None,
) -> ResolvedOcrModelAssets:
    preset = get_ocr_preset_spec(preset_id)
    home = _coerce_model_home(model_home)
    home.mkdir(parents=True, exist_ok=True)

    preset_dir = _preset_directory(home, preset_id)
    if not force and is_ocr_preset_installed(preset_id, home):
        if activate:
            set_active_ocr_preset(preset_id, home)
        return ResolvedOcrModelAssets(
            model_assets=_model_asset_paths_for_preset(preset_dir, preset),
            source="preset",
            preset_id=preset_id,
            model_home=home,
        )

    temp_dir = Path(tempfile.mkdtemp(prefix=f"{preset_id}-", dir=home))
    resolved_sources: dict[str, str] = {}
    try:
        for file_spec in preset.model_files():
            resolved_sources[file_spec.filename] = _materialize_model_file(
                file_spec,
                temp_dir / file_spec.filename,
                downloader=downloader,
            )

        manifest = {
            "preset_id": preset.preset_id,
            "display_name": preset.display_name,
            "description": preset.description,
            "license": _APACHE_LICENSE,
            "catalog_source": _RAPIDOCR_CATALOG_URL,
            "files": {
                file_spec.filename: {
                    "sha256": file_spec.sha256,
                    "source_url": file_spec.source_url,
                    "resolved_from": resolved_sources[file_spec.filename],
                }
                for file_spec in preset.model_files()
            },
        }
        (temp_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

        if preset_dir.exists():
            shutil.rmtree(preset_dir)
        preset_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(temp_dir), str(preset_dir))
        if activate:
            set_active_ocr_preset(preset_id, home)
        return ResolvedOcrModelAssets(
            model_assets=_model_asset_paths_for_preset(preset_dir, preset),
            source="preset",
            preset_id=preset_id,
            model_home=home,
        )
    finally:
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)


def set_active_ocr_preset(preset_id: str, model_home: Path | None = None) -> Path:
    get_ocr_preset_spec(preset_id)
    home = _coerce_model_home(model_home)
    if not is_ocr_preset_installed(preset_id, home):
        raise MissingOcrModelsError(
            f"OCR preset '{preset_id}' is not installed. Run `bananaslides init-models --preset {preset_id}` first."
        )
    path = _active_preset_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"preset_id": preset_id}, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def resolve_ocr_model_assets(
    *,
    model_home: Path | None = None,
    preset_id: str | None = None,
    fallback_assets: ModelAssetPaths | None = None,
) -> ResolvedOcrModelAssets:
    home = _coerce_model_home(model_home)
    requested_preset = preset_id or get_active_ocr_preset_id(home)
    if requested_preset is not None:
        preset = get_ocr_preset_spec(requested_preset)
        preset_paths = _model_asset_paths_for_preset(_preset_directory(home, requested_preset), preset)
        if not _all_model_files_exist(preset_paths):
            raise MissingOcrModelsError(
                f"OCR preset '{requested_preset}' is not installed. Run `bananaslides init-models --preset {requested_preset}` first."
            )
        return ResolvedOcrModelAssets(
            model_assets=preset_paths,
            source="preset",
            preset_id=requested_preset,
            model_home=home,
        )

    if fallback_assets is not None and fallback_assets.all_exist():
        return ResolvedOcrModelAssets(
            model_assets=fallback_assets,
            source="bundled",
            preset_id=None,
            model_home=home,
        )

    raise MissingOcrModelsError(
        f"OCR models are not configured. Run `bananaslides init-models --preset {DEFAULT_OCR_PRESET_ID}` first."
    )


def _coerce_model_home(model_home: Path | None) -> Path:
    return Path(model_home).expanduser() if model_home is not None else default_ocr_model_home()


def _active_preset_path(model_home: Path) -> Path:
    return model_home / "active_preset.json"


def _presets_root(model_home: Path) -> Path:
    return model_home / "presets"


def _preset_directory(model_home: Path, preset_id: str) -> Path:
    return _presets_root(model_home) / preset_id


def _model_asset_paths_for_preset(preset_dir: Path, preset: OcrPresetSpec) -> ModelAssetPaths:
    return ModelAssetPaths(
        rapidocr_det_model=preset_dir / preset.detector.filename,
        rapidocr_cls_model=preset_dir / preset.classifier.filename,
        rapidocr_rec_model=preset_dir / preset.recognizer.filename,
        rapidocr_keys=preset_dir / preset.dictionary.filename,
    )


def _all_model_files_exist(paths: ModelAssetPaths) -> bool:
    return paths.all_exist()


def _materialize_model_file(
    file_spec: ModelFileSpec,
    output_path: Path,
    *,
    downloader: Callable[[str, Path], None] | None = None,
) -> str:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    for bundled_path in file_spec.bundled_paths:
        if bundled_path.exists() and _sha256_file(bundled_path) == file_spec.sha256:
            shutil.copy2(bundled_path, output_path)
            return str(bundled_path)

    last_error: Exception | None = None
    for url in file_spec.urls:
        temp_path = output_path.with_suffix(f"{output_path.suffix}.part")
        try:
            if downloader is not None:
                downloader(url, temp_path)
            else:
                _download_to_path(url, temp_path)
            actual_sha = _sha256_file(temp_path)
            if actual_sha != file_spec.sha256:
                raise OcrModelDownloadError(
                    f"Checksum mismatch for {file_spec.filename}: expected {file_spec.sha256}, got {actual_sha}"
                )
            temp_path.replace(output_path)
            return url
        except Exception as exc:  # pragma: no cover - covered by tests via final raised error
            last_error = exc
            if temp_path.exists():
                temp_path.unlink()

    raise OcrModelDownloadError(f"Failed to fetch {file_spec.filename}: {last_error}")


def _download_to_path(url: str, output_path: Path) -> None:
    with urlopen(url, timeout=60) as response, output_path.open("wb") as handle:
        shutil.copyfileobj(response, handle)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _spec(
    filename: str,
    url: str,
    sha256: str,
    *,
    source_url: str,
    bundled_paths: tuple[Path, ...] = (),
) -> ModelFileSpec:
    return ModelFileSpec(
        filename=filename,
        urls=(url,),
        sha256=sha256,
        source_url=source_url,
        license_name=_APACHE_LICENSE,
        bundled_paths=bundled_paths,
    )


_DET_MOBILE = _spec(
    "ch_PP-OCRv5_det_mobile.onnx",
    "https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.8.0/onnx/PP-OCRv5/det/ch_PP-OCRv5_det_mobile.onnx",
    "4d97c44a20d30a81aad087d6a396b08f786c4635742afc391f6621f5c6ae78ae",
    source_url=_RAPIDOCR_CATALOG_URL,
    bundled_paths=(Path("assets/models/rapidocr/ch_PP-OCRv5_det_mobile.onnx"),),
)
_CLS_MOBILE = _spec(
    "ch_PP-LCNet_x0_25_textline_ori_cls_mobile.onnx",
    "https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.8.0/onnx/PP-OCRv5/cls/ch_PP-LCNet_x0_25_textline_ori_cls_mobile.onnx",
    "54379ae5174d026780215fc748a7f31910dee36818e63d49e17dc598ecc82df7",
    source_url=_RAPIDOCR_CATALOG_URL,
    bundled_paths=(Path("assets/models/rapidocr/ch_PP-LCNet_x0_25_textline_ori_cls_mobile.onnx"),),
)


def _rec_spec(name: str, sha256: str, *, bundled_paths: tuple[Path, ...] = ()) -> ModelFileSpec:
    return _spec(
        f"{name}.onnx",
        f"https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.8.0/onnx/PP-OCRv5/rec/{name}.onnx",
        sha256,
        source_url=_RAPIDOCR_CATALOG_URL,
        bundled_paths=bundled_paths,
    )


def _dict_spec(name: str, sha256: str, *, bundled_paths: tuple[Path, ...] = ()) -> ModelFileSpec:
    return _spec(
        name,
        f"{_PADDLE_DICT_BASE_URL}/{name}",
        sha256,
        source_url=f"{_PADDLE_DICT_BASE_URL}/{name}",
        bundled_paths=bundled_paths,
    )


OCR_PRESET_CATALOG: dict[str, OcrPresetSpec] = {
    "ko-en": OcrPresetSpec(
        preset_id="ko-en",
        display_name="Korean + English",
        description="Default PP-OCRv5 mobile preset for Korean-centric slides with Latin text coverage.",
        detector=_DET_MOBILE,
        classifier=_CLS_MOBILE,
        recognizer=_rec_spec(
            "korean_PP-OCRv5_rec_mobile",
            "cd6e2ea50f6943ca7271eb8c56a877a5a90720b7047fe9c41a2e541a25773c9b",
            bundled_paths=(Path("assets/models/rapidocr/korean_PP-OCRv5_rec_mobile.onnx"),),
        ),
        dictionary=_dict_spec(
            "ppocrv5_korean_dict.txt",
            "a88071c68c01707489baa79ebe0405b7beb5cca229f4fc94cc3ef992328802d7",
            bundled_paths=(Path("assets/models/rapidocr/ppocrv5_korean_dict.txt"),),
        ),
    ),
    "chinese": OcrPresetSpec(
        preset_id="chinese",
        display_name="Chinese Simplified",
        description="PP-OCRv5 mobile preset for simplified Chinese text.",
        detector=_DET_MOBILE,
        classifier=_CLS_MOBILE,
        recognizer=_rec_spec("ch_PP-OCRv5_rec_mobile", "5825fc7ebf84ae7a412be049820b4d86d77620f204a041697b0494669b1742c5"),
        dictionary=_dict_spec("ppocrv5_dict.txt", "d1979e9f794c464c0d2e0b70a7fe14dd978e9dc644c0e71f14158cdf8342af1b"),
    ),
    "english": OcrPresetSpec(
        preset_id="english",
        display_name="English",
        description="PP-OCRv5 mobile preset for English-heavy OCR.",
        detector=_DET_MOBILE,
        classifier=_CLS_MOBILE,
        recognizer=_rec_spec("en_PP-OCRv5_rec_mobile", "c3461add59bb4323ecba96a492ab75e06dda42467c9e3d0c18db5d1d21924be8"),
        dictionary=_dict_spec("ppocrv5_en_dict.txt", "e025a66d31f327ba0c232e03f407ae8d105e1e709e7ccb3f408aa778c24e70d6"),
    ),
    "latin": OcrPresetSpec(
        preset_id="latin",
        display_name="Latin",
        description="PP-OCRv5 mobile preset for Latin-script OCR.",
        detector=_DET_MOBILE,
        classifier=_CLS_MOBILE,
        recognizer=_rec_spec("latin_PP-OCRv5_rec_mobile", "b20bd37c168a570f583afbc8cd7925603890efbcdc000a59e22c269d160b5f5a"),
        dictionary=_dict_spec("ppocrv5_latin_dict.txt", "ccbcc45730b3fbbd9050c5bc74db6a99067141ef1035e3d14889a84a6b9b1aff"),
    ),
    "eslav": OcrPresetSpec(
        preset_id="eslav",
        display_name="Eslav",
        description="PP-OCRv5 mobile preset for East/Slavic Latin-script OCR.",
        detector=_DET_MOBILE,
        classifier=_CLS_MOBILE,
        recognizer=_rec_spec("eslav_PP-OCRv5_rec_mobile", "08705d6721849b1347d26187f15a5e362c431963a2a62bfff4feac578c489aab"),
        dictionary=_dict_spec("ppocrv5_eslav_dict.txt", "3e95f1581557162870cacdba5af91a4c6be2890710d395b0c3c7578e7ee5e6eb"),
    ),
    "thai": OcrPresetSpec(
        preset_id="thai",
        display_name="Thai",
        description="PP-OCRv5 mobile preset for Thai OCR.",
        detector=_DET_MOBILE,
        classifier=_CLS_MOBILE,
        recognizer=_rec_spec("th_PP-OCRv5_rec_mobile", "de541dd83161c241ff426f7ecfd602a0ba77d686cf3ab9a6c255ea82fd08006e"),
        dictionary=_dict_spec("ppocrv5_th_dict.txt", "57f5406f94bb6688fb7077f7be65f08bbd71cecf48c01ea26c522cb5c4836b7a"),
    ),
    "greek": OcrPresetSpec(
        preset_id="greek",
        display_name="Greek",
        description="PP-OCRv5 mobile preset for Greek OCR.",
        detector=_DET_MOBILE,
        classifier=_CLS_MOBILE,
        recognizer=_rec_spec("el_PP-OCRv5_rec_mobile", "b4368bccd557123c702b7549fee6cd1e94b581337d1c9b65310f109131542b7f"),
        dictionary=_dict_spec("ppocrv5_el_dict.txt", "31defc62c0c3ad3674a82da6192226a2ba98ef4ff014a7045cb88d59f9c3de31"),
    ),
    "arabic": OcrPresetSpec(
        preset_id="arabic",
        display_name="Arabic",
        description="PP-OCRv5 mobile preset for Arabic OCR.",
        detector=_DET_MOBILE,
        classifier=_CLS_MOBILE,
        recognizer=_rec_spec("arabic_PP-OCRv5_rec_mobile", "c1192e632d0baa9146ae5b756a0e635e3dc63c1733737ebfd1629e87144e9295"),
        dictionary=_dict_spec("ppocrv5_arabic_dict.txt", "7f92f7dbb9b75a4787a83bfb4f6d14a8ab515525130c9d40a9036f61cf6999e9"),
    ),
    "cyrillic": OcrPresetSpec(
        preset_id="cyrillic",
        display_name="Cyrillic",
        description="PP-OCRv5 mobile preset for Cyrillic OCR.",
        detector=_DET_MOBILE,
        classifier=_CLS_MOBILE,
        recognizer=_rec_spec("cyrillic_PP-OCRv5_rec_mobile", "90f761b4bfcce0c8c561c0cb5c887b0971d3ec01c32164bdf7374a35b0982711"),
        dictionary=_dict_spec("ppocrv5_cyrillic_dict.txt", "db40aa52ceb112055be80c694afdf655d5d2c4f7873704524cc16a447ca913ba"),
    ),
    "devanagari": OcrPresetSpec(
        preset_id="devanagari",
        display_name="Devanagari",
        description="PP-OCRv5 mobile preset for Devanagari OCR.",
        detector=_DET_MOBILE,
        classifier=_CLS_MOBILE,
        recognizer=_rec_spec("devanagari_PP-OCRv5_rec_mobile", "d6f0a906580e3fa6b324a318718f1f31f268b6ea8ef985f91c2012a37f52c91e"),
        dictionary=_dict_spec("ppocrv5_devanagari_dict.txt", "09c7440bfc5477e5c41052304b6b185aff8c4a5e8b2b4c23c1c706f6fe1ee9fc"),
    ),
    "tamil": OcrPresetSpec(
        preset_id="tamil",
        display_name="Tamil",
        description="PP-OCRv5 mobile preset for Tamil OCR.",
        detector=_DET_MOBILE,
        classifier=_CLS_MOBILE,
        recognizer=_rec_spec("ta_PP-OCRv5_rec_mobile", "a42448808b7dea87597336f12438935f40353f1949e8360acd9e06b4da21bfe1"),
        dictionary=_dict_spec("ppocrv5_ta_dict.txt", "85b541352ae18dc6ba6d47152d8bf8adff6b0266e605d2eef2990c1bf466117b"),
    ),
    "telugu": OcrPresetSpec(
        preset_id="telugu",
        display_name="Telugu",
        description="PP-OCRv5 mobile preset for Telugu OCR.",
        detector=_DET_MOBILE,
        classifier=_CLS_MOBILE,
        recognizer=_rec_spec("te_PP-OCRv5_rec_mobile", "a3690451b50028a09a3316a1274f7c05728151ea3f8fd392696397a7fefcbd92"),
        dictionary=_dict_spec("ppocrv5_te_dict.txt", "42f83f5d3fdb50778e4fa5b66c58d99a59ab7792151c5e74f34b8ffd7b61c9d6"),
    ),
}
