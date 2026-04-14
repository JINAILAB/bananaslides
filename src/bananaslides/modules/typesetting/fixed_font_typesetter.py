from __future__ import annotations

import os
import re
import sys
from collections import Counter
from dataclasses import dataclass, replace
from math import ceil
from pathlib import Path
from statistics import median
from typing import Mapping, Sequence

from PIL import Image, ImageDraw, ImageFont
from pptx.text.fonts import FontFiles

from bananaslides.config import FontPolicy
from bananaslides.domain.models import DetectionBox, ElementCategory, OCRLine, OCRResult, RGBColor, TextPlacement
from bananaslides.modules.typesetting.base import Typesetter
from bananaslides.utils.geometry import pixels_to_points
from bananaslides.utils.text import contains_cjk, contains_korean


@dataclass(slots=True)
class _Rect:
    x: float
    y: float
    width: float
    height: float

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def bottom(self) -> float:
        return self.y + self.height

    @property
    def center_y(self) -> float:
        return self.y + self.height / 2.0


@dataclass(slots=True)
class _LineSegment:
    text: str
    rect: _Rect
    polygons: tuple[tuple[tuple[float, float], ...], ...] = ()


@dataclass(slots=True)
class _ParagraphSegment:
    text: str
    rect: _Rect
    rows: tuple[_LineSegment, ...]


@dataclass(slots=True)
class _ParagraphCluster:
    rows: list[_LineSegment]
    rect: _Rect

    @property
    def first_row(self) -> _LineSegment:
        return self.rows[0]

    @property
    def last_row(self) -> _LineSegment:
        return self.rows[-1]


@dataclass(slots=True)
class _MeasuredText:
    left: float
    top: float
    right: float
    bottom: float

    @property
    def width(self) -> float:
        return self.right - self.left

    @property
    def height(self) -> float:
        return self.bottom - self.top


@dataclass(slots=True)
class _RawColorEstimate:
    color: tuple[int, int, int]
    support: int


@dataclass(slots=True)
class _EstimatedColor:
    color: RGBColor
    support: int
    estimated: bool


@dataclass(slots=True)
class _BuiltPlacement:
    placement: TextPlacement
    color_support: int
    color_estimated: bool


@dataclass(slots=True)
class _ColorCluster:
    members: list[int]
    weighted_color_sum: list[float]
    total_support: int

    @property
    def size(self) -> int:
        return len(self.members)

    def center(self) -> tuple[int, int, int]:
        divisor = max(1, self.total_support)
        return tuple(int(round(channel / divisor)) for channel in self.weighted_color_sum)

    def add(self, member_index: int, color: tuple[int, int, int], support: int) -> None:
        weight = max(1, support)
        self.members.append(member_index)
        self.weighted_color_sum[0] += color[0] * weight
        self.weighted_color_sum[1] += color[1] * weight
        self.weighted_color_sum[2] += color[2] * weight
        self.total_support += weight


class FixedFontTypesetter(Typesetter):
    """Fixed-font typesetter with OCR line grouping and measured text fitting."""

    _FONT_SIZE_RATIO_LIMIT = 1.15
    _PARAGRAPH_FONT_SIZE_RATIO_LIMIT = 1.22
    _HEADING_BODY_HEIGHT_RATIO = 1.18
    _HEADING_BODY_GAP_PX = 8.0
    _HEADING_BODY_GAP_RATIO = 0.18
    _BODY_FONT_SIZE_RATIO_LIMIT = 1.22
    _PARAGRAPH_GAP_PX = 12.0
    _PARAGRAPH_GAP_RATIO = 0.20
    _PARAGRAPH_LEFT_DELTA_RATIO = 2.0
    _PARAGRAPH_OVERLAP_RATIO = 0.35
    _ROW_SCAN_STEP_PX = 1.0
    _COLOR_DIFF_THRESHOLD = 18.0
    _COLOR_LUMINANCE_DELTA_THRESHOLD = 6.0
    _COLOR_STRONG_PIXEL_RATIO = 0.35
    _COLOR_STRONG_PIXEL_MIN_COUNT = 24
    _COLOR_CLUSTER_DISTANCE = 20.0
    _COLOR_SNAP_DISTANCE = 18.0
    _KOREAN_FONT_FALLBACKS = (
        "Pretendard",
        "Apple SD Gothic Neo",
        "AppleSDGothicNeo",
        "Noto Sans CJK KR",
        "NotoSansCJKkr",
        "Malgun Gothic",
        "NanumGothic",
    )
    _LATIN_FONT_FALLBACKS = (
        "Pretendard",
        "Helvetica",
        "Aptos",
        "Noto Sans",
        "DejaVu Sans",
        "Liberation Sans",
    )

    def __init__(self, font_policy: FontPolicy, dpi: int = 96) -> None:
        self.font_policy = font_policy
        self.dpi = dpi
        self._font_file_cache: dict[tuple[str, bool], str | None] = {}

    def build_text_placements(
        self,
        detections: Sequence[DetectionBox],
        ocr_results: Sequence[OCRResult],
        *,
        source_image_path: Path | None = None,
        background_image_path: Path | None = None,
    ) -> list[TextPlacement]:
        ocr_by_box = {result.box_id: result for result in ocr_results}
        built_placements: list[_BuiltPlacement] = []
        source_image = self._load_source_image(source_image_path)
        background_image = self._load_source_image(background_image_path)

        try:
            for detection in detections:
                if detection.category is not ElementCategory.TEXT:
                    continue

                result = ocr_by_box.get(detection.box_id)
                if result is None:
                    continue

                paragraph_segments = self._group_paragraph_segments(result)
                if paragraph_segments:
                    built_placements.extend(
                        self._build_paragraph_placements(
                            detection,
                            paragraph_segments,
                            source_image=source_image,
                            background_image=background_image,
                        )
                    )
                    continue

                text = self._normalise_text(result)
                if not text:
                    continue
                built_placements.append(
                    self._build_block_placement(
                        detection,
                        result,
                        text,
                        source_image=source_image,
                        background_image=background_image,
                    )
                )
        finally:
            if source_image is not None:
                source_image.close()
            if background_image is not None:
                background_image.close()

        normalized = self._normalize_slide_placement_colors(built_placements)
        return [item.placement for item in normalized]

    def _build_paragraph_placements(
        self,
        detection: DetectionBox,
        paragraph_segments: Sequence[_ParagraphSegment],
        *,
        source_image: Image.Image | None,
        background_image: Image.Image | None,
    ) -> list[_BuiltPlacement]:
        placements: list[_BuiltPlacement] = []

        for index, paragraph in enumerate(paragraph_segments, start=1):
            text = paragraph.text.strip()
            if not text:
                continue

            is_korean = contains_korean(text)
            font_name = self.font_policy.korean_font if is_korean else self.font_policy.latin_font
            font_file = self._resolve_font_file(font_name, prefer_cjk=contains_cjk(text))
            font_size_pt, measured = self._fit_block_text(
                text=text,
                box_width_px=paragraph.rect.width,
                box_height_px=paragraph.rect.height,
                font_file=font_file,
            )

            estimated_color = self._estimate_text_color(
                source_image,
                background_image,
                paragraph.rect,
                line_segments=paragraph.rows,
            )
            placements.append(
                _BuiltPlacement(
                    placement=TextPlacement(
                        box_id=f"{detection.box_id}:p{index:02d}",
                        text=text,
                        x=paragraph.rect.x,
                        y=paragraph.rect.y,
                        width=max(paragraph.rect.width + max(0.0, measured.left), measured.right),
                        height=max(paragraph.rect.height + max(0.0, measured.top), measured.bottom),
                        font_name=font_name,
                        font_size_pt=font_size_pt,
                        color=estimated_color.color,
                        align="left",
                        language="ko" if is_korean else "en",
                        word_wrap=False,
                        auto_fit=False,
                        font_file=font_file,
                    ),
                    color_support=estimated_color.support,
                    color_estimated=estimated_color.estimated,
                )
            )

        return placements

    def _build_block_placement(
        self,
        detection: DetectionBox,
        result: OCRResult,
        text: str,
        *,
        source_image: Image.Image | None,
        background_image: Image.Image | None,
    ) -> _BuiltPlacement:
        is_korean = contains_korean(text)
        font_name = self.font_policy.korean_font if is_korean else self.font_policy.latin_font
        font_file = self._resolve_font_file(font_name, prefer_cjk=contains_cjk(text))
        font_size_pt, _ = self._fit_block_text(
            text=text,
            box_width_px=detection.width,
            box_height_px=detection.height,
            font_file=font_file,
        )
        line_segments = [segment for segment in (self._to_line_segment(line) for line in result.lines) if segment]
        estimated_color = self._estimate_text_color(
            source_image,
            background_image,
            _Rect(x=detection.x, y=detection.y, width=detection.width, height=detection.height),
            line_segments=line_segments,
        )
        return _BuiltPlacement(
            placement=TextPlacement(
                box_id=detection.box_id,
                text=text,
                x=detection.x,
                y=detection.y,
                width=detection.width,
                height=detection.height,
                font_name=font_name,
                font_size_pt=font_size_pt,
                color=estimated_color.color,
                align="left",
                language="ko" if is_korean else "en",
                word_wrap=True,
                auto_fit=font_file is not None,
                font_file=font_file,
            ),
            color_support=estimated_color.support,
            color_estimated=estimated_color.estimated,
        )

    def _normalize_slide_placement_colors(
        self,
        placements: Sequence[_BuiltPlacement],
    ) -> list[_BuiltPlacement]:
        if len(placements) < 2:
            return list(placements)

        clusters: list[_ColorCluster] = []
        for index, built in enumerate(placements):
            if not built.color_estimated:
                continue
            color = built.placement.color.as_tuple()
            best_cluster: _ColorCluster | None = None
            best_distance: float | None = None
            for cluster in clusters:
                distance = self._rgb_distance(color, cluster.center())
                if distance > self._COLOR_CLUSTER_DISTANCE:
                    continue
                if best_distance is None or distance < best_distance:
                    best_distance = distance
                    best_cluster = cluster
            if best_cluster is None:
                weight = max(1, built.color_support)
                clusters.append(
                    _ColorCluster(
                        members=[index],
                        weighted_color_sum=[
                            color[0] * weight,
                            color[1] * weight,
                            color[2] * weight,
                        ],
                        total_support=weight,
                    )
                )
                continue
            best_cluster.add(index, color, built.color_support)

        palette_tokens = [cluster.center() for cluster in clusters if cluster.size >= 2]
        if not palette_tokens:
            return list(placements)

        normalized: list[_BuiltPlacement] = []
        for built in placements:
            if not built.color_estimated:
                normalized.append(built)
                continue
            color = built.placement.color.as_tuple()
            snapped = min(palette_tokens, key=lambda token: self._rgb_distance(color, token))
            if self._rgb_distance(color, snapped) > self._COLOR_SNAP_DISTANCE:
                normalized.append(built)
                continue
            normalized.append(
                replace(
                    built,
                    placement=replace(built.placement, color=RGBColor(*snapped)),
                )
            )
        return normalized

    def _group_paragraph_segments(self, result: OCRResult) -> list[_ParagraphSegment]:
        segments = [segment for segment in (self._to_line_segment(line) for line in result.lines) if segment]
        if not segments:
            return []

        rows = self._split_segments_into_rows(segments)
        merged_rows: list[_LineSegment] = []
        for row in rows:
            merged_rows.extend(self._split_row_into_line_clusters(row))

        return self._merge_rows_into_paragraphs(merged_rows)

    def _split_segments_into_rows(self, segments: Sequence[_LineSegment]) -> list[list[_LineSegment]]:
        ordered = sorted(segments, key=lambda segment: (segment.rect.center_y, segment.rect.x))
        if len(ordered) <= 1:
            return [ordered] if ordered else []

        top = min(segment.rect.y for segment in ordered)
        bottom = max(segment.rect.bottom for segment in ordered)
        if (bottom - top) < 5.0:
            return [ordered]

        step = self._ROW_SCAN_STEP_PX
        bins = max(1, int(round((bottom - top) / step)))
        scan_positions = [top + (index * step) for index in range(bins + 1)]
        collision_counts = [
            sum(1 for segment in ordered if segment.rect.y <= scan_y <= segment.rect.bottom)
            for scan_y in scan_positions
        ]

        separators: list[float] = []
        in_gap = False
        gap_start = 0
        for index, count in enumerate(collision_counts):
            if count < 1 and not in_gap:
                in_gap = True
                gap_start = index
            elif count >= 1 and in_gap:
                in_gap = False
                separators.append((scan_positions[gap_start] + scan_positions[index - 1]) / 2.0)
        if in_gap:
            separators.append((scan_positions[gap_start] + scan_positions[-1]) / 2.0)

        if not separators:
            return [ordered]

        rows: list[list[_LineSegment]] = [[] for _ in range(len(separators) + 1)]
        for segment in ordered:
            row_index = 0
            while row_index < len(separators) and segment.rect.center_y > separators[row_index]:
                row_index += 1
            rows[row_index].append(segment)
        return [row for row in rows if row]

    def _split_row_into_line_clusters(self, row: Sequence[_LineSegment]) -> list[_LineSegment]:
        ordered = sorted(row, key=lambda segment: segment.rect.x)
        if not ordered:
            return []

        clusters: list[list[_LineSegment]] = [[ordered[0]]]
        for segment in ordered[1:]:
            previous = clusters[-1][-1]
            if self._is_vertical_segment(previous) or self._is_vertical_segment(segment):
                clusters.append([segment])
                continue

            gap = segment.rect.x - previous.rect.right
            min_height = min(previous.rect.height, segment.rect.height)
            max_height = max(previous.rect.height, segment.rect.height)
            center_delta = abs(previous.rect.center_y - segment.rect.center_y)
            x_overlap = self._horizontal_overlap(previous.rect, segment.rect)
            max_gap = max(24.0, min_height * 0.8)

            if (
                x_overlap >= min(previous.rect.width, segment.rect.width) * 0.25
                and center_delta >= (min_height * 0.35)
            ):
                clusters.append([segment])
                continue
            if not self._has_similar_font_size(
                previous.rect,
                segment.rect,
                ratio_limit=self._FONT_SIZE_RATIO_LIMIT,
            ):
                clusters.append([segment])
                continue
            if gap > max_gap:
                clusters.append([segment])
                continue

            clusters[-1].append(segment)

        grouped_lines: list[_LineSegment] = []
        for cluster in clusters:
            rect = self._union_rect(item.rect for item in cluster)
            text = self._join_segment_texts(item.text for item in cluster)
            if text:
                grouped_lines.append(
                    _LineSegment(
                        text=text,
                        rect=rect,
                        polygons=tuple(
                            polygon
                            for item in cluster
                            for polygon in item.polygons
                        ),
                    )
                )
        return grouped_lines

    def _merge_rows_into_paragraphs(self, rows: Sequence[_LineSegment]) -> list[_ParagraphSegment]:
        ordered = sorted(rows, key=lambda row: (row.rect.y, row.rect.x))
        if not ordered:
            return []

        clusters: list[_ParagraphCluster] = []
        for row in ordered:
            best_cluster: _ParagraphCluster | None = None
            best_score = float("-inf")
            for cluster in clusters:
                score = self._score_paragraph_candidate(cluster, row)
                if score is None or score <= best_score:
                    continue
                best_score = score
                best_cluster = cluster

            if best_cluster is None:
                clusters.append(_ParagraphCluster(rows=[row], rect=row.rect))
                continue

            best_cluster.rows.append(row)
            best_cluster.rect = self._union_rect((best_cluster.rect, row.rect))

        split_clusters: list[_ParagraphCluster] = []
        for cluster in clusters:
            split_clusters.extend(self._split_heading_like_cluster(cluster))

        paragraphs: list[_ParagraphSegment] = []
        for cluster in self._sort_paragraph_clusters(split_clusters):
            ordered_rows = sorted(cluster.rows, key=lambda row: (row.rect.y, row.rect.x))
            lines = tuple(row for row in ordered_rows if row.text.strip())
            if not lines:
                continue
            rect = self._union_rect(row.rect for row in lines)
            text = "\n".join(row.text.strip() for row in lines if row.text.strip())
            paragraphs.append(_ParagraphSegment(text=text, rect=rect, rows=lines))
        return paragraphs

    def _sort_paragraph_clusters(
        self,
        clusters: Sequence[_ParagraphCluster],
    ) -> list[_ParagraphCluster]:
        if len(clusters) <= 1:
            return list(clusters)

        first_rows = [cluster.first_row for cluster in clusters]
        grouped_rows = self._split_segments_into_rows(first_rows)
        ordered_clusters: list[_ParagraphCluster] = []
        remaining = list(clusters)

        for row in grouped_rows:
            for segment in sorted(row, key=lambda item: item.rect.x):
                match_index = next(
                    (index for index, cluster in enumerate(remaining) if cluster.first_row is segment),
                    None,
                )
                if match_index is None:
                    continue
                ordered_clusters.append(remaining.pop(match_index))

        ordered_clusters.extend(remaining)
        return ordered_clusters

    def _split_heading_like_cluster(
        self,
        cluster: _ParagraphCluster,
    ) -> list[_ParagraphCluster]:
        ordered_rows = sorted(cluster.rows, key=lambda row: (row.rect.y, row.rect.x))
        if len(ordered_rows) < 3:
            return [cluster]

        heading = ordered_rows[0]
        body = ordered_rows[1:]
        body_heights = [row.rect.height for row in body]
        body_median_height = median(body_heights)
        if body_median_height <= 0:
            return [cluster]

        heading_ratio = heading.rect.height / body_median_height
        if heading_ratio < self._HEADING_BODY_HEIGHT_RATIO:
            return [cluster]

        first_gap = body[0].rect.y - heading.rect.bottom
        body_gaps = [current.rect.y - previous.rect.bottom for previous, current in zip(body, body[1:])]
        body_gap_median = median(body_gaps) if body_gaps else 0.0
        gap_threshold = max(
            self._HEADING_BODY_GAP_PX,
            body_median_height * self._HEADING_BODY_GAP_RATIO,
            body_gap_median + self._HEADING_BODY_GAP_PX,
        )
        if first_gap < gap_threshold:
            return [cluster]

        heading_overlap = self._horizontal_overlap(heading.rect, body[0].rect)
        min_width = max(1.0, min(heading.rect.width, body[0].rect.width))
        if heading_overlap < (min_width * self._PARAGRAPH_OVERLAP_RATIO):
            return [cluster]

        if not self._body_rows_are_consistent(body):
            return [cluster]

        return [
            _ParagraphCluster(rows=[heading], rect=heading.rect),
            _ParagraphCluster(rows=body, rect=self._union_rect(row.rect for row in body)),
        ]

    def _body_rows_are_consistent(self, rows: Sequence[_LineSegment]) -> bool:
        if len(rows) < 2:
            return True

        heights = [row.rect.height for row in rows]
        min_height = max(1.0, min(heights))
        max_height = max(heights)
        if (max_height / min_height) > self._BODY_FONT_SIZE_RATIO_LIMIT:
            return False

        gaps = [current.rect.y - previous.rect.bottom for previous, current in zip(rows, rows[1:])]
        if not gaps:
            return True

        median_gap = median(gaps)
        allowed_gap = max(self._HEADING_BODY_GAP_PX, median(heights) * self._HEADING_BODY_GAP_RATIO)
        return all(abs(gap - median_gap) <= allowed_gap for gap in gaps)

    def _starts_new_paragraph(self, current_rows: Sequence[_LineSegment], row: _LineSegment) -> bool:
        previous = current_rows[-1]
        if not self._has_similar_font_size(
            previous.rect,
            row.rect,
            ratio_limit=self._PARAGRAPH_FONT_SIZE_RATIO_LIMIT,
        ):
            return True

        vertical_gap = row.rect.y - previous.rect.bottom
        min_height = min(previous.rect.height, row.rect.height)
        if vertical_gap < -(min_height * 0.35):
            return True

        if vertical_gap > max(self._PARAGRAPH_GAP_PX, previous.rect.height * self._PARAGRAPH_GAP_RATIO):
            return True

        overlap = self._horizontal_overlap(previous.rect, row.rect)
        min_width = max(1.0, min(previous.rect.width, row.rect.width))
        left_delta = abs(previous.rect.x - row.rect.x)
        if (
            overlap < (min_width * self._PARAGRAPH_OVERLAP_RATIO)
            and left_delta > (previous.rect.height * self._PARAGRAPH_LEFT_DELTA_RATIO)
        ):
            return True

        if current_rows and self._starts_with_bullet(row.text):
            return True

        return False

    def _score_paragraph_candidate(self, cluster: _ParagraphCluster, row: _LineSegment) -> float | None:
        if self._starts_new_paragraph(cluster.rows, row):
            return None

        previous = cluster.last_row
        overlap = max(
            self._horizontal_overlap(previous.rect, row.rect),
            self._horizontal_overlap(cluster.rect, row.rect),
        )
        overlap_ratio = overlap / max(1.0, row.rect.width)

        gap_limit = max(self._PARAGRAPH_GAP_PX, previous.rect.height * self._PARAGRAPH_GAP_RATIO, 1.0)
        vertical_gap = max(0.0, row.rect.y - previous.rect.bottom)
        gap_score = 1.0 - min(vertical_gap / gap_limit, 1.0)

        left_limit = max(previous.rect.height * self._PARAGRAPH_LEFT_DELTA_RATIO, 1.0)
        left_delta = min(abs(previous.rect.x - row.rect.x), abs(cluster.rect.x - row.rect.x))
        left_score = 1.0 - min(left_delta / left_limit, 1.0)

        width_ratio = min(cluster.rect.width, row.rect.width) / max(cluster.rect.width, row.rect.width, 1.0)
        return (overlap_ratio * 3.0) + gap_score + left_score + (width_ratio * 0.5)

    @staticmethod
    def _is_vertical_segment(segment: _LineSegment) -> bool:
        return segment.rect.height > segment.rect.width * 1.4

    @staticmethod
    def _has_similar_font_size(
        left: _Rect,
        right: _Rect,
        *,
        ratio_limit: float,
    ) -> bool:
        min_height = max(1.0, min(left.height, right.height))
        max_height = max(left.height, right.height)
        return (max_height / min_height) <= ratio_limit

    @staticmethod
    def _horizontal_overlap(left: _Rect, right: _Rect) -> float:
        return max(0.0, min(left.right, right.right) - max(left.x, right.x))

    @staticmethod
    def _starts_with_bullet(text: str) -> bool:
        return bool(re.match(r"^\s*(?:[-*•·▪◦‣]|\d+[.)]|[A-Za-z][.)])\s+", text))

    @staticmethod
    def _union_rect(rects: Sequence[_Rect] | list[_Rect] | tuple[_Rect, ...] | object) -> _Rect:
        rect_list = list(rects)
        min_x = min(rect.x for rect in rect_list)
        min_y = min(rect.y for rect in rect_list)
        max_x = max(rect.right for rect in rect_list)
        max_y = max(rect.bottom for rect in rect_list)
        return _Rect(x=min_x, y=min_y, width=max_x - min_x, height=max_y - min_y)

    def _to_line_segment(self, line: OCRLine) -> _LineSegment | None:
        text = line.text.strip()
        if not text or not line.bbox:
            return None
        xs = [point[0] for point in line.bbox]
        ys = [point[1] for point in line.bbox]
        polygon = tuple((float(point[0]), float(point[1])) for point in line.bbox)
        return _LineSegment(
            text=text,
            rect=_Rect(
                x=min(xs),
                y=min(ys),
                width=max(xs) - min(xs),
                height=max(ys) - min(ys),
            ),
            polygons=(polygon,),
        )

    def _fit_line_text(
        self,
        text: str,
        rect: _Rect,
        font_file: str | None,
    ) -> tuple[float, _MeasuredText]:
        if font_file is None:
            font_size_pt = self._fallback_font_size(rect.height)
            return font_size_pt, _MeasuredText(0.0, 0.0, rect.width, rect.height)

        min_pt = self.font_policy.min_font_size_pt
        max_pt = max(self.font_policy.max_font_size_pt, pixels_to_points(rect.height * 1.8, dpi=self.dpi))
        best_pt = min_pt
        best_measurement = self._measure_text(text, min_pt, font_file)

        low = min_pt
        high = max_pt
        for _ in range(16):
            probe = (low + high) / 2.0
            measurement = self._measure_text(text, probe, font_file)
            if measurement.width <= rect.width and measurement.height <= rect.height:
                best_pt = probe
                best_measurement = measurement
                low = probe
            else:
                high = probe

        return round(best_pt, 2), best_measurement

    def _fit_block_text(
        self,
        text: str,
        box_width_px: float,
        box_height_px: float,
        font_file: str | None,
    ) -> tuple[float, _MeasuredText]:
        if font_file is None:
            font_size_pt = self._fallback_font_size(box_height_px)
            return font_size_pt, _MeasuredText(0.0, 0.0, box_width_px, box_height_px)

        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            font_size_pt = self.font_policy.min_font_size_pt
            return font_size_pt, _MeasuredText(0.0, 0.0, 0.0, 0.0)

        min_pt = self.font_policy.min_font_size_pt
        max_pt = max(
            self.font_policy.max_font_size_pt,
            pixels_to_points((box_height_px / max(1, len(lines))) * 1.8, dpi=self.dpi),
        )
        best_pt = min_pt
        best_measurement = self._measure_multiline(lines, min_pt, font_file)

        low = min_pt
        high = max_pt
        for _ in range(16):
            probe = (low + high) / 2.0
            measurement = self._measure_multiline(lines, probe, font_file)
            if measurement.width <= box_width_px and measurement.height <= box_height_px:
                best_pt = probe
                best_measurement = measurement
                low = probe
            else:
                high = probe

        return round(best_pt, 2), best_measurement

    def _measure_multiline(
        self,
        lines: Sequence[str],
        font_size_pt: float,
        font_file: str,
    ) -> _MeasuredText:
        left = 0.0
        top = 0.0
        right = 0.0
        bottom = 0.0
        current_y = 0.0
        line_gap = self._font_size_to_px(font_size_pt) * (0.5 if any(contains_cjk(line) for line in lines) else 0.3)

        for index, line in enumerate(lines):
            measurement = self._measure_text(line, font_size_pt, font_file)
            left = min(left, measurement.left)
            top = min(top, current_y + measurement.top) if index else measurement.top
            right = max(right, measurement.right)
            bottom = max(bottom, current_y + measurement.bottom)
            current_y += measurement.height + line_gap

        return _MeasuredText(left=left, top=top, right=right, bottom=bottom)

    def _measure_text(self, text: str, font_size_pt: float, font_file: str) -> _MeasuredText:
        font = ImageFont.truetype(font_file, size=self._font_size_to_px(font_size_pt))
        left, top, right, bottom = font.getbbox(text or " ")
        return _MeasuredText(float(left), float(top), float(right), float(bottom))

    def _font_size_to_px(self, font_size_pt: float) -> int:
        return max(1, int(round(font_size_pt * self.dpi / 72.0)))

    def _fallback_font_size(self, box_height_px: float) -> float:
        estimated_pt = pixels_to_points(box_height_px / 1.5, dpi=self.dpi)
        return max(self.font_policy.min_font_size_pt, round(estimated_pt, 2))

    def _resolve_font_file(self, font_name: str, prefer_cjk: bool) -> str | None:
        cache_key = (font_name, prefer_cjk)
        if cache_key in self._font_file_cache:
            return self._font_file_cache[cache_key]

        candidates = [font_name]
        if prefer_cjk:
            candidates.extend(self._KOREAN_FONT_FALLBACKS)
        else:
            candidates.extend(self._LATIN_FONT_FALLBACKS)

        for candidate in candidates:
            font_file = self._try_find_font_file(candidate)
            if font_file is not None:
                self._font_file_cache[cache_key] = font_file
                return font_file

        self._font_file_cache[cache_key] = None
        return None

    def _try_find_font_file(self, family_name: str) -> str | None:
        try:
            return FontFiles.find(family_name, False, False)
        except Exception:
            pass

        target = self._normalise_font_name(family_name)
        for directory in self._font_directories():
            if not directory.exists():
                continue
            for root, _, files in os.walk(directory):
                for filename in files:
                    suffix = Path(filename).suffix.lower()
                    if suffix not in {".ttf", ".otf", ".ttc", ".otc"}:
                        continue
                    if target in self._normalise_font_name(filename):
                        return str(Path(root) / filename)
        return None

    @classmethod
    def _font_directories(cls) -> tuple[Path, ...]:
        directories = [Path("assets/fonts")]
        directories.extend(cls._platform_font_directories(sys.platform, Path.home(), os.environ))

        deduped: list[Path] = []
        seen: set[str] = set()
        for directory in directories:
            key = str(directory)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(directory)
        return tuple(deduped)

    @staticmethod
    def _platform_font_directories(
        platform_name: str,
        home: Path,
        env: Mapping[str, str],
    ) -> tuple[Path, ...]:
        if platform_name.startswith("darwin"):
            return (
                Path("/Library/Fonts"),
                Path("/System/Library/Fonts"),
                home / "Library" / "Fonts",
                home / ".fonts",
            )
        if platform_name.startswith("win"):
            windir = Path(env.get("WINDIR", "C:/Windows"))
            local_appdata = env.get("LOCALAPPDATA")
            roaming_appdata = env.get("APPDATA")
            directories = [windir / "Fonts"]
            if local_appdata:
                directories.append(Path(local_appdata) / "Microsoft" / "Windows" / "Fonts")
            if roaming_appdata:
                directories.append(Path(roaming_appdata) / "Microsoft" / "Windows" / "Fonts")
            return tuple(directories)

        directories = [
            Path("/usr/share/fonts"),
            Path("/usr/local/share/fonts"),
            home / ".local" / "share" / "fonts",
            home / ".fonts",
        ]
        xdg_data_home = env.get("XDG_DATA_HOME")
        if xdg_data_home:
            directories.append(Path(xdg_data_home) / "fonts")
        return tuple(directories)

    @staticmethod
    def _normalise_font_name(value: str) -> str:
        return "".join(character for character in value.lower() if character.isalnum())

    @staticmethod
    def _join_segment_texts(parts: Sequence[str] | list[str] | tuple[str, ...] | object) -> str:
        result = ""
        for raw_part in parts:
            part = raw_part.strip()
            if not part:
                continue
            if not result:
                result = part
                continue
            if result.endswith(("-", "/", "(")) or part.startswith((",", ".", ":", ";", "!", "?", ")", "]", "%")):
                result += part
                continue
            if contains_cjk(result[-1]) and contains_cjk(part[0]):
                result += part
                continue
            result += f" {part}"
        return result

    @staticmethod
    def _normalise_text(result: OCRResult) -> str:
        return "\n".join(line.text.strip() for line in result.lines if line.text.strip()).strip() or result.text.strip()

    @staticmethod
    def _load_source_image(image_path: Path | None) -> Image.Image | None:
        if image_path is None or not image_path.exists():
            return None
        try:
            with Image.open(image_path) as image:
                return image.convert("RGB")
        except Exception:
            return None

    def _estimate_text_color(
        self,
        source_image: Image.Image | None,
        background_image: Image.Image | None,
        rect: _Rect,
        *,
        line_segments: Sequence[_LineSegment] | None = None,
    ) -> _EstimatedColor:
        if source_image is None or background_image is None or source_image.size != background_image.size:
            return _EstimatedColor(
                color=self.font_policy.default_text_color,
                support=0,
                estimated=False,
            )

        estimated = self._estimate_raw_text_color(
            source_image,
            background_image,
            rect,
            line_segments=line_segments,
        )
        if estimated is None:
            return _EstimatedColor(
                color=self.font_policy.default_text_color,
                support=0,
                estimated=False,
            )

        return _EstimatedColor(
            color=RGBColor(*estimated.color),
            support=estimated.support,
            estimated=True,
        )

    def _estimate_raw_text_color(
        self,
        source_image: Image.Image,
        background_image: Image.Image,
        rect: _Rect,
        *,
        line_segments: Sequence[_LineSegment] | None = None,
    ) -> _RawColorEstimate | None:
        if line_segments:
            line_estimates = [
                estimate
                for estimate in (
                    self._estimate_line_text_color(source_image, background_image, segment)
                    for segment in line_segments
                )
                if estimate is not None
            ]
            if line_estimates:
                return self._combine_color_estimates(line_estimates)

        return self._estimate_rect_text_color(source_image, background_image, rect)

    def _estimate_line_text_color(
        self,
        source_image: Image.Image,
        background_image: Image.Image,
        line_segment: _LineSegment,
    ) -> _RawColorEstimate | None:
        bounds = self._rect_bounds(source_image, line_segment.rect)
        if bounds is None:
            return None
        mask = self._build_polygon_mask(bounds, line_segment.polygons)
        return self._estimate_crop_text_color(source_image, background_image, bounds, mask)

    def _estimate_rect_text_color(
        self,
        source_image: Image.Image,
        background_image: Image.Image,
        rect: _Rect,
    ) -> _RawColorEstimate | None:
        bounds = self._rect_bounds(source_image, rect)
        if bounds is None:
            return None
        return self._estimate_crop_text_color(source_image, background_image, bounds, None)

    def _estimate_crop_text_color(
        self,
        source_image: Image.Image,
        background_image: Image.Image,
        bounds: tuple[int, int, int, int],
        mask: Image.Image | None,
    ) -> _RawColorEstimate | None:
        source_crop = source_image.crop(bounds)
        background_crop = background_image.crop(bounds)
        source_pixels = list(source_crop.getdata())
        background_pixels = list(background_crop.getdata())
        if not source_pixels or len(source_pixels) != len(background_pixels):
            return None

        mask_pixels = list(mask.getdata()) if mask is not None else None
        candidate_pixels: list[tuple[tuple[int, int, int], float]] = []
        lighter_pixels: list[tuple[tuple[int, int, int], float]] = []
        darker_pixels: list[tuple[tuple[int, int, int], float]] = []
        lighter_score = 0.0
        darker_score = 0.0

        for index, (source_pixel, background_pixel) in enumerate(zip(source_pixels, background_pixels, strict=True)):
            if mask_pixels is not None and mask_pixels[index] == 0:
                continue

            distance = self._rgb_distance(source_pixel, background_pixel)
            if distance < self._COLOR_DIFF_THRESHOLD:
                continue

            sample = (source_pixel, distance)
            candidate_pixels.append(sample)
            luminance_delta = self._luminance(source_pixel) - self._luminance(background_pixel)
            if luminance_delta >= self._COLOR_LUMINANCE_DELTA_THRESHOLD:
                lighter_pixels.append(sample)
                lighter_score += distance
            elif luminance_delta <= -self._COLOR_LUMINANCE_DELTA_THRESHOLD:
                darker_pixels.append(sample)
                darker_score += distance

        if lighter_score > darker_score and lighter_pixels:
            selected = lighter_pixels
        elif darker_pixels:
            selected = darker_pixels
        elif lighter_pixels:
            selected = lighter_pixels
        else:
            selected = candidate_pixels

        strongest_pixels = self._select_strongest_pixels(selected)
        if not strongest_pixels:
            return None

        return _RawColorEstimate(
            color=self._median_color(strongest_pixels),
            support=len(strongest_pixels),
        )

    def _select_strongest_pixels(
        self,
        pixels: Sequence[tuple[tuple[int, int, int], float]],
    ) -> list[tuple[int, int, int]]:
        if not pixels:
            return []
        keep_count = max(
            self._COLOR_STRONG_PIXEL_MIN_COUNT,
            int(ceil(len(pixels) * self._COLOR_STRONG_PIXEL_RATIO)),
        )
        strongest = sorted(pixels, key=lambda item: item[1], reverse=True)[: min(len(pixels), keep_count)]
        return [pixel for pixel, _distance in strongest]

    def _combine_color_estimates(
        self,
        estimates: Sequence[_RawColorEstimate],
    ) -> _RawColorEstimate:
        total_support = sum(max(1, estimate.support) for estimate in estimates)
        if total_support <= 0:
            total_support = len(estimates)
        return _RawColorEstimate(
            color=(
                int(round(sum(estimate.color[0] * max(1, estimate.support) for estimate in estimates) / total_support)),
                int(round(sum(estimate.color[1] * max(1, estimate.support) for estimate in estimates) / total_support)),
                int(round(sum(estimate.color[2] * max(1, estimate.support) for estimate in estimates) / total_support)),
            ),
            support=total_support,
        )

    @staticmethod
    def _median_color(pixels: Sequence[tuple[int, int, int]]) -> tuple[int, int, int]:
        return tuple(
            int(round(median(channel_values)))
            for channel_values in zip(*pixels, strict=True)
        )

    @staticmethod
    def _build_polygon_mask(
        bounds: tuple[int, int, int, int],
        polygons: Sequence[tuple[tuple[float, float], ...]],
    ) -> Image.Image | None:
        if not polygons:
            return None

        left, top, right, bottom = bounds
        mask = Image.new("L", (max(1, right - left), max(1, bottom - top)), 0)
        draw = ImageDraw.Draw(mask)
        has_valid_polygon = False
        for polygon in polygons:
            if len(polygon) < 3:
                continue
            translated = [(point_x - left, point_y - top) for point_x, point_y in polygon]
            draw.polygon(translated, fill=255)
            has_valid_polygon = True
        return mask if has_valid_polygon else None

    def _dominant_color(self, pixels: Sequence[tuple[int, int, int]]) -> tuple[int, int, int]:
        buckets = Counter(self._bucket_rgb(pixel) for pixel in pixels)
        bucket, _count = buckets.most_common(1)[0]
        selected = [pixel for pixel in pixels if self._bucket_rgb(pixel) == bucket]
        if not selected:
            return bucket
        return tuple(
            int(round(sum(channel_values) / len(selected)))
            for channel_values in zip(*selected, strict=True)
        )

    @staticmethod
    def _rect_bounds(source_image: Image.Image, rect: _Rect) -> tuple[int, int, int, int] | None:
        left = max(0, int(rect.x))
        top = max(0, int(rect.y))
        right = min(source_image.width, int(round(rect.right)))
        bottom = min(source_image.height, int(round(rect.bottom)))
        if right <= left or bottom <= top:
            return None
        return left, top, right, bottom

    @staticmethod
    def _bucket_rgb(rgb: tuple[int, int, int]) -> tuple[int, int, int]:
        return tuple(int(round(channel / 16.0) * 16) for channel in rgb)

    @staticmethod
    def _luminance(rgb: tuple[int, int, int]) -> float:
        return rgb[0] * 0.299 + rgb[1] * 0.587 + rgb[2] * 0.114

    @staticmethod
    def _rgb_distance(left: tuple[int, int, int], right: tuple[int, int, int]) -> float:
        return ((left[0] - right[0]) ** 2 + (left[1] - right[1]) ** 2 + (left[2] - right[2]) ** 2) ** 0.5
