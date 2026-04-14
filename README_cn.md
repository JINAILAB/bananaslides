<div align="center">

<img src="docs/assets/bananaslides-logo.png" alt="bananaslides" width="300" />

<br />

[English](README.md) | [한국어](README_ko.md) | 简体中文

</div>

# bananaslides

`bananaslides` 用于从幻灯片图片重建可编辑的 `.pptx`。

它适合这样的场景：视觉稿已经是 PNG、截图或其他图片形式，但最终交付物仍然需要在 PowerPoint 中可编辑的文本框。

## 1. 这个项目做什么？

给定一张幻灯片图片，`bananaslides` 会执行以下本地恢复流程：

- 检测文本区域
- 使用本地 ONNX 模型执行 OCR
- 在需要时使用预期文案修正 OCR
- 从背景图中移除文本
- 重建可编辑文本框
- 渲染最终 `.pptx`

适用场景包括：

- 将生成式图片恢复成可编辑幻灯片
- 将栅格化幻灯片修复为可编辑 PPT
- 在 Python 或 CLI 中自动化图片幻灯片到 PPT 的流程

## 2. 包含哪些能力？

- 基于 `RapidOCR + ONNX Runtime` 的本地 OCR
- `PP-OCRv5 mobile` OCR 预设初始化
- 基于 `OpenCV Telea` 的文本掩码与 inpainting
- 段落重建与标题/正文拆分
- 按幻灯片或整套文档进行字号归一化
- 基于 `python-pptx` 的可编辑 PowerPoint 渲染
- 支持分步产物和一键流程的 CLI

## 3. 安装

### 3.1 从源码安装

```bash
git clone <your-repo-url> bananaslides
cd bananaslides
pip install -e .
```

### 3.2 安装构建好的 wheel

```bash
python -m build --wheel
pip install dist/bananaslides-0.1.0-py3-none-any.whl
```

### 3.3 开发环境安装

```bash
pip install -e ".[dev]"
```

### 3.4 Web 后端安装

```bash
pip install -e ".[dev,web]"
```

## 4. 首次使用前的准备

OCR 模型会安装到本地缓存目录。首次运行 OCR 前请先执行一次：

```bash
bananaslides init-models --preset ko-en
```

常用检查命令：

```bash
bananaslides list-ocr-presets
bananaslides show-config
```

默认 OCR 模型缓存位置：

- macOS: `~/Library/Caches/bananaslides/ocr_models`
- Linux: `~/.cache/bananaslides/ocr_models`
- Windows: `%LOCALAPPDATA%\\bananaslides\\ocr_models`

## 5. 快速开始

### 5.1 对单张栅格幻灯片进行一键处理

```bash
bananaslides run slide.png --output-dir artifacts/slide
```

`run` 只接受图片输入。如果源文件是 PDF，请使用 `deck` 命令。

### 5.2 从多张图片或 PDF 构建多页 PPTX

```bash
bananaslides deck slide1.png slide2.png slide3.png --output-dir artifacts/deck
```

```bash
bananaslides deck slides.pdf --output-dir artifacts/deck
```

典型输出：

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

幻灯片顺序遵循输入参数顺序。对于 PDF，页码顺序会转换为幻灯片顺序。第一张图片或 PDF 第一页的尺寸会成为整套文档的幻灯片尺寸。

单页输出示例：

```text
artifacts/slide/
  slide.detections.json
  slide.ocr.json
  slide.mask.png
  slide.background.png
  slide.pptx
```

### 5.3 分步执行管线

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

### 5.4 使用预期文案修正 OCR

```bash
bananaslides repair-ocr \
  artifacts/slide/slide.ocr.json \
  --expected-text "Revenue grew 18%" \
  --expected-text "Gross margin improved"
```

## 6. 命令行接口

主要命令：

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

输入规则：

- `bananaslides run`：单张栅格幻灯片图片
- `bananaslides deck`：一张或多张栅格图片、单个 PDF，或图片与 PDF 混合输入

帮助命令：

```bash
bananaslides --help
bananaslides run --help
```

详细命令示例见 [docs/cli.md](docs/cli.md)。

### 6.1 Web 应用

仓库中还包含一套 Web 产品：

- `Auto Mode`：上传 -> 处理 -> 下载
- `Review Mode`：上传 -> OCR 审核 -> 人工校对后构建 PPTX

启动 Web API：

```bash
bananaslides-web-api
```

启动前端：

```bash
cd web
npm install
npm run dev
```

前端默认访问 `http://127.0.0.1:8000`。如有需要，可通过 `VITE_API_BASE_URL` 覆盖。

默认 Web job store 根目录为 `./bananaslides-web-data`。

当前 Web UI 会在切换幻灯片时自动保存审核编辑内容，而 `Build PPTX` 会执行最终的幻灯片重建与 PPTX 组装。

## 7. 文档

- 安装与环境说明：[docs/installation.md](docs/installation.md)
- CLI 使用与示例：[docs/cli.md](docs/cli.md)
- Web 应用与 API：[docs/web.md](docs/web.md)
- 管线架构：[docs/architecture.md](docs/architecture.md)
- 当前限制：[docs/limitations.md](docs/limitations.md)

## 8. 技术概览

默认处理流程：

1. 全页文本检测
2. 使用本地 ONNX 资源执行 RapidOCR
3. 根据预期文案候选修正 OCR
4. 生成文本掩码
5. 使用 OpenCV Telea 恢复背景
6. 将 OCR 行重建为段落布局
7. 进行标题/正文拆分与字号归一化
8. 基于 `python-pptx` 渲染可编辑 `.pptx`

更多架构细节请见 [docs/architecture.md](docs/architecture.md)。

## 9. 平台说明

- 已实现 macOS、Linux、Windows 的 OCR 缓存与字体路径处理。
- 默认运行时为 CPU 版 `onnxruntime`。
- 如果没有本地字体资源，会回退到系统字体。
- 已在 macOS 上验证 fresh install 与 CLI smoke test。
- Linux 与 Windows 的代码路径已实现，但正式发布前仍建议单独验证。

## 10. 限制

- 数学公式不会转换为 PowerPoint 原生公式对象。
- 图表、图标和装饰性图形通常仍会保留在背景图片中。
- OCR 质量仍然依赖文本清晰度、间距和图片质量。
- 对于非常密集的版式或复杂表格，仍可能需要人工审核。

详情请参见 [docs/limitations.md](docs/limitations.md)。

## 11. 开发

运行测试：

```bash
python -m pytest
```

构建 wheel：

```bash
python -m build --wheel
```

项目结构：

```text
api/
web/
src/bananaslides/
src/bananaslides_webapi/
tests/
docs/
pyproject.toml
README.md
README_ko.md
README_cn.md
```

## License

Apache-2.0. 详见 [LICENSE](LICENSE)。
