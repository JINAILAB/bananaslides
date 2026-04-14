# CLI Guide

## Overview

`bananaslides` provides both one-shot and step-by-step commands.

One-shot:

```bash
bananaslides run slide.png --output-dir artifacts/slide
```

`run` only accepts a single raster slide image.

Deck build:

```bash
bananaslides deck slide1.png slide2.png slide3.png --output-dir artifacts/deck
```

PDF input is handled through `deck`:

```bash
bananaslides deck slides.pdf --output-dir artifacts/deck
```

The CLI keeps the input order as slide order. For PDFs, page order becomes slide order. The first image or first PDF page size becomes the deck slide size.

Step-by-step:

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

## OCR preset commands

List available presets:

```bash
bananaslides list-ocr-presets
```

Install a preset:

```bash
bananaslides init-models --preset ko-en
```

Switch active preset:

```bash
bananaslides use-ocr-preset ko-en
```

Inspect current config:

```bash
bananaslides show-config
```

## Detection

```bash
bananaslides detect-text slide.png --output-json artifacts/slide/slide.detections.json
```

## OCR

```bash
bananaslides ocr-text \
  slide.png \
  artifacts/slide/slide.detections.json \
  --output-json artifacts/slide/slide.ocr.json
```

## OCR correction

Repair using explicit expected phrases:

```bash
bananaslides repair-ocr \
  artifacts/slide/slide.ocr.json \
  --expected-text "Revenue grew 18%" \
  --expected-text "Gross margin improved"
```

Repair using a deck plan file:

```bash
bananaslides repair-ocr \
  artifacts/slide/slide.ocr.json \
  --deck-plan-file deck-plan.json
```

## Inpainting

```bash
bananaslides inpaint-text \
  slide.png \
  artifacts/slide/slide.detections.json \
  --output-mask artifacts/slide/slide.mask.png \
  --output-background artifacts/slide/slide.background.png
```

## Rendering

Render from existing artifacts:

```bash
bananaslides render-from-artifacts \
  slide.png \
  artifacts/slide/slide.detections.json \
  artifacts/slide/slide.ocr.json \
  artifacts/slide/slide.background.png \
  artifacts/slide/slide.pptx
```

One-shot full pipeline:

```bash
bananaslides run slide.png --output-dir artifacts/slide
```

Multi-slide deck build from images:

```bash
bananaslides deck slide1.png slide2.png slide3.png --output-dir artifacts/deck
```

Deck build from PDF:

```bash
bananaslides deck slides.pdf --output-dir artifacts/deck
```

## Output artifacts

Typical outputs:

- `slide.detections.json`
- `slide.ocr.json`
- `slide.mask.png`
- `slide.background.png`
- `slide.pptx`

For `deck`, the output directory contains per-slide subdirectories plus `deck.pptx`. When the input includes PDFs, rendered page PNGs are stored under `_pdf-pages/`.

## Help

```bash
bananaslides --help
bananaslides run --help
bananaslides repair-ocr --help
```
