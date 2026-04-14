from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from bananaslides.config import ModelAssetPaths
from bananaslides.utils import ocr_models
from bananaslides.utils.ocr_models import (
    DEFAULT_OCR_PRESET_ID,
    MissingOcrModelsError,
    ModelFileSpec,
    OcrPresetSpec,
    default_ocr_model_home,
    get_active_ocr_preset_id,
    install_ocr_preset,
    list_installed_ocr_presets,
    list_ocr_presets,
    resolve_ocr_model_assets,
)


def test_list_ocr_presets_contains_default_and_multilingual_variants() -> None:
    preset_ids = {preset.preset_id for preset in list_ocr_presets()}

    assert DEFAULT_OCR_PRESET_ID in preset_ids
    assert {"chinese", "english", "latin", "arabic", "cyrillic", "devanagari"} <= preset_ids


def test_install_ocr_preset_downloads_selected_preset_and_sets_active(tmp_path: Path, monkeypatch) -> None:
    preset, payloads = _build_test_preset(tmp_path, preset_id="demo")
    monkeypatch.setattr(ocr_models, "OCR_PRESET_CATALOG", {"demo": preset})

    def fake_downloader(url: str, output_path: Path) -> None:
        output_path.write_bytes(payloads[url])

    model_home = tmp_path / "cache"
    resolved = install_ocr_preset("demo", model_home=model_home, downloader=fake_downloader)

    assert resolved.preset_id == "demo"
    assert resolved.model_assets.all_exist()
    assert get_active_ocr_preset_id(model_home) == "demo"
    assert list_installed_ocr_presets(model_home) == ("demo",)
    assert (model_home / "presets" / "demo" / "manifest.json").exists()

    resolved_again = resolve_ocr_model_assets(model_home=model_home)
    assert resolved_again.source == "preset"
    assert resolved_again.preset_id == "demo"
    assert resolved_again.model_assets.all_exist()


def test_install_ocr_preset_uses_bundled_assets_before_network(tmp_path: Path, monkeypatch) -> None:
    preset, _ = _build_test_preset(tmp_path, preset_id="bundled", bundle_all=True)
    monkeypatch.setattr(ocr_models, "OCR_PRESET_CATALOG", {"bundled": preset})

    def fail_downloader(url: str, output_path: Path) -> None:
        raise AssertionError(f"Unexpected download attempt for {url}")

    resolved = install_ocr_preset("bundled", model_home=tmp_path / "cache", downloader=fail_downloader)

    assert resolved.model_assets.all_exist()
    assert get_active_ocr_preset_id(tmp_path / "cache") == "bundled"


def test_resolve_ocr_model_assets_falls_back_to_bundled_assets_when_no_active_preset(tmp_path: Path) -> None:
    fallback_assets = _write_model_asset_paths(tmp_path / "bundled")

    resolved = resolve_ocr_model_assets(
        model_home=tmp_path / "cache",
        fallback_assets=fallback_assets,
    )

    assert resolved.source == "bundled"
    assert resolved.preset_id is None
    assert resolved.model_assets == fallback_assets


def test_resolve_ocr_model_assets_requires_init_when_nothing_is_configured(tmp_path: Path) -> None:
    with pytest.raises(MissingOcrModelsError, match="init-models --preset ko-en"):
        resolve_ocr_model_assets(model_home=tmp_path / "cache")


def test_default_ocr_model_home_uses_bananaslides_env_var(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("BANANASLIDES_MODEL_HOME", str(tmp_path / "new-home"))

    assert default_ocr_model_home() == tmp_path / "new-home"


def test_default_ocr_model_home_uses_platform_default_without_env(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("BANANASLIDES_MODEL_HOME", raising=False)
    monkeypatch.setattr(ocr_models.sys, "platform", "linux")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))

    assert default_ocr_model_home() == tmp_path / "cache" / "bananaslides" / "ocr_models"


def test_default_ocr_model_home_migrates_legacy_cache_dir(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("BANANASLIDES_MODEL_HOME", raising=False)
    monkeypatch.setattr(ocr_models.sys, "platform", "linux")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))

    legacy_home = tmp_path / "cache" / "banana2pptx" / "ocr_models"
    legacy_home.mkdir(parents=True, exist_ok=True)
    (legacy_home / "active_preset.json").write_text('{"preset_id":"ko-en"}', encoding="utf-8")

    resolved_home = default_ocr_model_home()

    assert resolved_home == tmp_path / "cache" / "bananaslides" / "ocr_models"
    assert (resolved_home / "active_preset.json").exists()
    assert not legacy_home.exists()


def _build_test_preset(
    tmp_path: Path,
    *,
    preset_id: str,
    bundle_all: bool = False,
) -> tuple[OcrPresetSpec, dict[str, bytes]]:
    payloads: dict[str, bytes] = {}

    def make_file(filename: str, content: bytes) -> ModelFileSpec:
        url = f"https://example.test/{filename}"
        payloads[url] = content
        bundled_paths: tuple[Path, ...] = ()
        if bundle_all:
            bundled_path = tmp_path / "bundled-src" / filename
            bundled_path.parent.mkdir(parents=True, exist_ok=True)
            bundled_path.write_bytes(content)
            bundled_paths = (bundled_path,)
        return ModelFileSpec(
            filename=filename,
            urls=(url,),
            sha256=hashlib.sha256(content).hexdigest(),
            source_url=url,
            license_name="Apache-2.0",
            bundled_paths=bundled_paths,
        )

    return (
        OcrPresetSpec(
            preset_id=preset_id,
            display_name=f"{preset_id.title()} Preset",
            description="test preset",
            detector=make_file("det.onnx", b"det-bytes"),
            classifier=make_file("cls.onnx", b"cls-bytes"),
            recognizer=make_file("rec.onnx", b"rec-bytes"),
            dictionary=make_file("dict.txt", b"dict-bytes"),
        ),
        payloads,
    )


def _write_model_asset_paths(root: Path) -> ModelAssetPaths:
    root.mkdir(parents=True, exist_ok=True)
    paths = ModelAssetPaths(
        rapidocr_det_model=root / "det.onnx",
        rapidocr_cls_model=root / "cls.onnx",
        rapidocr_rec_model=root / "rec.onnx",
        rapidocr_keys=root / "keys.txt",
    )
    paths.rapidocr_det_model.write_bytes(b"det")
    paths.rapidocr_cls_model.write_bytes(b"cls")
    paths.rapidocr_rec_model.write_bytes(b"rec")
    paths.rapidocr_keys.write_bytes(b"keys")
    return paths
