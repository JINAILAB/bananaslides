from __future__ import annotations

import io
import json
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from bananaslides.domain.models import (
    DetectionBox,
    ElementCategory,
    OCRLine,
    OCRResult,
    RGBColor,
    SlideSize,
    TextPlacement,
)
from bananaslides.modules.inpainting.base import Inpainter
from bananaslides.modules.ocr.base import OcrEngine
from bananaslides.modules.ppt.render import PowerPointRenderer
from bananaslides.pipeline.orchestrator import PipelineComponents
from bananaslides.utils.pdf import RenderedPdfPage
from bananaslides_webapi import main as webapi_main
from bananaslides_webapi.main import create_app
from bananaslides_webapi.store import JobStore
import bananaslides_webapi.service as service_module


class _FakeDetector:
    backend_name = "web_fake_detector"

    def detect(self, slide_image_path: Path, slide_size: SlideSize) -> list[DetectionBox]:
        return [
            DetectionBox(
                box_id="t0001",
                category=ElementCategory.TEXT,
                x=120,
                y=96,
                width=max(240, slide_size.width_px // 3),
                height=72,
            )
        ]


class _FakeOcrEngine(OcrEngine):
    backend_name = "web_fake_ocr"

    def recognize(self, slide_image_path: Path, detections: list[DetectionBox]) -> list[OCRResult]:
        results: list[OCRResult] = []
        for detection in detections:
            left = detection.x
            top = detection.y
            right = detection.x + detection.width
            bottom = detection.y + detection.height
            text = f"{slide_image_path.stem}:{detection.box_id}"
            results.append(
                OCRResult(
                    box_id=detection.box_id,
                    text=text,
                    lines=[
                        OCRLine(
                            text=text,
                            bbox=[
                                [left, top],
                                [right, top],
                                [right, bottom],
                                [left, bottom],
                            ],
                            confidence=0.99,
                        )
                    ],
                    language="ko+en",
                    confidence=0.99,
                )
            )
        return results


class _CopyInpainter(Inpainter):
    def inpaint(self, slide_image_path: Path, mask_path: Path, output_path: Path) -> Path:
        output_path.write_bytes(slide_image_path.read_bytes())
        return output_path


class _FakeTypesetter:
    def build_text_placements(
        self,
        detections,
        ocr_results,
        *,
        source_image_path=None,
        background_image_path=None,
    ) -> list[TextPlacement]:
        placements: list[TextPlacement] = []
        for index, result in enumerate(ocr_results, start=1):
            line = result.lines[0]
            placements.append(
                TextPlacement(
                    box_id=result.box_id,
                    text=result.text,
                    x=float(line.bbox[0][0]),
                    y=float(line.bbox[0][1]),
                    width=float(line.bbox[1][0] - line.bbox[0][0]),
                    height=float(line.bbox[2][1] - line.bbox[1][1]),
                    font_name="Pretendard",
                    font_size_pt=18.0 + index,
                    color=RGBColor(10, 20, 30),
                    language="ko",
                )
            )
        return placements


def _fake_components():
    return PipelineComponents(
        detector=_FakeDetector(),
        ocr_engine=_FakeOcrEngine(),
        inpainter=_CopyInpainter(),
        typesetter=_FakeTypesetter(),
        renderer=PowerPointRenderer(),
    )


def _png_bytes(*, width: int = 1280, height: int = 720, color: str = "white") -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buffer, format="PNG")
    return buffer.getvalue()


def _build_client(tmp_path: Path, monkeypatch) -> TestClient:
    store = JobStore(tmp_path / "web-data")
    monkeypatch.setattr(service_module, "build_default_components", lambda config: _fake_components())
    monkeypatch.setattr(service_module, "build_ocr_engine", lambda config: _FakeOcrEngine())
    monkeypatch.setattr(webapi_main, "_start_background", lambda job_id, target, store: target())
    app = create_app(store=store)
    return TestClient(app)


def test_auto_mode_image_job_endpoints(tmp_path: Path, monkeypatch) -> None:
    client = _build_client(tmp_path, monkeypatch)

    response = client.post(
        "/jobs",
        data={"mode": "auto"},
        files=[("files", ("slide.png", _png_bytes(), "image/png"))],
    )
    assert response.status_code == 200
    job_id = response.json()["job_id"]

    response = client.post(f"/jobs/{job_id}/prepare")
    assert response.status_code == 200
    prepared = response.json()
    assert prepared["status"] == "prepared"
    assert len(prepared["slides"]) == 1

    response = client.post(f"/jobs/{job_id}/process")
    assert response.status_code == 200
    assert response.json()["ok"] is True

    job = client.get(f"/jobs/{job_id}").json()
    assert job["status"] == "completed"
    deck_relpath = job["outputs"]["deck_pptx"]
    assert deck_relpath and deck_relpath.endswith("deck.final.pptx")

    download = client.get(f"/jobs/{job_id}/download")
    assert download.status_code == 200
    assert download.headers["content-type"] == "application/vnd.openxmlformats-officedocument.presentationml.presentation"


def test_review_mode_editor_save_apply_and_build_deck(tmp_path: Path, monkeypatch) -> None:
    client = _build_client(tmp_path, monkeypatch)

    response = client.post(
        "/jobs",
        data={"mode": "review"},
        files=[("files", ("slide.png", _png_bytes(color="lightgray"), "image/png"))],
    )
    assert response.status_code == 200
    job_id = response.json()["job_id"]

    assert client.post(f"/jobs/{job_id}/prepare").status_code == 200
    assert client.post(f"/jobs/{job_id}/process").status_code == 200

    job = client.get(f"/jobs/{job_id}").json()
    assert job["status"] == "awaiting_review"

    editor_state = client.get(f"/jobs/{job_id}/slides/1/editor-state")
    assert editor_state.status_code == 200
    payload = editor_state.json()
    assert payload["slide_number"] == 1
    assert len(payload["boxes"]) == 1

    store = client.app.state.job_store
    job_record = store.load_job(job_id)
    slide = job_record["slides"][0]
    ocr_path = store.resolve_job_path(job_record, slide["artifacts"]["ocr_json"])
    edits_path = store.resolve_job_path(job_record, slide["artifacts"]["ocr_edits_json"])
    assert ocr_path is not None and edits_path is not None
    baseline_ocr = ocr_path.read_text(encoding="utf-8")

    save = client.post(
        f"/jobs/{job_id}/slides/1/editor-save",
        json={"boxes": payload["boxes"]},
    )
    assert save.status_code == 200
    assert edits_path.exists()
    assert ocr_path.read_text(encoding="utf-8") == baseline_ocr

    apply = client.post(f"/jobs/{job_id}/slides/1/apply")
    assert apply.status_code == 200
    apply_payload = apply.json()
    assert apply_payload["ok"] is True
    changed_labels = {item["label"] for item in apply_payload["changed_items"]}
    assert changed_labels == {"Detections", "OCR", "Mask", "Background", "Slide PPT"}

    build = client.post(f"/jobs/{job_id}/build-deck")
    assert build.status_code == 200
    deck_relpath = build.json()["deck_pptx"]
    assert deck_relpath.endswith("deck.final.pptx")

    final_job = client.get(f"/jobs/{job_id}").json()
    assert final_job["status"] == "completed"
    assert client.get(f"/jobs/{job_id}/download").status_code == 200


def test_prepare_job_expands_pdf_uploads(tmp_path: Path, monkeypatch) -> None:
    client = _build_client(tmp_path, monkeypatch)

    page_dir = tmp_path / "pdf-pages"
    page_dir.mkdir(parents=True, exist_ok=True)
    page_one = page_dir / "page-001.png"
    page_two = page_dir / "page-002.png"
    page_one.write_bytes(_png_bytes(width=1200, height=675))
    page_two.write_bytes(_png_bytes(width=1400, height=900))

    monkeypatch.setattr(
        service_module,
        "render_pdf_pages",
        lambda pdf_path, output_dir: [
            RenderedPdfPage(
                source_pdf_path=pdf_path,
                page_number=1,
                image_path=page_one,
                slide_size=SlideSize(width_px=1200, height_px=675),
            ),
            RenderedPdfPage(
                source_pdf_path=pdf_path,
                page_number=2,
                image_path=page_two,
                slide_size=SlideSize(width_px=1400, height_px=900),
            ),
        ],
    )

    response = client.post(
        "/jobs",
        data={"mode": "auto"},
        files=[("files", ("report.pdf", b"%PDF-1.4\n%fake\n", "application/pdf"))],
    )
    assert response.status_code == 200
    job_id = response.json()["job_id"]

    prepared = client.post(f"/jobs/{job_id}/prepare")
    assert prepared.status_code == 200
    payload = prepared.json()
    assert payload["status"] == "prepared"
    assert [slide["page_number"] for slide in payload["slides"]] == [1, 2]
    assert [slide["source_type"] for slide in payload["slides"]] == ["pdf_page", "pdf_page"]
    assert payload["slides"][0]["image_relpath"].endswith("slide-001.png")
    assert payload["slides"][1]["image_relpath"].endswith("slide-002.png")
