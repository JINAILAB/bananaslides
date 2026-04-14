from __future__ import annotations

from bananaslides.domain.models import PresentationRenderSpec, RGBColor, SlideRenderSpec, SlideSize, TextPlacement
from bananaslides.modules.typesetting.font_normalizer import normalize_presentation_fonts


def _placement(
    *,
    text: str,
    font_size_pt: float,
    x: float = 100.0,
    y: float = 100.0,
    width: float = 420.0,
    height: float = 120.0,
    color: RGBColor | None = None,
) -> TextPlacement:
    return TextPlacement(
        box_id=f"box-{abs(hash((text, font_size_pt, x, y)))}",
        text=text,
        x=x,
        y=y,
        width=width,
        height=height,
        font_name="Pretendard",
        font_size_pt=font_size_pt,
        color=color or RGBColor(0, 0, 0),
        language="ko",
    )


def test_body_family_font_sizes_are_normalized_across_slides() -> None:
    original = PresentationRenderSpec(
        slides=[
            SlideRenderSpec(
                slide_size=SlideSize(width_px=1600, height_px=900),
                text_placements=[
                    _placement(
                        text="이미지 내의 텍스트를 로컬\n환경에서 RapidOCR와\nPP-OCRv5 mobile 모델을\n이용해 정밀하게 인식한다.",
                        font_size_pt=20.6,
                        x=120.0,
                        y=240.0,
                        color=RGBColor(10, 20, 30),
                    )
                ],
            ),
            SlideRenderSpec(
                slide_size=SlideSize(width_px=1600, height_px=900),
                text_placements=[
                    _placement(
                        text="복원된 깨끗한 배경 이미지 위에\nOCR로 추출한 텍스트를 다시\n배치하여 최종\nPowerPoint 파일을 생성한다.",
                        font_size_pt=20.8,
                        x=980.0,
                        y=240.0,
                        color=RGBColor(40, 50, 60),
                    )
                ],
            ),
        ],
        dpi=96,
    )

    normalized = normalize_presentation_fonts(original)

    first = normalized.slides[0].text_placements[0]
    second = normalized.slides[1].text_placements[0]
    assert first.font_size_pt == 20.5
    assert second.font_size_pt == 20.5
    assert first.x == 120.0
    assert first.y == 240.0
    assert first.color == RGBColor(10, 20, 30)


def test_label_family_splits_into_heading_and_caption_tokens() -> None:
    spec = PresentationRenderSpec(
        slides=[
            SlideRenderSpec(
                slide_size=SlideSize(width_px=1600, height_px=900),
                text_placements=[
                    _placement(text="RapidOCR + ONNX 엔진", font_size_pt=29.6, y=120.0, height=56.0),
                    _placement(text="Gemini 이미지 생성", font_size_pt=29.8, y=200.0, height=56.0),
                    _placement(text="로컬 OCR", font_size_pt=13.6, y=580.0, height=28.0),
                    _placement(text="배경 복원", font_size_pt=13.8, y=640.0, height=28.0),
                ],
            )
        ],
        dpi=96,
    )

    normalized = normalize_presentation_fonts(spec)
    sizes = [placement.font_size_pt for placement in normalized.slides[0].text_placements]

    assert sizes == [29.5, 29.5, 13.5, 13.5]


def test_outlier_box_is_forced_to_cluster_token_even_if_it_is_small() -> None:
    spec = PresentationRenderSpec(
        slides=[
            SlideRenderSpec(
                slide_size=SlideSize(width_px=1600, height_px=900),
                text_placements=[
                    _placement(text="긴 본문 블록 하나\n둘째 줄", font_size_pt=20.0),
                    _placement(text="긴 본문 블록 둘\n둘째 줄", font_size_pt=20.5),
                    _placement(text="아주 작은 박스\n둘째 줄", font_size_pt=11.0, width=180.0, height=46.0),
                ],
            )
        ],
        dpi=96,
    )

    normalized = normalize_presentation_fonts(spec)
    sizes = [placement.font_size_pt for placement in normalized.slides[0].text_placements]

    assert sizes == [20.0, 20.0, 20.0]


def test_normalization_disables_auto_fit_to_preserve_clustered_size() -> None:
    spec = PresentationRenderSpec(
        slides=[
            SlideRenderSpec(
                slide_size=SlideSize(width_px=1600, height_px=900),
                text_placements=[
                    TextPlacement(
                        box_id="box-auto-fit",
                        text="짧은 라벨",
                        x=100.0,
                        y=100.0,
                        width=160.0,
                        height=40.0,
                        font_name="Pretendard",
                        font_size_pt=24.2,
                        color=RGBColor(0, 0, 0),
                        language="ko",
                        auto_fit=True,
                    ),
                    TextPlacement(
                        box_id="box-auto-fit-2",
                        text="또 다른 라벨",
                        x=100.0,
                        y=160.0,
                        width=170.0,
                        height=40.0,
                        font_name="Pretendard",
                        font_size_pt=24.6,
                        color=RGBColor(0, 0, 0),
                        language="ko",
                        auto_fit=True,
                    ),
                ],
            )
        ],
        dpi=96,
    )

    normalized = normalize_presentation_fonts(spec)

    assert all(not placement.auto_fit for placement in normalized.slides[0].text_placements)


def test_body_family_automatically_selects_three_tokens() -> None:
    spec = PresentationRenderSpec(
        slides=[
            SlideRenderSpec(
                slide_size=SlideSize(width_px=1600, height_px=900),
                text_placements=[
                    _placement(text="작은 본문 A\n둘째 줄", font_size_pt=14.1),
                    _placement(text="작은 본문 B\n둘째 줄", font_size_pt=14.2),
                    _placement(text="중간 본문 A\n둘째 줄", font_size_pt=24.1),
                    _placement(text="중간 본문 B\n둘째 줄", font_size_pt=24.2),
                    _placement(text="큰 본문 A\n둘째 줄", font_size_pt=36.1),
                    _placement(text="큰 본문 B\n둘째 줄", font_size_pt=36.2),
                ],
            )
        ],
        dpi=96,
    )

    normalized = normalize_presentation_fonts(spec)
    sizes = [placement.font_size_pt for placement in normalized.slides[0].text_placements]

    assert sizes == [14.0, 14.0, 24.0, 24.0, 36.0, 36.0]


def test_body_family_can_expand_to_six_tokens_when_tiers_are_clear() -> None:
    spec = PresentationRenderSpec(
        slides=[
            SlideRenderSpec(
                slide_size=SlideSize(width_px=1600, height_px=900),
                text_placements=[
                    _placement(text="tier 1A\nbody", font_size_pt=12.1),
                    _placement(text="tier 1B\nbody", font_size_pt=12.2),
                    _placement(text="tier 2A\nbody", font_size_pt=16.1),
                    _placement(text="tier 2B\nbody", font_size_pt=16.2),
                    _placement(text="tier 3A\nbody", font_size_pt=21.1),
                    _placement(text="tier 3B\nbody", font_size_pt=21.2),
                    _placement(text="tier 4A\nbody", font_size_pt=27.1),
                    _placement(text="tier 4B\nbody", font_size_pt=27.2),
                    _placement(text="tier 5A\nbody", font_size_pt=34.1),
                    _placement(text="tier 5B\nbody", font_size_pt=34.2),
                    _placement(text="tier 6A\nbody", font_size_pt=42.1),
                    _placement(text="tier 6B\nbody", font_size_pt=42.2),
                ],
            )
        ],
        dpi=96,
    )

    normalized = normalize_presentation_fonts(spec)
    sizes = [placement.font_size_pt for placement in normalized.slides[0].text_placements]

    assert sizes == [12.0, 12.0, 16.0, 16.0, 21.0, 21.0, 27.0, 27.0, 34.0, 34.0, 42.0, 42.0]
