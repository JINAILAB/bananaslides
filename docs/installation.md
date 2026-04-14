# Installation

## Supported environment

- Python `>=3.11`
- CPU runtime by default
- Tested fresh-install path on macOS
- Linux and Windows path handling is implemented, but release validation should still be done on those OSes directly

## Install from source

```bash
git clone <your-repo-url> bananaslides
cd bananaslides
pip install -e .
```

## Install for development

```bash
pip install -e ".[dev]"
```

## Install from wheel

```bash
python -m build --wheel
pip install dist/bananaslides-0.1.0-py3-none-any.whl
```

## OCR model bootstrap

Install the default OCR preset:

```bash
bananaslides init-models --preset ko-en
```

Check active and installed presets:

```bash
bananaslides list-ocr-presets
bananaslides show-config
```

## OCR model cache locations

- macOS: `~/Library/Caches/bananaslides/ocr_models`
- Linux: `~/.cache/bananaslides/ocr_models`
- Windows: `%LOCALAPPDATA%\\bananaslides\\ocr_models`

## Common setup checks

Check CLI availability:

```bash
bananaslides --help
```

Run a minimal smoke test:

```bash
bananaslides run slide.png --output-dir artifacts/slide
```

Run a PDF smoke test:

```bash
bananaslides deck slides.pdf --output-dir artifacts/deck
```

## Notes

- OCR assets are downloaded into the local cache, not embedded into your slide output directory.
- System fonts are used as fallback if no local font assets are present.
- PDF input support uses `pypdfium2` through the `deck` command. `run` remains raster-image only.
- If you are preparing a public release, validate `init-models -> run` on macOS, Linux, and Windows separately.
