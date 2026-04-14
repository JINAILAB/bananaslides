from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import typer

from bananaslides.config import PipelineConfig
from bananaslides.domain.models import PresentationRenderSpec, SlideRenderSpec, SlideSize
from bananaslides.modules.inpainting.mask import save_text_mask, save_text_mask_from_ocr_results
from bananaslides.modules.ppt.render import PowerPointRenderer
from bananaslides.modules.typesetting.fixed_font_typesetter import FixedFontTypesetter
from bananaslides.modules.typesetting.font_normalizer import normalize_presentation_fonts
from bananaslides.pipeline.factory import (
    build_default_components,
    build_inpainter,
    build_ocr_engine,
    build_text_detector,
)
from bananaslides.pipeline.orchestrator import ProcessedSlide, SlideToPptPipeline
from bananaslides.utils.artifacts import (
    build_pipeline_metadata,
    read_detection_artifact,
    read_ocr_artifact,
    write_correction_artifact,
    write_detection_artifact,
    write_ocr_artifact,
)
from bananaslides.utils.correction import (
    correct_ocr_results,
    load_expected_texts_file,
    load_expected_texts_from_deck_plan,
)
from bananaslides.utils.image import infer_slide_size
from bananaslides.utils.ocr_models import (
    DEFAULT_OCR_PRESET_ID,
    MissingOcrModelsError,
    OcrModelError,
    get_active_ocr_preset_id,
    install_ocr_preset,
    list_installed_ocr_presets,
    list_ocr_presets,
    resolve_ocr_model_assets,
    set_active_ocr_preset,
)
from bananaslides.utils.pdf import PdfRenderError, is_pdf_path, render_pdf_pages
from bananaslides.utils.ppt_patch import patch_ppt_preserve_style, save_ppt_text_inventory

app = typer.Typer(no_args_is_help=True, help="Rebuild editable PPT slides from slide images.")


@dataclass(slots=True)
class _PreparedSlideSource:
    image_path: Path
    slide_size: SlideSize
    original_source_path: Path


@app.command("show-config")
def show_config(
    ocr_model_home: Path | None = typer.Option(None, help="Override the OCR model cache directory."),
    ocr_preset: str | None = typer.Option(None, help="Resolve a specific OCR preset instead of the active preset."),
) -> None:
    """Print the default local asset and font configuration."""

    config = PipelineConfig()
    _apply_ocr_model_overrides(
        config,
        ocr_model_home=ocr_model_home,
        ocr_preset=ocr_preset,
    )
    typer.echo("Detector backends: ocr")
    typer.echo("OCR backends: portable | auto")
    typer.echo("Inpainting backends: telea")
    typer.echo(f"Detector backend: {config.detector_backend}")
    typer.echo(f"OCR backend: {config.ocr_backend}")
    typer.echo(f"OCR model home: {config.ocr_model_home}")
    typer.echo(f"OCR active preset: {get_active_ocr_preset_id(config.ocr_model_home) or '(none)'}")
    installed_presets = ", ".join(list_installed_ocr_presets(config.ocr_model_home)) or "(none)"
    typer.echo(f"Installed OCR presets: {installed_presets}")
    try:
        resolved_models = resolve_ocr_model_assets(
            model_home=config.ocr_model_home,
            preset_id=config.ocr_preset,
            fallback_assets=config.model_assets,
        )
        typer.echo(f"OCR model source: {resolved_models.source}")
        typer.echo(f"OCR resolved preset: {resolved_models.preset_id or '(bundled assets)'}")
        typer.echo(f"RapidOCR det model: {resolved_models.model_assets.rapidocr_det_model}")
        typer.echo(f"RapidOCR cls model: {resolved_models.model_assets.rapidocr_cls_model}")
        typer.echo(f"RapidOCR rec model: {resolved_models.model_assets.rapidocr_rec_model}")
        typer.echo(f"RapidOCR keys: {resolved_models.model_assets.rapidocr_keys}")
    except MissingOcrModelsError as exc:
        typer.echo(f"OCR models: {exc}")
    typer.echo(f"Inpainting backend: {config.inpainting_backend}")
    typer.echo(f"OpenCV inpaint radius: {config.cv2_inpaint_radius}")
    typer.echo(f"Korean font: {config.fonts.korean_font}")
    typer.echo(f"Latin font: {config.fonts.latin_font}")


@app.command("list-ocr-presets")
def list_ocr_presets_command(
    ocr_model_home: Path | None = typer.Option(None, help="Override the OCR model cache directory."),
) -> None:
    """List built-in OCR presets and their install status."""

    home = ocr_model_home or PipelineConfig().ocr_model_home
    active_preset = get_active_ocr_preset_id(home)
    installed_presets = set(list_installed_ocr_presets(home))
    for preset in list_ocr_presets():
        status: list[str] = []
        if preset.preset_id == DEFAULT_OCR_PRESET_ID:
            status.append("default")
        if preset.preset_id in installed_presets:
            status.append("installed")
        if preset.preset_id == active_preset:
            status.append("active")
        suffix = f" [{' '.join(status)}]" if status else ""
        typer.echo(f"{preset.preset_id}{suffix}: {preset.display_name}")
        typer.echo(f"  {preset.description}")


@app.command("init-models")
def init_models(
    preset: str = typer.Option(DEFAULT_OCR_PRESET_ID, help="OCR preset id to install."),
    ocr_model_home: Path | None = typer.Option(None, help="Override the OCR model cache directory."),
    force: bool = typer.Option(False, help="Reinstall the preset even if it is already installed."),
    activate: bool = typer.Option(True, "--activate/--no-activate", help="Set the installed preset as active."),
) -> None:
    """Install an OCR preset into the local model cache."""

    home = ocr_model_home or PipelineConfig().ocr_model_home
    try:
        resolved = install_ocr_preset(
            preset,
            home,
            activate=activate,
            force=force,
        )
    except OcrModelError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1)

    typer.echo(f"Installed OCR preset: {resolved.preset_id}")
    typer.echo(f"Model home: {resolved.model_home}")
    typer.echo(f"RapidOCR det model: {resolved.model_assets.rapidocr_det_model}")
    typer.echo(f"RapidOCR cls model: {resolved.model_assets.rapidocr_cls_model}")
    typer.echo(f"RapidOCR rec model: {resolved.model_assets.rapidocr_rec_model}")
    typer.echo(f"RapidOCR keys: {resolved.model_assets.rapidocr_keys}")
    if activate:
        typer.echo(f"Active OCR preset: {resolved.preset_id}")


@app.command("use-ocr-preset")
def use_ocr_preset(
    preset: str,
    ocr_model_home: Path | None = typer.Option(None, help="Override the OCR model cache directory."),
) -> None:
    """Switch the active OCR preset without reinstalling it."""

    home = ocr_model_home or PipelineConfig().ocr_model_home
    try:
        set_active_ocr_preset(preset, home)
    except OcrModelError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1)
    typer.echo(f"Active OCR preset: {preset}")


@app.command("detect-text")
def detect_text(
    slide_image: Path,
    output_json: Path | None = None,
    width_px: int | None = typer.Option(None, min=1),
    height_px: int | None = typer.Option(None, min=1),
    detector_backend: str | None = typer.Option(None, help="Detector backend: ocr."),
) -> None:
    """Run text detection and save detections.json."""

    _reject_pdf_input(slide_image, command_name="detect-text")
    config = PipelineConfig()
    if detector_backend is not None:
        config.detector_backend = detector_backend
    pipeline_metadata = build_pipeline_metadata(
        detector_backend=config.detector_backend,
        ocr_backend=config.ocr_backend,
        inpainting_backend=config.inpainting_backend,
    )
    slide_size = _resolve_slide_size(slide_image, width_px=width_px, height_px=height_px)
    detector = build_text_detector(config)
    detections = detector.detect(slide_image, slide_size)
    output_path = output_json or _default_artifact_dir(config, slide_image) / f"{slide_image.stem}.detections.json"
    write_detection_artifact(
        output_path,
        image_path=slide_image,
        slide_size=slide_size,
        backend=detector.backend_name,
        detections=detections,
        pipeline=pipeline_metadata,
    )
    typer.echo(f"Saved {output_path}")


@app.command("ocr-text")
def ocr_text(
    slide_image: Path,
    detections_json: Path,
    output_json: Path | None = None,
    ocr_backend: str | None = typer.Option(None, help="OCR backend: portable or auto."),
    ocr_preset: str | None = typer.Option(None, help="OCR preset id such as ko-en or latin."),
    ocr_model_home: Path | None = typer.Option(None, help="Override the OCR model cache directory."),
) -> None:
    """Run the configured OCR backend on detected text boxes and save ocr.json."""

    _reject_pdf_input(slide_image, command_name="ocr-text")
    config = PipelineConfig()
    if ocr_backend is not None:
        config.ocr_backend = ocr_backend
    _apply_ocr_model_overrides(
        config,
        ocr_model_home=ocr_model_home,
        ocr_preset=ocr_preset,
    )
    pipeline_metadata = build_pipeline_metadata(
        detector_backend=config.detector_backend,
        ocr_backend=config.ocr_backend,
        inpainting_backend=config.inpainting_backend,
    )
    _, detections = read_detection_artifact(detections_json)
    try:
        ocr_engine = build_ocr_engine(config)
    except MissingOcrModelsError as exc:
        raise typer.BadParameter(str(exc)) from exc
    results = ocr_engine.recognize(slide_image, detections)
    output_path = output_json or _default_artifact_dir(config, slide_image) / f"{slide_image.stem}.ocr.json"
    write_ocr_artifact(
        output_path,
        image_path=slide_image,
        backend=ocr_engine.backend_name,
        language=config.ocr_language,
        results=results,
        pipeline=pipeline_metadata,
    )
    typer.echo(f"Saved {output_path}")


@app.command("inpaint-text")
def inpaint_text(
    slide_image: Path,
    detections_json: Path,
    output_background: Path | None = None,
    output_mask: Path | None = None,
    ocr_json: Path | None = typer.Option(None, help="Optional OCR artifact to build a line-level mask."),
    inpainting_backend: str | None = typer.Option(None, help="Inpainting backend: telea."),
) -> None:
    """Build a text mask from detections and run the configured inpainter."""

    _reject_pdf_input(slide_image, command_name="inpaint-text")
    config = PipelineConfig()
    if inpainting_backend is not None:
        config.inpainting_backend = inpainting_backend
    slide_size, detections = read_detection_artifact(detections_json)
    artifact_dir = _default_artifact_dir(config, slide_image)
    mask_path = output_mask or artifact_dir / f"{slide_image.stem}.mask.png"
    background_path = output_background or artifact_dir / f"{slide_image.stem}.background.png"
    if ocr_json is not None:
        ocr_results = read_ocr_artifact(ocr_json)
        save_text_mask_from_ocr_results(slide_size=slide_size, ocr_results=ocr_results, output_path=mask_path)
    else:
        save_text_mask(slide_size=slide_size, detections=detections, output_path=mask_path)
    inpainter = build_inpainter(config)
    inpainter.inpaint(slide_image, mask_path, background_path)
    typer.echo(f"Saved {mask_path}")
    typer.echo(f"Saved {background_path}")


@app.command("run")
def run_pipeline(
    slide_image: Path,
    output_dir: Path | None = None,
    width_px: int | None = typer.Option(None, min=1),
    height_px: int | None = typer.Option(None, min=1),
    detector_backend: str | None = typer.Option(None, help="Detector backend: ocr."),
    ocr_backend: str | None = typer.Option(None, help="OCR backend: portable or auto."),
    ocr_preset: str | None = typer.Option(None, help="OCR preset id such as ko-en or latin."),
    ocr_model_home: Path | None = typer.Option(None, help="Override the OCR model cache directory."),
    inpainting_backend: str | None = typer.Option(None, help="Inpainting backend: telea."),
) -> None:
    """Run the full text restoration pipeline for one raster slide image."""

    _reject_pdf_input(slide_image, command_name="run")
    config = PipelineConfig()
    if detector_backend is not None:
        config.detector_backend = detector_backend
    if ocr_backend is not None:
        config.ocr_backend = ocr_backend
    _apply_ocr_model_overrides(
        config,
        ocr_model_home=ocr_model_home,
        ocr_preset=ocr_preset,
    )
    if inpainting_backend is not None:
        config.inpainting_backend = inpainting_backend
    try:
        pipeline = SlideToPptPipeline(config=config, components=build_default_components(config))
    except MissingOcrModelsError as exc:
        raise typer.BadParameter(str(exc)) from exc
    slide_size = _resolve_slide_size(slide_image, width_px=width_px, height_px=height_px)
    artifact_dir = output_dir or _default_artifact_dir(config, slide_image)
    paths = pipeline.run(slide_image_path=slide_image, slide_size=slide_size, output_dir=artifact_dir)
    typer.echo(f"Saved {paths.detections_json}")
    typer.echo(f"Saved {paths.ocr_json}")
    typer.echo(f"Saved {paths.mask_png}")
    typer.echo(f"Saved {paths.background_png}")
    typer.echo(f"Saved {paths.result_pptx}")


@app.command("deck")
def build_deck(
    slide_inputs: list[Path],
    output_dir: Path | None = None,
    output_pptx: Path | None = typer.Option(None, help="Final multi-slide deck output path."),
    detector_backend: str | None = typer.Option(None, help="Detector backend: ocr."),
    ocr_backend: str | None = typer.Option(None, help="OCR backend: portable or auto."),
    ocr_preset: str | None = typer.Option(None, help="OCR preset id such as ko-en or latin."),
    ocr_model_home: Path | None = typer.Option(None, help="Override the OCR model cache directory."),
    inpainting_backend: str | None = typer.Option(None, help="Inpainting backend: telea."),
) -> None:
    """Run the full pipeline for slide images and/or PDFs and build one PPT deck."""

    if not slide_inputs:
        raise typer.BadParameter("Provide at least one slide image or PDF.")

    config = PipelineConfig()
    if detector_backend is not None:
        config.detector_backend = detector_backend
    if ocr_backend is not None:
        config.ocr_backend = ocr_backend
    _apply_ocr_model_overrides(
        config,
        ocr_model_home=ocr_model_home,
        ocr_preset=ocr_preset,
    )
    if inpainting_backend is not None:
        config.inpainting_backend = inpainting_backend
    try:
        pipeline = SlideToPptPipeline(config=config, components=build_default_components(config))
    except MissingOcrModelsError as exc:
        raise typer.BadParameter(str(exc)) from exc

    deck_output_dir = output_dir or _default_deck_artifact_dir(config, slide_inputs[0])
    prepared_slides = _prepare_deck_sources(slide_inputs, deck_output_dir)
    processed_slides: list[ProcessedSlide] = []
    deck_slide_size: SlideSize | None = None

    for slide_index, prepared_slide in enumerate(prepared_slides, start=1):
        slide_image = prepared_slide.image_path
        slide_size = prepared_slide.slide_size
        if deck_slide_size is None:
            deck_slide_size = slide_size
        slide_output_dir = deck_output_dir / f"slide-{slide_index:02d}"
        processed = pipeline.process_slide(
            slide_image_path=slide_image,
            slide_size=slide_size,
            output_dir=slide_output_dir,
        )
        processed_slides.append(processed)
        typer.echo(f"Saved {processed.artifact_paths.detections_json}")
        typer.echo(f"Saved {processed.artifact_paths.ocr_json}")
        typer.echo(f"Saved {processed.artifact_paths.mask_png}")
        typer.echo(f"Saved {processed.artifact_paths.background_png}")

    assert deck_slide_size is not None
    slide_specs = [
        pipeline.build_slide_render_spec(processed, target_slide_size=deck_slide_size)
        for processed in processed_slides
    ]
    deck_output_path = output_pptx or deck_output_dir / "deck.pptx"
    normalized_spec = pipeline.render_presentation(slide_specs, deck_output_path)
    for processed, slide_spec in zip(processed_slides, normalized_spec.slides, strict=True):
        pipeline.components.renderer.render(
            PresentationRenderSpec(slides=[slide_spec], dpi=normalized_spec.dpi),
            processed.artifact_paths.result_pptx,
        )
        typer.echo(f"Saved {processed.artifact_paths.result_pptx}")
    typer.echo(f"Saved {deck_output_path}")


@app.command("repair-ocr")
def repair_ocr(
    ocr_json: Path,
    output_json: Path | None = None,
    correction_json: Path | None = None,
    deck_plan_file: Path | None = typer.Option(None),
    slide_number: int | None = typer.Option(None, min=1),
    expected_text_file: Path | None = typer.Option(None),
    expected_text: list[str] = typer.Option([]),
    min_score: float = typer.Option(0.74, min=0.0, max=1.0),
) -> None:
    """Correct OCR text using expected phrases from a deck plan or an explicit list."""

    candidates: list[str] = []
    if deck_plan_file is not None:
        if slide_number is None:
            raise typer.BadParameter("--slide-number is required when --deck-plan-file is used.")
        candidates.extend(load_expected_texts_from_deck_plan(deck_plan_file, slide_number))
    if expected_text_file is not None:
        candidates.extend(load_expected_texts_file(expected_text_file))
    if expected_text:
        candidates.extend(expected_text)
    if not candidates:
        raise typer.BadParameter("Provide expected text via --deck-plan-file/--slide-number, --expected-text-file, or --expected-text.")

    ocr_payload = json.loads(ocr_json.read_text(encoding="utf-8"))
    image_path = Path(ocr_payload.get("image_path", ocr_json))
    ocr_results = read_ocr_artifact(ocr_json)
    corrected_results, corrections = correct_ocr_results(ocr_results, candidates, min_score=min_score)
    output_path = output_json or ocr_json
    write_ocr_artifact(
        output_path,
        image_path=image_path,
        backend="ocr-correction",
        language="corrected",
        results=corrected_results,
    )
    report_path = correction_json or output_path.with_name(f"{output_path.stem}.corrections.json")
    write_correction_artifact(
        report_path,
        ocr_json_path=ocr_json,
        expected_texts=candidates,
        corrections=corrections,
    )
    typer.echo(f"Saved {output_path}")
    typer.echo(f"Saved {report_path}")


@app.command("render-from-artifacts")
def render_from_artifacts(
    detections_json: Path,
    ocr_json: Path,
    background_image: Path,
    output_pptx: Path,
) -> None:
    """Render an editable PPT from existing detections, OCR, and a clean background."""

    if not background_image.exists():
        raise typer.BadParameter(f"Background image not found: {background_image}")

    config = PipelineConfig()
    slide_size, detections = read_detection_artifact(detections_json)
    ocr_payload = json.loads(ocr_json.read_text(encoding="utf-8"))
    ocr_results = read_ocr_artifact(ocr_json)
    typesetter = FixedFontTypesetter(font_policy=config.fonts, dpi=config.default_dpi)
    source_image_path = Path(ocr_payload["image_path"]) if ocr_payload.get("image_path") else None
    if source_image_path is not None and not source_image_path.exists():
        source_image_path = None
    placements = typesetter.build_text_placements(
        detections,
        ocr_results,
        source_image_path=source_image_path,
        background_image_path=background_image,
    )
    spec = PresentationRenderSpec(
        slides=[
            SlideRenderSpec(
                slide_size=slide_size,
                background_image_path=background_image,
                text_placements=placements,
            )
        ],
        dpi=config.default_dpi,
    )
    spec = normalize_presentation_fonts(spec)
    renderer = PowerPointRenderer()
    renderer.render(spec, output_pptx)
    typer.echo(f"Saved {output_pptx}")


@app.command("render-background")
def render_background(
    background_image: Path,
    output_pptx: Path,
    width_px: int = typer.Option(..., min=1),
    height_px: int = typer.Option(..., min=1),
) -> None:
    """Create a one-slide PPT using only the background image."""

    if not background_image.exists():
        raise typer.BadParameter(f"Background image not found: {background_image}")

    slide = SlideRenderSpec(
        slide_size=SlideSize(width_px=width_px, height_px=height_px),
        background_image_path=background_image,
    )
    renderer = PowerPointRenderer()
    renderer.render(normalize_presentation_fonts(PresentationRenderSpec(slides=[slide])), output_pptx)
    typer.echo(f"Saved {output_pptx}")


@app.command("inspect-ppt-text")
def inspect_ppt_text(
    input_pptx: Path,
    output_json: Path,
    slide_number: int | None = typer.Option(None, min=1),
) -> None:
    """Export the current PPT text boxes and their styles to JSON."""

    save_ppt_text_inventory(input_pptx, output_json, slide_number=slide_number)
    typer.echo(f"Saved {output_json}")


@app.command("patch-ppt-preserve-style")
def patch_ppt_preserve_style_command(
    input_pptx: Path,
    mapping_json: Path,
    output_pptx: Path,
    slide_number: int | None = typer.Option(None, min=1),
) -> None:
    """Patch text and colors while preserving the original textbox style."""

    payload = json.loads(mapping_json.read_text(encoding="utf-8"))
    patch_ppt_preserve_style(input_pptx, output_pptx, payload, slide_number=slide_number)
    typer.echo(f"Saved {output_pptx}")

def _resolve_slide_size(
    slide_image: Path,
    *,
    width_px: int | None,
    height_px: int | None,
) -> SlideSize:
    if width_px is not None and height_px is not None:
        return SlideSize(width_px=width_px, height_px=height_px)
    return infer_slide_size(slide_image)


def _default_artifact_dir(config: PipelineConfig, slide_image: Path) -> Path:
    return config.default_output_dir / slide_image.stem


def _default_deck_artifact_dir(config: PipelineConfig, first_slide_image: Path) -> Path:
    return config.default_output_dir / f"{first_slide_image.stem}-deck"


def _reject_pdf_input(path: Path, *, command_name: str) -> None:
    if is_pdf_path(path):
        raise typer.BadParameter(
            f"The '{command_name}' command only supports raster slide images. Use 'bananaslides deck {path.name}' for PDFs."
        )


def _prepare_deck_sources(slide_inputs: list[Path], deck_output_dir: Path) -> list[_PreparedSlideSource]:
    prepared: list[_PreparedSlideSource] = []
    pdf_render_root = deck_output_dir / "_pdf-pages"

    for input_index, path in enumerate(slide_inputs, start=1):
        if not path.exists():
            raise typer.BadParameter(f"Input not found: {path}")
        if is_pdf_path(path):
            try:
                rendered_pages = render_pdf_pages(
                    path,
                    pdf_render_root / f"{input_index:02d}-{path.stem}",
                )
            except PdfRenderError as exc:
                raise typer.BadParameter(str(exc)) from exc
            prepared.extend(
                _PreparedSlideSource(
                    image_path=page.image_path,
                    slide_size=page.slide_size,
                    original_source_path=path,
                )
                for page in rendered_pages
            )
            continue

        prepared.append(
            _PreparedSlideSource(
                image_path=path,
                slide_size=infer_slide_size(path),
                original_source_path=path,
            )
        )

    if not prepared:
        raise typer.BadParameter("No slide pages were prepared from the provided inputs.")
    return prepared


def _apply_ocr_model_overrides(
    config: PipelineConfig,
    *,
    ocr_model_home: Path | None,
    ocr_preset: str | None,
) -> None:
    if ocr_model_home is not None:
        config.ocr_model_home = ocr_model_home
    if ocr_preset is not None:
        config.ocr_preset = ocr_preset


if __name__ == "__main__":
    app()
