# Architecture

## Pipeline

The default pipeline is:

1. Detect text regions
2. Run OCR on detected text
3. Optionally repair OCR using expected text candidates
4. Build a text mask
5. Restore a clean background image
6. Convert OCR lines into paragraph placements
7. Normalize font sizes across render placements
8. Render an editable PowerPoint slide

## Core modules

### Detection

- Default detector: full-slide text detection
- Purpose: create text regions that define OCR scope

### OCR

- Backend: `RapidOCR + ONNX Runtime`
- OCR assets are explicit local files resolved from the active preset cache

### OCR correction

- Uses expected phrases from explicit inputs or a deck plan
- Matches OCR output against candidate phrases and rewrites low-quality OCR to known slide copy

### Inpainting

- Builds masks from text geometry
- Uses `OpenCV Telea` to reconstruct the clean background

### Typesetting

- Reconstructs line groups into paragraphs
- Splits heading/body where needed
- Normalizes font sizes so similar roles use similar tokens

### PPT rendering

- Uses `python-pptx`
- Places the restored background image first
- Adds editable text boxes on top

## Artifact flow

```text
slide.png
  -> detections.json
  -> ocr.json
  -> mask.png
  -> background.png
  -> slide.pptx
```

## Design assumptions

- Raster slide visuals already exist
- Text is the main editable target
- Background graphics are usually preserved as image content
- OCR can be improved by expected-copy correction

## Non-goals

- Native chart reconstruction
- Native PowerPoint equation object generation
- Full semantic understanding of arbitrary slide layouts
