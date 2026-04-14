from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from PIL import Image, ImageChops, ImageDraw
from bananaslides.config import PipelineConfig
from bananaslides.domain.models import (
    DetectionBox,
    ElementCategory,
    ImagePlacement,
    OCRLine,
    OCRResult,
    PresentationRenderSpec,
    SlideRenderSpec,
    SlideSize,
)
from bananaslides.modules.inpainting.mask import build_text_mask_from_ocr_results
from bananaslides.pipeline.factory import build_default_components, build_ocr_engine
from bananaslides.pipeline.orchestrator import ArtifactPaths, ProcessedSlide, SlideToPptPipeline
from bananaslides.utils.artifacts import read_detection_artifact, read_ocr_artifact, write_detection_artifact, write_ocr_artifact
from bananaslides.utils.geometry import bbox_bounds
from bananaslides.utils.image import infer_slide_size
from bananaslides.utils.pdf import is_pdf_path, render_pdf_pages
from bananaslides_webapi.store import JobStore, sanitize_filename


_GEOMETRY_TOLERANCE_PX = 1.0


@dataclass(slots=True)
class EditorBox:
    box_id: str
    x: float
    y: float
    width: float
    height: float
    category: str = ElementCategory.TEXT.value
    source: str = "base"
    source_box_id: str | None = None


def _slide_label(slide_number: int) -> str:
    return f"slide-{slide_number:03d}"


def _slide_artifacts(slide_dir: Path, slide_label: str) -> dict[str, str]:
    return {
        "repair_dir": slide_dir.name and str(slide_dir.relative_to(slide_dir.parents[1])),
        "detections_json": f"{slide_dir.relative_to(slide_dir.parents[1])}/{slide_label}.detections.json",
        "ocr_json": f"{slide_dir.relative_to(slide_dir.parents[1])}/{slide_label}.ocr.json",
        "mask_png": f"{slide_dir.relative_to(slide_dir.parents[1])}/{slide_label}.mask.png",
        "background_png": f"{slide_dir.relative_to(slide_dir.parents[1])}/{slide_label}.background.png",
        "result_pptx": f"{slide_dir.relative_to(slide_dir.parents[1])}/{slide_label}.pptx",
        "image_placements_json": f"{slide_dir.relative_to(slide_dir.parents[1])}/{slide_label}.image.placements.json",
        "baseline_detections_json": f"{slide_dir.relative_to(slide_dir.parents[1])}/{slide_label}.detections.base.json",
        "baseline_ocr_json": f"{slide_dir.relative_to(slide_dir.parents[1])}/{slide_label}.ocr.base.json",
        "ocr_edits_json": f"{slide_dir.relative_to(slide_dir.parents[1])}/{slide_label}.ocr.edits.json",
    }


def _pipeline(config: PipelineConfig) -> SlideToPptPipeline:
    return SlideToPptPipeline(config=config, components=build_default_components(config))


def deck_filename(job: dict[str, Any], *, safe: bool = False) -> str:
    pdf_upload = next((upload for upload in job["uploads"] if upload.get("kind") == "pdf"), None)
    if pdf_upload is None:
        return "bananaslides.pptx"

    original_name = Path(str(pdf_upload.get("original_name") or "deck.pdf")).name
    stem = Path(original_name).stem.strip() or "deck"
    if safe:
        stem = sanitize_filename(stem)
    return f"{stem}.pptx"


def prepare_job(store: JobStore, job_id: str) -> dict[str, Any]:
    job = store.load_job(job_id)
    job_dir = store.job_dir(job_id)
    slides_dir = job_dir / "slides"
    prepared_dir = job_dir / "prepared"
    shutil.rmtree(slides_dir, ignore_errors=True)
    slides_dir.mkdir(parents=True, exist_ok=True)
    job["slides"] = []

    slide_number = 1
    for upload in job["uploads"]:
        upload_path = store.resolve_job_path(job, upload["stored_relpath"])
        assert upload_path is not None
        if upload["kind"] == "pdf" or is_pdf_path(upload_path):
            rendered_pages = render_pdf_pages(upload_path, prepared_dir / upload["upload_id"])
            for page in rendered_pages:
                label = _slide_label(slide_number)
                target = slides_dir / f"{label}.png"
                shutil.copy2(page.image_path, target)
                job["slides"].append(
                    {
                        "slide_number": slide_number,
                        "label": label,
                        "source_type": "pdf_page",
                        "source_name": upload["original_name"],
                        "page_number": page.page_number,
                        "image_relpath": store.relative_to_job(job, target),
                        "slide_size": {"width_px": page.slide_size.width_px, "height_px": page.slide_size.height_px},
                        "status": "prepared",
                        "artifacts": None,
                    }
                )
                slide_number += 1
            continue

        if upload["kind"] != "image":
            raise ValueError(f"Unsupported upload type: {upload['original_name']}")
        label = _slide_label(slide_number)
        target = slides_dir / f"{label}{upload_path.suffix.lower()}"
        shutil.copy2(upload_path, target)
        size = infer_slide_size(target)
        job["slides"].append(
            {
                "slide_number": slide_number,
                "label": label,
                "source_type": "image",
                "source_name": upload["original_name"],
                "page_number": None,
                "image_relpath": store.relative_to_job(job, target),
                "slide_size": {"width_px": size.width_px, "height_px": size.height_px},
                "status": "prepared",
                "artifacts": None,
            }
        )
        slide_number += 1

    store.set_status(job, "prepared")
    return store.load_job(job_id)


def process_job(store: JobStore, job_id: str) -> dict[str, Any]:
    job = store.load_job(job_id)
    if not job["slides"]:
        job = prepare_job(store, job_id)
    store.set_status(job, "processing")
    config = PipelineConfig()
    pipeline = _pipeline(config)
    processed_slides: list[ProcessedSlide] = []
    deck_slide_size: SlideSize | None = None

    for slide in job["slides"]:
        image_path = store.resolve_job_path(job, slide["image_relpath"])
        assert image_path is not None
        slide_size = SlideSize(**slide["slide_size"])
        if deck_slide_size is None:
            deck_slide_size = slide_size
        repair_dir = store.job_dir(job_id) / "repair" / slide["label"]
        processed = pipeline.process_slide(image_path, slide_size, repair_dir)
        processed_slides.append(processed)
        artifacts = _artifact_manifest_from_processed(store, job, slide["label"], processed.artifact_paths)
        slide["artifacts"] = artifacts
        slide["status"] = "processed"
        _ensure_review_baselines(job, store, slide)

    if job["mode"] == "review":
        store.set_status(job, "awaiting_review")
        store.save_job(job)
        return store.load_job(job_id)

    assert deck_slide_size is not None
    deck_path = build_job_deck(store, job_id, job=job, processed_slides=processed_slides, deck_slide_size=deck_slide_size)
    job["outputs"]["deck_pptx"] = store.relative_to_job(job, deck_path)
    store.set_status(job, "completed")
    store.save_job(job)
    return store.load_job(job_id)


def build_job_deck(
    store: JobStore,
    job_id: str,
    *,
    job: dict[str, Any] | None = None,
    processed_slides: list[ProcessedSlide] | None = None,
    deck_slide_size: SlideSize | None = None,
) -> Path:
    job = job or store.load_job(job_id)
    config = PipelineConfig()
    pipeline = _pipeline(config)

    if processed_slides is None and job["mode"] == "review":
        for slide in job["slides"]:
            _rebuild_review_slide(store, job, slide, config=config)

    slide_specs: list[SlideRenderSpec] = []
    if processed_slides is not None:
        assert deck_slide_size is not None
        slide_specs = [
            pipeline.build_slide_render_spec(processed_slide, target_slide_size=deck_slide_size)
            for processed_slide in processed_slides
        ]
    else:
        for slide in job["slides"]:
            image_path = store.resolve_job_path(job, slide["image_relpath"])
            assert image_path is not None
            slide_size = SlideSize(**slide["slide_size"])
            deck_slide_size = deck_slide_size or slide_size
            detections_path = store.resolve_job_path(job, slide["artifacts"]["detections_json"])
            ocr_path = store.resolve_job_path(job, slide["artifacts"]["ocr_json"])
            background_path = store.resolve_job_path(job, slide["artifacts"]["background_png"])
            assert detections_path is not None and ocr_path is not None and background_path is not None
            _, detections = read_detection_artifact(detections_path)
            ocr_results = read_ocr_artifact(ocr_path)
            processed = ProcessedSlide(
                source_image_path=image_path,
                slide_size=slide_size,
                artifact_paths=ArtifactPaths(
                    detections_json=detections_path,
                    ocr_json=ocr_path,
                    mask_png=store.resolve_job_path(job, slide["artifacts"]["mask_png"]) or background_path,
                    background_png=background_path,
                    result_pptx=store.resolve_job_path(job, slide["artifacts"]["result_pptx"]) or background_path,
                ),
                detections=detections,
                ocr_results=ocr_results,
                image_placements=_read_image_placements_artifact(store, job, slide),
            )
            slide_specs.append(pipeline.build_slide_render_spec(processed, target_slide_size=deck_slide_size))

    exports_dir = store.job_dir(job_id) / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)
    deck_path = exports_dir / deck_filename(job, safe=True)
    normalized_spec = pipeline.render_presentation(slide_specs, deck_path)
    for slide, slide_spec in zip(job["slides"], normalized_spec.slides, strict=True):
        result_pptx = store.resolve_job_path(job, slide["artifacts"]["result_pptx"])
        assert result_pptx is not None
        pipeline.components.renderer.render(PresentationRenderSpec(slides=[slide_spec], dpi=normalized_spec.dpi), result_pptx)
    return deck_path


def get_editor_state(store: JobStore, job_id: str, slide_number: int) -> dict[str, Any]:
    job = store.load_job(job_id)
    slide = _find_slide(job, slide_number)
    image_path = store.resolve_job_path(job, slide["image_relpath"])
    baseline_ocr_path = store.resolve_job_path(job, slide["artifacts"]["baseline_ocr_json"])
    edits_path = store.resolve_job_path(job, slide["artifacts"]["ocr_edits_json"])
    assert image_path is not None and baseline_ocr_path is not None and edits_path is not None

    boxes = read_editor_edits(edits_path) if edits_path.exists() else build_editor_boxes(read_ocr_artifact(baseline_ocr_path))
    return {
        "job_id": job_id,
        "slide_number": slide_number,
        "slide_size": slide["slide_size"],
        "image_url": f"/jobs/{job_id}/files/{slide['image_relpath']}",
        "boxes": [_serialize_editor_box(box) for box in boxes],
        "ocr_edits_json": slide["artifacts"]["ocr_edits_json"],
    }


def save_editor_state(store: JobStore, job_id: str, slide_number: int, boxes_payload: Sequence[dict[str, Any]]) -> dict[str, Any]:
    job = store.load_job(job_id)
    slide = _find_slide(job, slide_number)
    edits_path = store.resolve_job_path(job, slide["artifacts"]["ocr_edits_json"])
    assert edits_path is not None
    boxes = [sanitize_editor_box(payload) for payload in boxes_payload]
    save_editor_edits(edits_path, boxes)
    return {
        "changed_items": [
            {
                "label": "OCR Edit Spec",
                "path": slide["artifacts"]["ocr_edits_json"],
            }
        ]
    }


def apply_slide_edits(store: JobStore, job_id: str, slide_number: int) -> dict[str, Any]:
    job = store.load_job(job_id)
    store.set_status(job, "rebuilding_slide")
    job = store.load_job(job_id)
    slide = _find_slide(job, slide_number)
    changed_items = _rebuild_review_slide(store, job, slide)
    if job["mode"] == "review":
        job["status"] = "awaiting_review"
        job["error"] = None
    store.touch(job)
    store.save_job(job)
    return {
        "slide_number": slide_number,
        "changed_items": changed_items,
    }


def _rebuild_review_slide(
    store: JobStore,
    job: dict[str, Any],
    slide: dict[str, Any],
    *,
    config: PipelineConfig | None = None,
) -> list[dict[str, str]]:
    edits_path = store.resolve_job_path(job, slide["artifacts"]["ocr_edits_json"])
    baseline_ocr_path = store.resolve_job_path(job, slide["artifacts"]["baseline_ocr_json"])
    detections_path = store.resolve_job_path(job, slide["artifacts"]["detections_json"])
    ocr_path = store.resolve_job_path(job, slide["artifacts"]["ocr_json"])
    mask_path = store.resolve_job_path(job, slide["artifacts"]["mask_png"])
    background_path = store.resolve_job_path(job, slide["artifacts"]["background_png"])
    result_pptx = store.resolve_job_path(job, slide["artifacts"]["result_pptx"])
    image_placements_path = store.resolve_job_path(job, _ensure_image_placements_artifact(slide))
    image_path = store.resolve_job_path(job, slide["image_relpath"])
    assert all(
        path is not None
        for path in (
            edits_path,
            baseline_ocr_path,
            detections_path,
            ocr_path,
            mask_path,
            background_path,
            result_pptx,
            image_placements_path,
            image_path,
        )
    )
    edits_path = edits_path  # type: ignore[assignment]
    baseline_ocr_path = baseline_ocr_path  # type: ignore[assignment]
    detections_path = detections_path  # type: ignore[assignment]
    ocr_path = ocr_path  # type: ignore[assignment]
    mask_path = mask_path  # type: ignore[assignment]
    background_path = background_path  # type: ignore[assignment]
    result_pptx = result_pptx  # type: ignore[assignment]
    image_placements_path = image_placements_path  # type: ignore[assignment]
    image_path = image_path  # type: ignore[assignment]

    baseline_ocr_results = read_ocr_artifact(baseline_ocr_path)
    saved_boxes = read_editor_edits(edits_path) if edits_path.exists() else build_editor_boxes(baseline_ocr_results)
    slide_size = SlideSize(**slide["slide_size"])

    config = config or PipelineConfig()
    pipeline = _pipeline(config)
    ocr_engine = build_ocr_engine(config)
    inpainter = pipeline.components.inpainter
    final_lines, text_removal_lines = rebuild_lines_from_editor_boxes(image_path, saved_boxes, baseline_ocr_results, ocr_engine)
    image_boxes = _image_boxes_from_editor_boxes(saved_boxes)
    synthetic_detection = DetectionBox(
        box_id="manual-editor-text",
        category=ElementCategory.TEXT,
        x=0,
        y=0,
        width=slide_size.width_px,
        height=slide_size.height_px,
    )
    image_detections = [_detection_from_box(box, ElementCategory.FIGURE) for box in image_boxes]
    synthetic_result = OCRResult(
        box_id=synthetic_detection.box_id,
        text="\n".join(line.text for line in final_lines if line.text.strip()),
        lines=final_lines,
        language="ko+en",
    )

    write_detection_artifact(
        detections_path,
        image_path=image_path,
        slide_size=slide_size,
        backend="manual-editor",
        detections=[synthetic_detection, *image_detections],
    )
    write_ocr_artifact(
        ocr_path,
        image_path=image_path,
        backend="manual-editor",
        language="ko+en",
        results=[synthetic_result],
    )
    text_mask = build_text_mask_from_ocr_results(
        slide_size=slide_size,
        ocr_results=[
            OCRResult(
                box_id="manual-editor-text-mask",
                text="",
                lines=text_removal_lines,
                language="ko+en",
            )
        ],
    )
    image_mask = _build_box_mask(slide_size, image_boxes)
    combined_mask = ImageChops.lighter(text_mask, image_mask)
    _save_mask_image(combined_mask, mask_path)

    image_assets_dir = image_placements_path.parent / f"{slide['label']}.image-boxes"
    text_mask_path = mask_path.with_name(f"{slide['label']}.mask.text.tmp.png")
    image_mask_path = mask_path.with_name(f"{slide['label']}.mask.image.tmp.png")
    text_background_path = background_path.with_name(f"{slide['label']}.background.text.tmp.png")
    try:
        if _mask_has_content(text_mask):
            _save_mask_image(text_mask, text_mask_path)
            inpainter.inpaint(image_path, text_mask_path, text_background_path)
        else:
            shutil.copy2(image_path, text_background_path)

        image_placements = _build_image_placements(
            slide_size=slide_size,
            source_image_path=text_background_path,
            boxes=image_boxes,
            output_dir=image_assets_dir,
        )
        _write_image_placements_artifact(image_placements_path, store, job, image_placements)

        if _mask_has_content(image_mask):
            _save_mask_image(image_mask, image_mask_path)
            inpainter.inpaint(text_background_path, image_mask_path, background_path)
        else:
            shutil.copy2(text_background_path, background_path)
    finally:
        for temp_path in (text_mask_path, image_mask_path, text_background_path):
            if temp_path.exists():
                temp_path.unlink()

    slide_spec = pipeline.build_slide_render_spec(
        ProcessedSlide(
            source_image_path=image_path,
            slide_size=slide_size,
            artifact_paths=ArtifactPaths(
                detections_json=detections_path,
                ocr_json=ocr_path,
                mask_png=mask_path,
                background_png=background_path,
                result_pptx=result_pptx,
            ),
            detections=[synthetic_detection, *image_detections],
            ocr_results=[synthetic_result],
            image_placements=image_placements,
        )
    )
    pipeline.render_presentation([slide_spec], result_pptx)
    slide["status"] = "reviewed"
    return [
        {"label": "Detections", "path": slide["artifacts"]["detections_json"]},
        {"label": "OCR", "path": slide["artifacts"]["ocr_json"]},
        {"label": "Image Placements", "path": slide["artifacts"]["image_placements_json"]},
        {"label": "Mask", "path": slide["artifacts"]["mask_png"]},
        {"label": "Background", "path": slide["artifacts"]["background_png"]},
        {"label": "Slide PPT", "path": slide["artifacts"]["result_pptx"]},
    ]


def build_editor_boxes(ocr_results: Sequence[OCRResult]) -> list[EditorBox]:
    boxes: list[EditorBox] = []
    counter = 1
    for result in ocr_results:
        for line in result.lines:
            if not line.text.strip():
                continue
            rect = _rect_from_line(line)
            if rect is None:
                continue
            box_id = f"line-{counter:03d}"
            boxes.append(
                EditorBox(
                    box_id=box_id,
                    x=rect[0],
                    y=rect[1],
                    width=rect[2],
                    height=rect[3],
                    category=ElementCategory.TEXT.value,
                    source="base",
                    source_box_id=box_id,
                )
            )
            counter += 1
    return boxes


def save_editor_edits(path: Path, boxes: Sequence[EditorBox]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "boxes": [_serialize_editor_box(box) for box in boxes],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def read_editor_edits(path: Path) -> list[EditorBox]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [sanitize_editor_box(item) for item in payload.get("boxes", [])]


def sanitize_editor_box(payload: dict[str, Any]) -> EditorBox:
    category = ElementCategory.FIGURE.value if payload.get("category") == ElementCategory.FIGURE.value else ElementCategory.TEXT.value
    return EditorBox(
        box_id=str(payload["box_id"]),
        x=float(payload["x"]),
        y=float(payload["y"]),
        width=max(1.0, float(payload["width"])),
        height=max(1.0, float(payload["height"])),
        category=category,
        source=str(payload.get("source") or "manual"),
        source_box_id=str(payload["source_box_id"]) if payload.get("source_box_id") else None,
    )


def _serialize_editor_box(box: EditorBox) -> dict[str, Any]:
    return {
        "box_id": box.box_id,
        "x": box.x,
        "y": box.y,
        "width": box.width,
        "height": box.height,
        "category": box.category,
        "source": box.source,
        "source_box_id": box.source_box_id,
    }


def _ensure_image_placements_artifact(slide: dict[str, Any]) -> str:
    artifacts = slide["artifacts"]
    relpath = artifacts.get("image_placements_json")
    if relpath:
        return relpath
    relpath = str(Path(artifacts["repair_dir"]) / f"{slide['label']}.image.placements.json")
    artifacts["image_placements_json"] = relpath
    return relpath


def _read_image_placements_artifact(
    store: JobStore,
    job: dict[str, Any],
    slide: dict[str, Any],
) -> list[ImagePlacement]:
    artifact_path = store.resolve_job_path(job, _ensure_image_placements_artifact(slide))
    if artifact_path is None or not artifact_path.exists():
        return []
    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    placements: list[ImagePlacement] = []
    for item in payload.get("placements", []):
        image_path = store.resolve_job_path(job, item.get("image_relpath"))
        if image_path is None or not image_path.exists():
            continue
        placements.append(
            ImagePlacement(
                box_id=str(item["box_id"]),
                image_path=image_path,
                x=float(item["x"]),
                y=float(item["y"]),
                width=float(item["width"]),
                height=float(item["height"]),
            )
        )
    return placements


def _write_image_placements_artifact(
    output_path: Path,
    store: JobStore,
    job: dict[str, Any],
    placements: Sequence[ImagePlacement],
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "placements": [
            {
                "box_id": placement.box_id,
                "image_relpath": store.relative_to_job(job, placement.image_path),
                "x": placement.x,
                "y": placement.y,
                "width": placement.width,
                "height": placement.height,
            }
            for placement in placements
        ]
    }
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _image_boxes_from_editor_boxes(boxes: Sequence[EditorBox]) -> list[EditorBox]:
    return sorted(
        (box for box in boxes if box.category == ElementCategory.FIGURE.value),
        key=lambda item: (item.y, item.x),
    )


def _detection_from_box(box: EditorBox, category: ElementCategory) -> DetectionBox:
    return DetectionBox(
        box_id=box.box_id,
        category=category,
        x=box.x,
        y=box.y,
        width=box.width,
        height=box.height,
    )


def _build_box_mask(
    slide_size: SlideSize,
    boxes: Sequence[EditorBox],
    *,
    padding_px: int = 0,
) -> Image.Image:
    mask = Image.new("L", slide_size.as_tuple(), 0)
    draw = ImageDraw.Draw(mask)
    for box in boxes:
        bounds = _box_bounds(box, slide_size, padding_px=padding_px)
        if bounds is None:
            continue
        draw.rectangle(bounds, fill=255)
    return mask


def _save_mask_image(mask: Image.Image, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    mask.save(output_path)
    return output_path


def _mask_has_content(mask: Image.Image) -> bool:
    return mask.getbbox() is not None


def _build_image_placements(
    *,
    slide_size: SlideSize,
    source_image_path: Path,
    boxes: Sequence[EditorBox],
    output_dir: Path,
) -> list[ImagePlacement]:
    shutil.rmtree(output_dir, ignore_errors=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    placements: list[ImagePlacement] = []
    with Image.open(source_image_path) as source_image:
        source_rgb = source_image.convert("RGB")
        for index, box in enumerate(boxes, start=1):
            bounds = _box_bounds(box, slide_size)
            if bounds is None:
                continue
            crop = source_rgb.crop(bounds)
            safe_box_id = sanitize_filename(box.box_id)
            output_path = output_dir / f"{index:03d}-{safe_box_id}.png"
            crop.save(output_path)
            placements.append(
                ImagePlacement(
                    box_id=box.box_id,
                    image_path=output_path.resolve(),
                    x=box.x,
                    y=box.y,
                    width=box.width,
                    height=box.height,
                )
            )
    return placements


def rebuild_lines_from_editor_boxes(
    image_path: Path,
    boxes: Sequence[EditorBox],
    baseline_ocr_results: Sequence[OCRResult],
    ocr_engine,
) -> tuple[list[OCRLine], list[OCRLine]]:
    baseline_boxes = build_editor_boxes(baseline_ocr_results)
    baseline_map = {box.box_id: line for box, line in zip(baseline_boxes, _iter_lines(baseline_ocr_results), strict=False)}
    final_lines: list[OCRLine] = []
    removal_lines: list[OCRLine] = []

    for box in sorted(boxes, key=lambda item: (item.y, item.x)):
        if box.category != ElementCategory.TEXT.value:
            continue

        baseline_line = baseline_map.get(box.source_box_id or box.box_id)
        if baseline_line is not None and _same_geometry(box, baseline_line):
            final_lines.append(baseline_line)
            removal_lines.append(baseline_line)
            continue

        if baseline_line is not None:
            removal_lines.append(baseline_line)
        removal_lines.append(_line_from_box(box))

        detection = _ocr_detection_for_box(box)
        recognized = ocr_engine.recognize(image_path, [detection])
        if not recognized:
            continue
        for line in recognized[0].lines:
            if line.text.strip() and _line_intersects_box(line, box):
                final_lines.append(line)

    final_lines.sort(key=lambda line: (min(point[1] for point in line.bbox), min(point[0] for point in line.bbox)))
    removal_lines.sort(key=lambda line: (min(point[1] for point in line.bbox), min(point[0] for point in line.bbox)))
    return final_lines, removal_lines


def _iter_lines(results: Sequence[OCRResult]) -> list[OCRLine]:
    lines: list[OCRLine] = []
    for result in results:
        lines.extend(result.lines)
    return lines


def _same_geometry(box: EditorBox, line: OCRLine) -> bool:
    rect = _rect_from_line(line)
    if rect is None:
        return False
    return (
        abs(box.x - rect[0]) <= _GEOMETRY_TOLERANCE_PX
        and abs(box.y - rect[1]) <= _GEOMETRY_TOLERANCE_PX
        and abs(box.width - rect[2]) <= _GEOMETRY_TOLERANCE_PX
        and abs(box.height - rect[3]) <= _GEOMETRY_TOLERANCE_PX
    )


def _ocr_detection_for_box(box: EditorBox, padding_px: float = 20.0) -> DetectionBox:
    return DetectionBox(
        box_id=box.box_id,
        category=ElementCategory.TEXT,
        x=box.x - padding_px,
        y=box.y - padding_px,
        width=box.width + (padding_px * 2),
        height=box.height + (padding_px * 2),
    )


def _line_from_box(box: EditorBox) -> OCRLine:
    return OCRLine(
        text="",
        bbox=[
            [box.x, box.y],
            [box.x + box.width, box.y],
            [box.x + box.width, box.y + box.height],
            [box.x, box.y + box.height],
        ],
        confidence=None,
    )


def _line_intersects_box(line: OCRLine, box: EditorBox) -> bool:
    if not line.bbox:
        return False
    line_left, line_top, line_right, line_bottom = bbox_bounds(line.bbox)
    box_left = box.x
    box_top = box.y
    box_right = box.x + box.width
    box_bottom = box.y + box.height
    return not (
        line_right < box_left
        or line_left > box_right
        or line_bottom < box_top
        or line_top > box_bottom
    )


def _rect_from_line(line: OCRLine) -> tuple[float, float, float, float] | None:
    if not line.bbox:
        return None
    left, top, right, bottom = bbox_bounds(line.bbox)
    return (left, top, right - left, bottom - top)


def _box_bounds(
    box: EditorBox,
    slide_size: SlideSize,
    *,
    padding_px: int = 0,
) -> tuple[int, int, int, int] | None:
    left = max(0, round(box.x) - padding_px)
    top = max(0, round(box.y) - padding_px)
    right = min(slide_size.width_px, round(box.x + box.width) + padding_px)
    bottom = min(slide_size.height_px, round(box.y + box.height) + padding_px)
    if right <= left or bottom <= top:
        return None
    return (left, top, right, bottom)


def _find_slide(job: dict[str, Any], slide_number: int) -> dict[str, Any]:
    for slide in job["slides"]:
        if int(slide["slide_number"]) == int(slide_number):
            return slide
    raise KeyError(f"Slide not found: {slide_number}")


def _artifact_manifest_from_processed(store: JobStore, job: dict[str, Any], label: str, paths: ArtifactPaths) -> dict[str, str]:
    job_dir = store.job_dir(job["job_id"])
    slide_dir = paths.detections_json.parent
    return {
        "repair_dir": str(slide_dir.relative_to(job_dir)),
        "detections_json": str(paths.detections_json.relative_to(job_dir)),
        "ocr_json": str(paths.ocr_json.relative_to(job_dir)),
        "mask_png": str(paths.mask_png.relative_to(job_dir)),
        "background_png": str(paths.background_png.relative_to(job_dir)),
        "result_pptx": str(paths.result_pptx.relative_to(job_dir)),
        "image_placements_json": str((slide_dir / f"{label}.image.placements.json").relative_to(job_dir)),
        "baseline_detections_json": str((slide_dir / f"{label}.detections.base.json").relative_to(job_dir)),
        "baseline_ocr_json": str((slide_dir / f"{label}.ocr.base.json").relative_to(job_dir)),
        "ocr_edits_json": str((slide_dir / f"{label}.ocr.edits.json").relative_to(job_dir)),
    }


def _ensure_review_baselines(job: dict[str, Any], store: JobStore, slide: dict[str, Any]) -> None:
    artifacts = slide["artifacts"]
    detections_path = store.resolve_job_path(job, artifacts["detections_json"])
    ocr_path = store.resolve_job_path(job, artifacts["ocr_json"])
    baseline_detections_path = store.resolve_job_path(job, artifacts["baseline_detections_json"])
    baseline_ocr_path = store.resolve_job_path(job, artifacts["baseline_ocr_json"])
    assert detections_path is not None and ocr_path is not None and baseline_detections_path is not None and baseline_ocr_path is not None
    if not baseline_detections_path.exists():
        shutil.copy2(detections_path, baseline_detections_path)
    if not baseline_ocr_path.exists():
        shutil.copy2(ocr_path, baseline_ocr_path)
