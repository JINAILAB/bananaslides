# Web App

## Overview

The standalone repo now includes a web product on top of the `bananaslides` core.

It supports two modes:

- `Auto Mode`: upload images or PDFs and build the final PPTX directly
- `Review Mode`: upload images or PDFs, inspect OCR boxes slide by slide, then build the final PPTX after manual review

The web product is split into:

- `src/bananaslides_webapi/`: FastAPI backend and file-based job store
- `api/main.py`: thin API entry wrapper
- `web/`: Vite + React + Tailwind frontend

## Supported inputs

The web flow accepts:

- one image
- multiple images
- one PDF
- multiple PDFs
- mixed image and PDF uploads

All uploads are normalized into an ordered slide-image list before OCR and PPT reconstruction.

## Backend setup

Install the backend with web dependencies:

```bash
pip install -e ".[dev,web]"
```

Run the API:

```bash
bananaslides-web-api
```

Default API address:

```text
http://127.0.0.1:8000
```

## Frontend setup

Install frontend dependencies:

```bash
cd web
npm install
```

Run the development server:

```bash
npm run dev
```

Build production assets:

```bash
npm run build
```

Preview the production build:

```bash
npm run preview -- --host 127.0.0.1 --port 4173
```

## Environment

The frontend uses the backend URL below by default:

```text
http://127.0.0.1:8000
```

Override it with:

```bash
VITE_API_BASE_URL=http://127.0.0.1:8000
```

## Job store

The web backend uses a file-based job store rooted at:

```text
./bananaslides-web-data
```

Each job stores:

- raw uploads
- normalized slide images
- slide repair artifacts
- OCR edit specs
- final PPTX export

## API summary

Key endpoints:

- `POST /jobs`
- `POST /jobs/{job_id}/prepare`
- `POST /jobs/{job_id}/process`
- `GET /jobs/{job_id}`
- `GET /jobs/{job_id}/slides/{slide_number}/editor-state`
- `POST /jobs/{job_id}/slides/{slide_number}/editor-save`
- `POST /jobs/{job_id}/slides/{slide_number}/apply`
- `POST /jobs/{job_id}/build-deck`
- `GET /jobs/{job_id}/download`

## Notes

- CLI remains non-interactive. OCR review is web-only.
- `run` is still raster-image only.
- `deck` is still the CLI entry point for images and PDFs.
- The current review UI autosaves editor changes while moving across slides.
- `Build PPTX` is the main user-facing action that rebuilds review artifacts and assembles the final PPTX.
- Review mode still stores manual changes in `slide-XXX.ocr.edits.json`.
