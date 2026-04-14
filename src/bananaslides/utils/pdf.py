from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from bananaslides.domain.models import SlideSize


class PdfRenderError(RuntimeError):
    pass


@dataclass(slots=True)
class RenderedPdfPage:
    source_pdf_path: Path
    page_number: int
    image_path: Path
    slide_size: SlideSize


def is_pdf_path(path: Path) -> bool:
    return path.suffix.lower() == ".pdf"


def render_pdf_pages(pdf_path: Path, output_dir: Path, *, dpi: int = 144) -> list[RenderedPdfPage]:
    if dpi <= 0:
        raise PdfRenderError("PDF DPI must be greater than 0.")
    if not pdf_path.exists():
        raise PdfRenderError(f"PDF not found: {pdf_path}")

    try:
        import pypdfium2 as pdfium
    except ImportError as exc:
        raise PdfRenderError("PDF support requires pypdfium2. Reinstall bananaslides with PDF dependencies available.") from exc

    output_dir.mkdir(parents=True, exist_ok=True)
    scale = dpi / 72.0
    rendered_pages: list[RenderedPdfPage] = []

    try:
        document = pdfium.PdfDocument(str(pdf_path), autoclose=True)
    except Exception as exc:  # pragma: no cover - backend-specific failure surface
        raise PdfRenderError(f"Failed to open PDF: {pdf_path}") from exc

    try:
        for page_index in range(len(document)):
            page = document[page_index]
            image_path = output_dir / f"{pdf_path.stem}-page-{page_index + 1:03d}.png"
            bitmap = page.render(scale=scale, rev_byteorder=True)
            image = bitmap.to_pil()
            image.save(image_path)
            width_px, height_px = image.size
            rendered_pages.append(
                RenderedPdfPage(
                    source_pdf_path=pdf_path,
                    page_number=page_index + 1,
                    image_path=image_path,
                    slide_size=SlideSize(width_px=width_px, height_px=height_px),
                )
            )
            bitmap.close()
            page.close()
    finally:
        document.close()

    if not rendered_pages:
        raise PdfRenderError(f"PDF has no pages: {pdf_path}")
    return rendered_pages
