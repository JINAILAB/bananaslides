from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path

from bananaslides.config import PipelineConfig
from bananaslides.domain.models import (
    DetectionBox,
    ImagePlacement,
    OCRResult,
    PresentationRenderSpec,
    SlideRenderSpec,
    SlideSize,
)
from bananaslides.modules.inpainting.mask import save_text_mask, save_text_mask_from_ocr_results
from bananaslides.modules.detection.base import TextDetector
from bananaslides.modules.inpainting.base import Inpainter
from bananaslides.modules.ocr.base import OcrEngine
from bananaslides.modules.ppt.render import PowerPointRenderer
from bananaslides.modules.typesetting.base import Typesetter
from bananaslides.modules.typesetting.font_normalizer import normalize_presentation_fonts
from bananaslides.utils.artifacts import build_pipeline_metadata, write_detection_artifact, write_ocr_artifact


@dataclass(slots=True)
class PipelineComponents:
    detector: TextDetector
    ocr_engine: OcrEngine
    inpainter: Inpainter
    typesetter: Typesetter
    renderer: PowerPointRenderer


@dataclass(slots=True)
class ArtifactPaths:
    detections_json: Path
    ocr_json: Path
    mask_png: Path
    background_png: Path
    result_pptx: Path


@dataclass(slots=True)
class ProcessedSlide:
    source_image_path: Path
    slide_size: SlideSize
    artifact_paths: ArtifactPaths
    detections: list[DetectionBox]
    ocr_results: list[OCRResult]
    image_placements: list[ImagePlacement] = field(default_factory=list)


class SlideToPptPipeline:
    def __init__(self, config: PipelineConfig, components: PipelineComponents) -> None:
        self.config = config
        self.components = components

    def build_artifact_paths(self, output_dir: Path, stem: str) -> ArtifactPaths:
        output_dir.mkdir(parents=True, exist_ok=True)
        return ArtifactPaths(
            detections_json=output_dir / f"{stem}.detections.json",
            ocr_json=output_dir / f"{stem}.ocr.json",
            mask_png=output_dir / f"{stem}.mask.png",
            background_png=output_dir / f"{stem}.background.png",
            result_pptx=output_dir / f"{stem}.pptx",
        )

    def build_slide_render_spec(
        self,
        processed_slide: ProcessedSlide,
        *,
        target_slide_size: SlideSize | None = None,
    ) -> SlideRenderSpec:
        placements = self.components.typesetter.build_text_placements(
            processed_slide.detections,
            processed_slide.ocr_results,
            source_image_path=processed_slide.source_image_path,
            background_image_path=processed_slide.artifact_paths.background_png,
        )
        slide_spec = SlideRenderSpec(
            slide_size=processed_slide.slide_size,
            background_image_path=processed_slide.artifact_paths.background_png,
            image_placements=list(processed_slide.image_placements),
            text_placements=placements,
        )
        if target_slide_size is not None:
            slide_spec = self._scale_slide_render_spec(slide_spec, target_slide_size)
        return slide_spec

    def render_presentation(
        self,
        slide_specs: list[SlideRenderSpec],
        output_pptx: Path,
    ) -> PresentationRenderSpec:
        spec = PresentationRenderSpec(slides=slide_specs, dpi=self.config.default_dpi)
        spec = normalize_presentation_fonts(spec)
        self.components.renderer.render(spec, output_pptx)
        return spec

    def process_slide(self, slide_image_path: Path, slide_size: SlideSize, output_dir: Path) -> ProcessedSlide:
        stem = slide_image_path.stem
        artifact_paths = self.build_artifact_paths(output_dir=output_dir, stem=stem)
        pipeline_metadata = build_pipeline_metadata(
            detector_backend=self.config.detector_backend,
            ocr_backend=self.config.ocr_backend,
            inpainting_backend=self.config.inpainting_backend,
        )
        detections = self.components.detector.detect(slide_image_path=slide_image_path, slide_size=slide_size)
        write_detection_artifact(
            artifact_paths.detections_json,
            image_path=slide_image_path,
            slide_size=slide_size,
            backend=getattr(self.components.detector, "backend_name", self.components.detector.__class__.__name__),
            detections=detections,
            pipeline=pipeline_metadata,
        )

        ocr_results = self.components.ocr_engine.recognize(slide_image_path=slide_image_path, detections=detections)
        write_ocr_artifact(
            artifact_paths.ocr_json,
            image_path=slide_image_path,
            backend=getattr(self.components.ocr_engine, "backend_name", self.components.ocr_engine.__class__.__name__),
            language=self.config.ocr_language,
            results=ocr_results,
            pipeline=pipeline_metadata,
        )

        if any(result.lines for result in ocr_results):
            save_text_mask_from_ocr_results(
                slide_size=slide_size,
                ocr_results=ocr_results,
                output_path=artifact_paths.mask_png,
            )
        else:
            save_text_mask(
                slide_size=slide_size,
                detections=detections,
                output_path=artifact_paths.mask_png,
            )
        self.components.inpainter.inpaint(
            slide_image_path=slide_image_path,
            mask_path=artifact_paths.mask_png,
            output_path=artifact_paths.background_png,
        )
        return ProcessedSlide(
            source_image_path=slide_image_path,
            slide_size=slide_size,
            artifact_paths=artifact_paths,
            detections=detections,
            ocr_results=ocr_results,
        )

    def run(self, slide_image_path: Path, slide_size: SlideSize, output_dir: Path) -> ArtifactPaths:
        processed_slide = self.process_slide(slide_image_path=slide_image_path, slide_size=slide_size, output_dir=output_dir)
        slide_spec = self.build_slide_render_spec(processed_slide)
        self.render_presentation([slide_spec], processed_slide.artifact_paths.result_pptx)
        return processed_slide.artifact_paths

    @staticmethod
    def _scale_slide_render_spec(slide_spec: SlideRenderSpec, target_slide_size: SlideSize) -> SlideRenderSpec:
        if (
            slide_spec.slide_size.width_px == target_slide_size.width_px
            and slide_spec.slide_size.height_px == target_slide_size.height_px
        ):
            return slide_spec

        source_width = max(1, slide_spec.slide_size.width_px)
        source_height = max(1, slide_spec.slide_size.height_px)
        scale_x = target_slide_size.width_px / source_width
        scale_y = target_slide_size.height_px / source_height
        font_scale = min(scale_x, scale_y)

        scaled_placements = [
            replace(
                placement,
                x=placement.x * scale_x,
                y=placement.y * scale_y,
                width=placement.width * scale_x,
                height=placement.height * scale_y,
                font_size_pt=placement.font_size_pt * font_scale,
            )
            for placement in slide_spec.text_placements
        ]
        scaled_images = [
            replace(
                placement,
                x=placement.x * scale_x,
                y=placement.y * scale_y,
                width=placement.width * scale_x,
                height=placement.height * scale_y,
            )
            for placement in slide_spec.image_placements
        ]
        return SlideRenderSpec(
            slide_size=target_slide_size,
            background_image_path=slide_spec.background_image_path,
            image_placements=scaled_images,
            text_placements=scaled_placements,
        )
