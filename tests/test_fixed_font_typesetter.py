from pathlib import Path

from PIL import Image, ImageDraw

import bananaslides.modules.typesetting.fixed_font_typesetter as fixed_font_typesetter_module
from bananaslides.config import FontPolicy
from bananaslides.domain.models import DetectionBox, ElementCategory, OCRLine, OCRResult
from bananaslides.modules.typesetting.fixed_font_typesetter import FixedFontTypesetter


def test_korean_text_uses_pretendard() -> None:
    typesetter = FixedFontTypesetter(FontPolicy(korean_font="Pretendard", latin_font="Pretendard"))
    detections = [
        DetectionBox(
            box_id="t1",
            category=ElementCategory.TEXT,
            x=10,
            y=10,
            width=200,
            height=40,
        )
    ]
    ocr_results = [OCRResult(box_id="t1", text="안녕하세요", lines=[OCRLine(text="안녕하세요")])]

    placements = typesetter.build_text_placements(detections, ocr_results)

    assert placements[0].font_name == "Pretendard"


def test_latin_text_uses_latin_font() -> None:
    typesetter = FixedFontTypesetter(FontPolicy(korean_font="Pretendard", latin_font="Pretendard"))
    detections = [
        DetectionBox(
            box_id="t2",
            category=ElementCategory.TEXT,
            x=10,
            y=10,
            width=200,
            height=40,
        )
    ]
    ocr_results = [OCRResult(box_id="t2", text="hello world")]

    placements = typesetter.build_text_placements(detections, ocr_results)

    assert placements[0].font_name == "Pretendard"
    assert placements[0].font_size_pt >= 10.0


def test_ocr_rows_with_similar_font_size_are_grouped_into_multiline_paragraph() -> None:
    typesetter = FixedFontTypesetter(FontPolicy(korean_font="Pretendard", latin_font="Pretendard"))
    detections = [
        DetectionBox(
            box_id="t3",
            category=ElementCategory.TEXT,
            x=100,
            y=100,
            width=600,
            height=160,
        )
    ]
    ocr_results = [
        OCRResult(
            box_id="t3",
            text="Accelerating\nGrowth, Key Metrics\n& Strategic\nOutlook",
            lines=[
                OCRLine(
                    text="Growth, Key Metrics",
                    bbox=[[280.0, 100.0], [560.0, 100.0], [560.0, 138.0], [280.0, 138.0]],
                ),
                OCRLine(
                    text="Accelerating",
                    bbox=[[100.0, 101.0], [260.0, 101.0], [260.0, 140.0], [100.0, 140.0]],
                ),
                OCRLine(
                    text="Outlook",
                    bbox=[[240.0, 148.0], [360.0, 148.0], [360.0, 186.0], [240.0, 186.0]],
                ),
                OCRLine(
                    text="& Strategic",
                    bbox=[[100.0, 146.0], [220.0, 146.0], [220.0, 187.0], [100.0, 187.0]],
                ),
            ],
        )
    ]

    placements = typesetter.build_text_placements(detections, ocr_results)

    assert len(placements) == 1
    assert placements[0].text == "Accelerating Growth, Key Metrics\n& Strategic Outlook"
    assert all(not placement.word_wrap for placement in placements)


def test_same_row_segments_with_large_font_size_difference_are_not_grouped() -> None:
    typesetter = FixedFontTypesetter(FontPolicy(korean_font="Pretendard", latin_font="Pretendard"))
    detections = [
        DetectionBox(
            box_id="t3b",
            category=ElementCategory.TEXT,
            x=100,
            y=100,
            width=500,
            height=120,
        )
    ]
    ocr_results = [
        OCRResult(
            box_id="t3b",
            text="Revenue 2025",
            lines=[
                OCRLine(
                    text="Revenue",
                    bbox=[[100.0, 100.0], [240.0, 100.0], [240.0, 138.0], [100.0, 138.0]],
                ),
                OCRLine(
                    text="2025",
                    bbox=[[252.0, 92.0], [330.0, 92.0], [330.0, 148.0], [252.0, 148.0]],
                ),
            ],
        )
    ]

    placements = typesetter.build_text_placements(detections, ocr_results)

    assert [placement.text for placement in placements] == ["Revenue", "2025"]


def test_rows_with_large_font_size_difference_start_new_paragraph() -> None:
    typesetter = FixedFontTypesetter(FontPolicy(korean_font="Pretendard", latin_font="Pretendard"))
    detections = [
        DetectionBox(
            box_id="t3c",
            category=ElementCategory.TEXT,
            x=80,
            y=80,
            width=640,
            height=220,
        )
    ]
    ocr_results = [
        OCRResult(
            box_id="t3c",
            text="Market Expansion\nNorth America",
            lines=[
                OCRLine(
                    text="Market Expansion",
                    bbox=[[90.0, 90.0], [360.0, 90.0], [360.0, 126.0], [90.0, 126.0]],
                ),
                OCRLine(
                    text="North America",
                    bbox=[[92.0, 144.0], [332.0, 144.0], [332.0, 198.0], [92.0, 198.0]],
                ),
            ],
        )
    ]

    placements = typesetter.build_text_placements(detections, ocr_results)

    assert [placement.text for placement in placements] == ["Market Expansion", "North America"]


def test_paragraph_merge_allows_small_ocr_height_drift_within_same_column() -> None:
    typesetter = FixedFontTypesetter(FontPolicy(korean_font="Pretendard", latin_font="Pretendard"))
    detections = [
        DetectionBox(
            box_id="t3c2",
            category=ElementCategory.TEXT,
            x=90,
            y=1240,
            width=480,
            height=220,
        )
    ]
    ocr_results = [
        OCRResult(
            box_id="t3c2",
            text="스토리라인,카피,스타일,\n근거(grounding)를JSON\n파일로 구체화하여 정의한다.",
            lines=[
                OCRLine(
                    text="스토리라인,카피,스타일,",
                    bbox=[[126.2, 1260.3], [522.9, 1260.3], [522.9, 1317.9], [126.2, 1317.9]],
                ),
                OCRLine(
                    text="근거(grounding)를JSON",
                    bbox=[[115.1, 1309.7], [535.4, 1309.7], [535.4, 1367.3], [115.1, 1367.3]],
                ),
                OCRLine(
                    text="파일로 구체화하여 정의한다.",
                    bbox=[[106.8, 1360.5], [547.9, 1360.5], [547.9, 1409.8], [106.8, 1409.8]],
                ),
            ],
        )
    ]

    placements = typesetter.build_text_placements(detections, ocr_results)

    assert [placement.text for placement in placements] == [
        "스토리라인,카피,스타일,\n근거(grounding)를JSON\n파일로 구체화하여 정의한다."
    ]


def test_paragraph_merge_allows_borderline_height_drift_for_four_line_column() -> None:
    typesetter = FixedFontTypesetter(FontPolicy(korean_font="Pretendard", latin_font="Pretendard"))
    detections = [
        DetectionBox(
            box_id="t3c3",
            category=ElementCategory.TEXT,
            x=2140,
            y=1240,
            width=540,
            height=240,
        )
    ]
    ocr_results = [
        OCRResult(
            box_id="t3c3",
            text="복원된 깨끗한 배경 이미지 위에\nOCR로 추출한 텍스트를 다시\n배치하여 최종\nPowerPoint 파일을 생성한다.",
            lines=[
                OCRLine(
                    text="복원된 깨끗한 배경 이미지 위에",
                    bbox=[[2177.7, 1263.1], [2659.1, 1263.1], [2659.1, 1315.2], [2177.7, 1315.2]],
                ),
                OCRLine(
                    text="OCR로 추출한 텍스트를 다시",
                    bbox=[[2194.4, 1315.2], [2641.0, 1315.2], [2641.0, 1360.5], [2194.4, 1360.5]],
                ),
                OCRLine(
                    text="배치하여 최종",
                    bbox=[[2305.4, 1357.7], [2528.7, 1357.7], [2528.7, 1412.6], [2305.4, 1412.6]],
                ),
                OCRLine(
                    text="PowerPoint 파일을 생성한다.",
                    bbox=[[2179.1, 1408.5], [2648.0, 1408.5], [2648.0, 1457.8], [2179.1, 1457.8]],
                ),
            ],
        )
    ]

    placements = typesetter.build_text_placements(detections, ocr_results)

    assert [placement.text for placement in placements] == [
        "복원된 깨끗한 배경 이미지 위에\nOCR로 추출한 텍스트를 다시\n배치하여 최종\nPowerPoint 파일을 생성한다."
    ]


def test_heading_like_first_row_splits_from_consistent_body_cluster() -> None:
    typesetter = FixedFontTypesetter(FontPolicy(korean_font="Pretendard", latin_font="Pretendard"))
    detections = [
        DetectionBox(
            box_id="t3c4",
            category=ElementCategory.TEXT,
            x=1120,
            y=1180,
            width=500,
            height=320,
        )
    ]
    ocr_results = [
        OCRResult(
            box_id="t3c4",
            text="RapidOCR + ONNX 엔진\n이미지 내의 텍스트를 로컬\n환경에서 RapidOCR와\nPP-OCRv5 mobile 모델을\n이용해 정밀하게 인식한다.",
            lines=[
                OCRLine(
                    text="RapidOCR + ONNX 엔진",
                    bbox=[[1141.6, 1190.4], [1591.0, 1190.4], [1591.0, 1252.1], [1141.6, 1252.1]],
                ),
                OCRLine(
                    text="이미지 내의 텍스트를 로컬",
                    bbox=[[1162.4, 1264.5], [1567.4, 1264.5], [1567.4, 1315.2], [1162.4, 1315.2]],
                ),
                OCRLine(
                    text="환경에서 RapidOCR와",
                    bbox=[[1184.6, 1313.8], [1543.9, 1313.8], [1543.9, 1364.5], [1184.6, 1364.5]],
                ),
                OCRLine(
                    text="PP-OCRv5 mobile 모델을",
                    bbox=[[1158.2, 1363.2], [1571.6, 1363.2], [1571.6, 1408.5], [1158.2, 1408.5]],
                ),
                OCRLine(
                    text="이용해 정밀하게 인식한다.",
                    bbox=[[1162.4, 1408.5], [1567.4, 1408.5], [1567.4, 1457.8], [1162.4, 1457.8]],
                ),
            ],
        )
    ]

    placements = typesetter.build_text_placements(detections, ocr_results)

    assert [placement.text for placement in placements] == [
        "RapidOCR + ONNX 엔진",
        "이미지 내의 텍스트를 로컬\n환경에서 RapidOCR와\nPP-OCRv5 mobile 모델을\n이용해 정밀하게 인식한다.",
    ]


def test_rows_with_large_left_offset_stay_in_same_paragraph_under_relaxed_threshold() -> None:
    typesetter = FixedFontTypesetter(FontPolicy(korean_font="Pretendard", latin_font="Pretendard"))
    detections = [
        DetectionBox(
            box_id="t3d",
            category=ElementCategory.TEXT,
            x=80,
            y=80,
            width=640,
            height=220,
        )
    ]
    ocr_results = [
        OCRResult(
            box_id="t3d",
            text="Platform Overview\nManual OCR Hint",
            lines=[
                OCRLine(
                    text="Platform Overview",
                    bbox=[[90.0, 90.0], [350.0, 90.0], [350.0, 130.0], [90.0, 130.0]],
                ),
                OCRLine(
                    text="Manual OCR Hint",
                    bbox=[[210.0, 138.0], [410.0, 138.0], [410.0, 178.0], [210.0, 178.0]],
                ),
            ],
        )
    ]

    placements = typesetter.build_text_placements(detections, ocr_results)

    assert [placement.text for placement in placements] == ["Platform Overview\nManual OCR Hint"]


def test_title_and_subtitle_with_large_vertical_gap_start_new_paragraphs() -> None:
    typesetter = FixedFontTypesetter(FontPolicy(korean_font="Pretendard", latin_font="Pretendard"))
    detections = [
        DetectionBox(
            box_id="t3e",
            category=ElementCategory.TEXT,
            x=600,
            y=1080,
            width=500,
            height=220,
        )
    ]
    ocr_results = [
        OCRResult(
            box_id="t3e",
            text="슬라이드 이미지 생성\nGemini+템플릿 렌더링",
            lines=[
                OCRLine(
                    text="슬라이드 이미지 생성",
                    bbox=[[634.0, 1104.0], [1060.0, 1104.0], [1060.0, 1168.5], [634.0, 1168.5]],
                ),
                OCRLine(
                    text="Gemini+템플릿 렌더링",
                    bbox=[[632.5, 1190.4], [1061.1, 1190.4], [1061.1, 1249.4], [632.5, 1249.4]],
                ),
            ],
        )
    ]

    placements = typesetter.build_text_placements(detections, ocr_results)

    assert [placement.text for placement in placements] == [
        "슬라이드 이미지 생성",
        "Gemini+템플릿 렌더링",
    ]


def test_paragraph_placement_keeps_original_rect_origin(tmp_path: Path, monkeypatch) -> None:
    source_path = tmp_path / "source-origin.png"
    background_path = tmp_path / "background-origin.png"
    Image.new("RGB", (320, 200), (255, 255, 255)).save(source_path)
    Image.new("RGB", (320, 200), (255, 255, 255)).save(background_path)

    typesetter = FixedFontTypesetter(FontPolicy(korean_font="Pretendard", latin_font="Pretendard"))

    def _fake_fit_block_text(*args, **kwargs):
        return 24.0, fixed_font_typesetter_module._MeasuredText(6.0, 5.0, 160.0, 44.0)

    monkeypatch.setattr(typesetter, "_fit_block_text", _fake_fit_block_text)
    monkeypatch.setattr(typesetter, "_resolve_font_file", lambda *args, **kwargs: None)

    detections = [
        DetectionBox(
            box_id="t3f",
            category=ElementCategory.TEXT,
            x=80,
            y=80,
            width=220,
            height=120,
        )
    ]
    ocr_results = [
        OCRResult(
            box_id="t3f",
            text="구조화된 계획 수립\ndeck-plan.json 생성",
            lines=[
                OCRLine(
                    text="구조화된 계획 수립",
                    bbox=[[90.0, 100.0], [260.0, 100.0], [260.0, 140.0], [90.0, 140.0]],
                ),
                OCRLine(
                    text="deck-plan.json 생성",
                    bbox=[[90.0, 148.0], [250.0, 148.0], [250.0, 186.0], [90.0, 186.0]],
                ),
            ],
        )
    ]

    placements = typesetter.build_text_placements(
        detections,
        ocr_results,
        source_image_path=source_path,
        background_image_path=background_path,
    )

    assert placements[0].x == 90.0
    assert placements[0].y == 100.0


def test_text_color_is_extracted_from_source_background_difference(tmp_path: Path) -> None:
    source_path = tmp_path / "source.png"
    background_path = tmp_path / "background.png"

    background = Image.new("RGB", (240, 120), (255, 255, 255))
    background.save(background_path)

    source = background.copy()
    draw = ImageDraw.Draw(source)
    draw.rectangle((40, 30, 180, 74), fill=(20, 58, 90))
    source.save(source_path)

    typesetter = FixedFontTypesetter(FontPolicy(korean_font="Pretendard", latin_font="Pretendard"))
    detections = [
        DetectionBox(
            box_id="t4",
            category=ElementCategory.TEXT,
            x=20,
            y=16,
            width=180,
            height=72,
        )
    ]
    ocr_results = [
        OCRResult(
            box_id="t4",
            text="Executive Title",
            lines=[
                OCRLine(
                    text="Executive Title",
                    bbox=[[20.0, 16.0], [200.0, 16.0], [200.0, 88.0], [20.0, 88.0]],
                )
            ],
        )
    ]

    placements = typesetter.build_text_placements(
        detections,
        ocr_results,
        source_image_path=source_path,
        background_image_path=background_path,
    )

    color = placements[0].color.as_tuple()
    assert abs(color[0] - 20) <= 20
    assert abs(color[1] - 58) <= 20
    assert abs(color[2] - 90) <= 20


def test_text_color_is_snapped_to_slide_palette(tmp_path: Path) -> None:
    source_path = tmp_path / "source-palette.png"
    background_path = tmp_path / "background-palette.png"

    background = Image.new("RGB", (300, 120), (255, 255, 255))
    background.save(background_path)

    source = background.copy()
    draw = ImageDraw.Draw(source)
    draw.rectangle((20, 24, 110, 82), fill=(18, 58, 90))
    draw.rectangle((160, 24, 250, 82), fill=(26, 66, 98))
    source.save(source_path)

    typesetter = FixedFontTypesetter(FontPolicy(korean_font="Pretendard", latin_font="Pretendard"))
    detections = [
        DetectionBox(
            box_id="t5",
            category=ElementCategory.TEXT,
            x=10,
            y=16,
            width=110,
            height=72,
        ),
        DetectionBox(
            box_id="t6",
            category=ElementCategory.TEXT,
            x=150,
            y=16,
            width=110,
            height=72,
        ),
    ]
    ocr_results = [
        OCRResult(
            box_id="t5",
            text="Left",
            lines=[OCRLine(text="Left", bbox=[[10.0, 16.0], [120.0, 16.0], [120.0, 88.0], [10.0, 88.0]])],
        ),
        OCRResult(
            box_id="t6",
            text="Right",
            lines=[OCRLine(text="Right", bbox=[[150.0, 16.0], [260.0, 16.0], [260.0, 88.0], [150.0, 88.0]])],
        ),
    ]

    placements = typesetter.build_text_placements(
        detections,
        ocr_results,
        source_image_path=source_path,
        background_image_path=background_path,
    )

    assert placements[0].color.as_tuple() == placements[1].color.as_tuple()
    color = placements[0].color.as_tuple()
    assert abs(color[0] - 22) <= 8
    assert abs(color[1] - 62) <= 8
    assert abs(color[2] - 94) <= 8


def test_text_color_prefers_line_region_over_paragraph_rect_noise(tmp_path: Path) -> None:
    source_path = tmp_path / "source-line-region.png"
    background_path = tmp_path / "background-line-region.png"

    background = Image.new("RGB", (260, 140), (255, 255, 255))
    background.save(background_path)

    source = background.copy()
    draw = ImageDraw.Draw(source)
    draw.rectangle((10, 20, 210, 100), fill=(32, 32, 32))
    draw.rectangle((50, 40, 120, 78), fill=(18, 58, 90))
    source.save(source_path)

    typesetter = FixedFontTypesetter(FontPolicy(korean_font="Pretendard", latin_font="Pretendard"))
    detections = [
        DetectionBox(
            box_id="t7",
            category=ElementCategory.TEXT,
            x=10,
            y=20,
            width=200,
            height=80,
        )
    ]
    ocr_results = [
        OCRResult(
            box_id="t7",
            text="Label",
            lines=[
                OCRLine(
                    text="Label",
                    bbox=[[50.0, 40.0], [120.0, 40.0], [120.0, 78.0], [50.0, 78.0]],
                )
            ],
        )
    ]

    placements = typesetter.build_text_placements(
        detections,
        ocr_results,
        source_image_path=source_path,
        background_image_path=background_path,
    )

    color = placements[0].color.as_tuple()
    assert abs(color[0] - 18) <= 8
    assert abs(color[1] - 58) <= 8
    assert abs(color[2] - 90) <= 8


def test_text_color_keeps_distinct_palette_clusters_separate(tmp_path: Path) -> None:
    source_path = tmp_path / "source-two-clusters.png"
    background_path = tmp_path / "background-two-clusters.png"

    background = Image.new("RGB", (420, 140), (255, 255, 255))
    background.save(background_path)

    source = background.copy()
    draw = ImageDraw.Draw(source)
    draw.rectangle((20, 24, 110, 82), fill=(18, 58, 90))
    draw.rectangle((150, 24, 240, 82), fill=(26, 66, 98))
    draw.rectangle((280, 24, 370, 82), fill=(190, 92, 20))
    source.save(source_path)

    typesetter = FixedFontTypesetter(FontPolicy(korean_font="Pretendard", latin_font="Pretendard"))
    detections = [
        DetectionBox(box_id="t8", category=ElementCategory.TEXT, x=10, y=16, width=110, height=72),
        DetectionBox(box_id="t9", category=ElementCategory.TEXT, x=140, y=16, width=110, height=72),
        DetectionBox(box_id="t10", category=ElementCategory.TEXT, x=270, y=16, width=110, height=72),
    ]
    ocr_results = [
        OCRResult(box_id="t8", text="Blue A", lines=[OCRLine(text="Blue A", bbox=[[10.0, 16.0], [120.0, 16.0], [120.0, 88.0], [10.0, 88.0]])]),
        OCRResult(box_id="t9", text="Blue B", lines=[OCRLine(text="Blue B", bbox=[[140.0, 16.0], [250.0, 16.0], [250.0, 88.0], [140.0, 88.0]])]),
        OCRResult(box_id="t10", text="Orange", lines=[OCRLine(text="Orange", bbox=[[270.0, 16.0], [380.0, 16.0], [380.0, 88.0], [270.0, 88.0]])]),
    ]

    placements = typesetter.build_text_placements(
        detections,
        ocr_results,
        source_image_path=source_path,
        background_image_path=background_path,
    )

    assert placements[0].color.as_tuple() == placements[1].color.as_tuple()
    assert placements[0].color.as_tuple() != placements[2].color.as_tuple()


def test_platform_font_directories_include_linux_defaults() -> None:
    home = Path("/tmp/test-home")

    directories = FixedFontTypesetter._platform_font_directories(
        "linux",
        home,
        {"XDG_DATA_HOME": str(home / ".xdg")},
    )

    assert Path("/usr/share/fonts") in directories
    assert Path("/usr/local/share/fonts") in directories
    assert home / ".local" / "share" / "fonts" in directories
    assert home / ".fonts" in directories
    assert home / ".xdg" / "fonts" in directories


def test_platform_font_directories_preserve_macos_defaults() -> None:
    home = Path("/tmp/test-home")

    directories = FixedFontTypesetter._platform_font_directories("darwin", home, {})

    assert Path("/Library/Fonts") in directories
    assert Path("/System/Library/Fonts") in directories
    assert home / "Library" / "Fonts" in directories
    assert home / ".fonts" in directories


def test_platform_font_directories_include_windows_defaults() -> None:
    home = Path("/tmp/test-home")

    directories = FixedFontTypesetter._platform_font_directories(
        "win32",
        home,
        {
            "WINDIR": "C:/Windows",
            "LOCALAPPDATA": str(home / "Local"),
            "APPDATA": str(home / "Roaming"),
        },
    )

    assert Path("C:/Windows") / "Fonts" in directories
    assert home / "Local" / "Microsoft" / "Windows" / "Fonts" in directories
    assert home / "Roaming" / "Microsoft" / "Windows" / "Fonts" in directories


def test_try_find_font_file_falls_back_to_directory_scan_when_fontfiles_lookup_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    font_dir = tmp_path / "fonts"
    font_dir.mkdir()
    font_file = font_dir / "Pretendard-Regular.ttf"
    font_file.write_bytes(b"")

    class _FailingFontFiles:
        @staticmethod
        def find(*args, **kwargs) -> str:
            raise OSError("unsupported operating system")

    monkeypatch.setattr(fixed_font_typesetter_module, "FontFiles", _FailingFontFiles)
    monkeypatch.setattr(
        FixedFontTypesetter,
        "_font_directories",
        classmethod(lambda cls: (font_dir,)),
    )

    typesetter = FixedFontTypesetter(FontPolicy(korean_font="Pretendard", latin_font="Pretendard"))

    assert typesetter._try_find_font_file("Pretendard") == str(font_file)


def test_far_apart_same_row_segments_are_not_grouped() -> None:
    typesetter = FixedFontTypesetter(FontPolicy(korean_font="Pretendard", latin_font="Pretendard"))
    detections = [
        DetectionBox(
            box_id="t7",
            category=ElementCategory.TEXT,
            x=0,
            y=0,
            width=1200,
            height=800,
        )
    ]
    ocr_results = [
        OCRResult(
            box_id="t7",
            text="",
            lines=[
                OCRLine(
                    text="Single Optical Sensor",
                    bbox=[[60.0, 120.0], [280.0, 120.0], [280.0, 164.0], [60.0, 164.0]],
                ),
                OCRLine(
                    text="Pulse Wave -> Features",
                    bbox=[[380.0, 122.0], [650.0, 122.0], [650.0, 166.0], [380.0, 166.0]],
                ),
                OCRLine(
                    text="BP Estimate",
                    bbox=[[760.0, 120.0], [930.0, 120.0], [930.0, 164.0], [760.0, 164.0]],
                ),
            ],
        )
    ]

    placements = typesetter.build_text_placements(detections, ocr_results)

    assert [placement.text for placement in placements] == [
        "Single Optical Sensor",
        "Pulse Wave -> Features",
        "BP Estimate",
    ]


def test_interleaved_multi_column_rows_join_with_matching_column_cluster() -> None:
    typesetter = FixedFontTypesetter(FontPolicy(korean_font="Pretendard", latin_font="Pretendard"))
    detections = [
        DetectionBox(
            box_id="t8",
            category=ElementCategory.TEXT,
            x=0,
            y=0,
            width=1800,
            height=1200,
        )
    ]
    ocr_results = [
        OCRResult(
            box_id="t8",
            text="",
            lines=[
                OCRLine(
                    text="Column One Intro",
                    bbox=[[80.0, 100.0], [340.0, 100.0], [340.0, 146.0], [80.0, 146.0]],
                ),
                OCRLine(
                    text="Template-aligned slide image",
                    bbox=[[620.0, 100.0], [1070.0, 100.0], [1070.0, 148.0], [620.0, 148.0]],
                ),
                OCRLine(
                    text="Column Three Intro",
                    bbox=[[1220.0, 102.0], [1510.0, 102.0], [1510.0, 148.0], [1220.0, 148.0]],
                ),
                OCRLine(
                    text="Column One Detail",
                    bbox=[[80.0, 152.0], [332.0, 152.0], [332.0, 198.0], [80.0, 198.0]],
                ),
                OCRLine(
                    text="is generated.",
                    bbox=[[760.0, 150.0], [940.0, 150.0], [940.0, 198.0], [760.0, 198.0]],
                ),
                OCRLine(
                    text="Column Three Detail",
                    bbox=[[1220.0, 154.0], [1526.0, 154.0], [1526.0, 200.0], [1220.0, 200.0]],
                ),
            ],
        )
    ]

    placements = typesetter.build_text_placements(detections, ocr_results)

    assert [placement.text for placement in placements] == [
        "Column One Intro\nColumn One Detail",
        "Template-aligned slide image\nis generated.",
        "Column Three Intro\nColumn Three Detail",
    ]


def test_same_column_rows_merge_even_when_input_order_is_scrambled() -> None:
    typesetter = FixedFontTypesetter(FontPolicy(korean_font="Pretendard", latin_font="Pretendard"))
    detections = [
        DetectionBox(
            box_id="t9",
            category=ElementCategory.TEXT,
            x=1080,
            y=1220,
            width=520,
            height=280,
        )
    ]
    ocr_results = [
        OCRResult(
            box_id="t9",
            text="",
            lines=[
                OCRLine(
                    text="PP-OCRv5 mobile 모델을",
                    bbox=[[1158.2, 1363.2], [1571.6, 1363.2], [1571.6, 1408.5], [1158.2, 1408.5]],
                ),
                OCRLine(
                    text="이미지 내의 텍스트를 로컬",
                    bbox=[[1162.4, 1264.5], [1567.4, 1264.5], [1567.4, 1315.2], [1162.4, 1315.2]],
                ),
                OCRLine(
                    text="이용해 정밀하게 인식한다.",
                    bbox=[[1162.4, 1408.5], [1567.4, 1408.5], [1567.4, 1457.8], [1162.4, 1457.8]],
                ),
                OCRLine(
                    text="환경에서 RapidOCR와",
                    bbox=[[1184.6, 1313.8], [1543.9, 1313.8], [1543.9, 1364.5], [1184.6, 1364.5]],
                ),
            ],
        )
    ]

    placements = typesetter.build_text_placements(detections, ocr_results)

    assert [placement.text for placement in placements] == [
        "이미지 내의 텍스트를 로컬\n환경에서 RapidOCR와\nPP-OCRv5 mobile 모델을\n이용해 정밀하게 인식한다."
    ]
