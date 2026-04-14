# Limitations

## Current limitations

### Math and equations

- OCR is general text OCR
- Equations are not converted into native PowerPoint equation objects
- Structured outputs such as LaTeX, MathML, or OMML are not produced by default

### Graphics

- Charts, icons, decorative shapes, and complex diagrams usually remain embedded in the background image
- The package focuses on editable text reconstruction, not full object reconstruction

### OCR quality

- Small text, low-contrast text, curved text, and compressed images can degrade OCR quality
- Dense infographics and heavily stylized slides can require manual review

### Layout complexity

- Complex tables and nonstandard multi-column layouts can still produce imperfect paragraph grouping
- Typesetting is heuristic-driven, not a learned layout model

### Fonts

- Font family fallback depends on what is available on the target system
- Visual fidelity can vary across macOS, Linux, and Windows if the same font assets are not installed

## Recommended workflow

- Treat `bananaslides` as a text-restoration engine
- Review final slides when layout is dense or highly designed
- Use OCR correction whenever expected slide copy is known
- Validate rendering on the target platform before shipping a release
