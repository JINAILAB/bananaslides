<div align="center">

<img src="docs/assets/bananaslides-logo.png" alt="bananaslides" width="300" />

<br />

English | [한국어](README_ko.md) | [简体中文](README_cn.md)

</div>

# bananaslides

`bananaslides` reconstructs an editable `.pptx` from slide images.

It is built for image-first slide workflows where the visual slide already exists as a PNG or screenshot, but the final deliverable still needs editable text boxes inside PowerPoint.

## 1. What does this do?

Given a slide image, `bananaslides` runs a local restoration pipeline:

- Detect text regions
- Run OCR with local ONNX models
- Optionally correct OCR using expected slide copy
- Remove text from the background image
- Rebuild editable text boxes
- Render a final `.pptx`

This makes it useful for:

- Rebuilding editable slides from generated images
- Repairing rasterized slides into editable PPT
- Automating slide-image to PPT workflows in Python or CLI

## 2. What is included?

- Local OCR with `RapidOCR + ONNX Runtime`
- OCR model preset bootstrap for `PP-OCRv5 mobile`
- Text mask generation and `OpenCV Telea` inpainting
- Paragraph reconstruction and heading/body splitting
- Deck or slide-level font-size normalization
- `python-pptx` based editable PowerPoint rendering
- CLI for step-by-step artifacts or one-shot pipeline runs

## 3. Installation

### 3.1 From source

```bash
git clone <your-repo-url> bananaslides
cd bananaslides
pip install -e .
```

### 3.2 From a built wheel

```bash
python -m build --wheel
pip install dist/bananaslides-0.1.0-py3-none-any.whl
```

### 3.3 Development install

```bash
pip install -e ".[dev]"
```

### 3.4 Web backend install

```bash
pip install -e ".[dev,web]"
```

## 4. First-time setup

OCR models are installed into a local cache. Run this once before your first OCR job:

```bash
bananaslides init-models --preset ko-en
```

Useful checks:

```bash
bananaslides list-ocr-presets
bananaslides show-config
```

Default OCR model cache:

- macOS: `~/Library/Caches/bananaslides/ocr_models`
- Linux: `~/.cache/bananaslides/ocr_models`
- Windows: `%LOCALAPPDATA%\\bananaslides\\ocr_models`

## 5. Quick start

### 5.1 One-shot pipeline for one raster slide image

```bash
bananaslides run slide.png --output-dir artifacts/slide
```

`run` is intentionally image-only. If your source is a PDF, use `deck`.

### 5.2 Multi-slide deck from multiple images or a PDF

```bash
bananaslides deck slide1.png slide2.png slide3.png --output-dir artifacts/deck
```

```bash
bananaslides deck slides.pdf --output-dir artifacts/deck
```

Typical outputs:

```text
artifacts/deck/
  slide-01/
    slide1.detections.json
    slide1.ocr.json
    slide1.mask.png
    slide1.background.png
    slide1.pptx
  slide-02/
    slide2.detections.json
    slide2.ocr.json
    slide2.mask.png
    slide2.background.png
    slide2.pptx
  slide-03/
    slide3.detections.json
    slide3.ocr.json
    slide3.mask.png
    slide3.background.png
    slide3.pptx
  deck.pptx
```

Deck ordering follows the input argument order. For PDFs, page order becomes slide order. The first slide image or first PDF page size becomes the deck slide size.

Typical outputs:

```text
artifacts/slide/
  slide.detections.json
  slide.ocr.json
  slide.mask.png
  slide.background.png
  slide.pptx
```

### 5.3 Step-by-step pipeline

```bash
bananaslides detect-text slide.png
bananaslides ocr-text slide.png artifacts/slide/slide.detections.json
bananaslides inpaint-text slide.png artifacts/slide/slide.detections.json
bananaslides render-from-artifacts \
  slide.png \
  artifacts/slide/slide.detections.json \
  artifacts/slide/slide.ocr.json \
  artifacts/slide/slide.background.png
```

### 5.4 OCR correction with expected copy

```bash
bananaslides repair-ocr \
  artifacts/slide/slide.ocr.json \
  --expected-text "Revenue grew 18%" \
  --expected-text "Gross margin improved"
```

## 6. Command line interface

Main commands:

- `bananaslides show-config`
- `bananaslides list-ocr-presets`
- `bananaslides init-models`
- `bananaslides use-ocr-preset`
- `bananaslides detect-text`
- `bananaslides ocr-text`
- `bananaslides inpaint-text`
- `bananaslides deck`
- `bananaslides repair-ocr`
- `bananaslides render-from-artifacts`
- `bananaslides run`

Input rules:

- `bananaslides run`: one raster slide image
- `bananaslides deck`: one or more raster slide images, one PDF, or a mix of images and PDFs

Help:

```bash
bananaslides --help
bananaslides run --help
```

Detailed command examples live in [docs/cli.md](docs/cli.md).

### 6.1 Web app

The standalone repo also includes a web product with two modes:

- `Auto Mode`: upload -> process -> download
- `Review Mode`: upload -> OCR review -> build PPTX after manual review

Run the web API:

```bash
bananaslides-web-api
```

Run the frontend:

```bash
cd web
npm install
npm run dev
```

The frontend expects the API at `http://127.0.0.1:8000` by default. Override with `VITE_API_BASE_URL` if needed.

The default web job store root is `./bananaslides-web-data`.

The current web UI autosaves review edits as you move through slides, and `Build PPTX` performs the final slide rebuild plus PPTX assembly.

## 7. Documentation

- Installation and environment notes: [docs/installation.md](docs/installation.md)
- CLI usage and examples: [docs/cli.md](docs/cli.md)
- Web app and API usage: [docs/web.md](docs/web.md)
- Pipeline architecture: [docs/architecture.md](docs/architecture.md)
- Current limitations: [docs/limitations.md](docs/limitations.md)

## 8. Technical summary

The default pipeline is:

1. Full-slide text detection
2. RapidOCR-based OCR with local ONNX assets
3. Optional OCR correction from expected text candidates
4. Text mask generation
5. OpenCV Telea background restoration
6. Line-to-paragraph reconstruction
7. Heading/body splitting and font-size normalization
8. Editable `.pptx` rendering with `python-pptx`

Architecture details are in [docs/architecture.md](docs/architecture.md).

## 9. Platform notes

- macOS, Linux, and Windows path handling are implemented for OCR model cache and font lookup.
- The default runtime path is CPU-based `onnxruntime`.
- System font fallback is used when bundled fonts are not present.
- Fresh install and CLI smoke tests were verified on macOS.
- Linux and Windows support is implemented in code, but should still be validated on real machines before release.

## 10. Limitations

- Math is not converted into native PowerPoint equation objects.
- Charts, icons, and decorative graphics usually remain part of the background image.
- OCR quality still depends on text clarity, spacing, and image quality.
- Very dense layouts or complex tables can require manual review.

Details are in [docs/limitations.md](docs/limitations.md).

## 11. Development

Run tests:

```bash
python -m pytest
```

Build a wheel:

```bash
python -m build --wheel
```

Project layout:

```text
api/
web/
src/bananaslides/
src/bananaslides_webapi/
  domain/
  modules/
  pipeline/
  utils/
tests/
docs/
pyproject.toml
README.md
README_ko.md
README_cn.md
```

## License

Apache-2.0. See [LICENSE](LICENSE).
