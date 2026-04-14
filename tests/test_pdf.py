from __future__ import annotations

from pathlib import Path

from PIL import Image

from bananaslides.utils.pdf import is_pdf_path, render_pdf_pages


def test_is_pdf_path_is_case_insensitive() -> None:
    assert is_pdf_path(Path("slides.PDF")) is True
    assert is_pdf_path(Path("slides.png")) is False


def test_render_pdf_pages_rasterizes_pdf_into_pngs(tmp_path: Path) -> None:
    pdf_path = tmp_path / "sample.pdf"
    output_dir = tmp_path / "rendered"

    source = Image.new("RGB", (240, 160), "white")
    source.save(pdf_path, "PDF", resolution=72)

    rendered_pages = render_pdf_pages(pdf_path, output_dir, dpi=144)

    assert len(rendered_pages) == 1
    page = rendered_pages[0]
    assert page.page_number == 1
    assert page.image_path.exists()
    assert page.image_path.suffix == ".png"
    assert page.slide_size.width_px > 0
    assert page.slide_size.height_px > 0
