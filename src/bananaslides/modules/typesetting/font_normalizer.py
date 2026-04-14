from __future__ import annotations

import math
import re
from dataclasses import dataclass, replace
from functools import lru_cache
from statistics import median

from bananaslides.domain.models import PresentationRenderSpec, SlideRenderSpec, TextPlacement


_SPACE_RE = re.compile(r"\s+")


@dataclass(slots=True)
class _PlacementRef:
    slide_index: int
    placement_index: int
    slide_height_px: int
    placement: TextPlacement
    family: str
    line_count: int
    text_length: int
    top_ratio: float


@dataclass(slots=True)
class _PartitionResult:
    intervals: tuple[tuple[int, int], ...]
    score: float


class FontNormalizer:
    _STEP_PT = 0.5
    _BODY_CLUSTER_RATIO = 1.15
    _LABEL_CLUSTER_RATIO = 1.20
    _MIN_CLUSTER_SIZE = 2
    _MAX_TOKENS_PER_FAMILY = 6

    def __init__(self, dpi: int = 96) -> None:
        self.dpi = dpi

    def normalize(self, spec: PresentationRenderSpec) -> PresentationRenderSpec:
        normalized_slides = [
            SlideRenderSpec(
                slide_size=slide.slide_size,
                background_image_path=slide.background_image_path,
                image_placements=list(slide.image_placements),
                text_placements=list(slide.text_placements),
            )
            for slide in spec.slides
        ]
        normalized_spec = PresentationRenderSpec(slides=normalized_slides, dpi=spec.dpi)
        refs = self._collect_refs(normalized_spec)
        if not refs:
            return normalized_spec

        groups: dict[str, list[_PlacementRef]] = {}
        for ref in refs:
            groups.setdefault(ref.family, []).append(ref)

        for family, family_refs in groups.items():
            threshold = self._BODY_CLUSTER_RATIO if family.endswith(":body") else self._LABEL_CLUSTER_RATIO
            tokens = self._build_tokens(family_refs, threshold=threshold)
            if not tokens:
                continue
            for ref in family_refs:
                snapped = min(tokens, key=lambda token: abs(token - ref.placement.font_size_pt))
                normalized_slides[ref.slide_index].text_placements[ref.placement_index] = replace(
                    ref.placement,
                    font_size_pt=snapped,
                    auto_fit=False,
                )

        return normalized_spec

    def _collect_refs(self, spec: PresentationRenderSpec) -> list[_PlacementRef]:
        refs: list[_PlacementRef] = []
        for slide_index, slide in enumerate(spec.slides):
            slide_height = max(1, slide.slide_size.height_px)
            for placement_index, placement in enumerate(slide.text_placements):
                text = self._clean_text(placement.text)
                if not text:
                    continue
                line_count = max(1, len(placement.text.splitlines()) or 1)
                text_length = len(text)
                family_type = "body" if line_count > 1 or text_length >= 24 else "label"
                font_name = placement.font_name.strip() or "default"
                refs.append(
                    _PlacementRef(
                        slide_index=slide_index,
                        placement_index=placement_index,
                        slide_height_px=slide_height,
                        placement=placement,
                        family=f"{font_name}:{family_type}",
                        line_count=line_count,
                        text_length=text_length,
                        top_ratio=max(0.0, placement.y / slide_height),
                    )
                )
        return refs

    def _build_tokens(self, refs: list[_PlacementRef], *, threshold: float) -> list[float]:
        sizes = sorted(ref.placement.font_size_pt for ref in refs if ref.placement.font_size_pt > 0)
        if not sizes:
            return []
        max_clusters = min(self._MAX_TOKENS_PER_FAMILY, len(sizes) // self._MIN_CLUSTER_SIZE)
        if max_clusters <= 1:
            return [self._round_step(median(sizes))]

        @lru_cache(maxsize=None)
        def best_partition(start: int, end: int, cluster_count: int) -> _PartitionResult | None:
            size_count = end - start
            if size_count < cluster_count * self._MIN_CLUSTER_SIZE:
                return None
            if cluster_count == 1:
                return _PartitionResult(intervals=((start, end),), score=0.0)

            best: _PartitionResult | None = None
            min_left_end = start + self._MIN_CLUSTER_SIZE
            max_left_end = end - self._MIN_CLUSTER_SIZE
            for split_index in range(min_left_end, max_left_end + 1):
                max_left_clusters = min(cluster_count - 1, (split_index - start) // self._MIN_CLUSTER_SIZE)
                min_left_clusters = max(1, cluster_count - ((end - split_index) // self._MIN_CLUSTER_SIZE))
                for left_cluster_count in range(min_left_clusters, max_left_clusters + 1):
                    left = best_partition(start, split_index, left_cluster_count)
                    right = best_partition(split_index, end, cluster_count - left_cluster_count)
                    if left is None or right is None:
                        continue
                    boundary = self._score_boundary(
                        sizes,
                        left.intervals[-1],
                        right.intervals[0],
                        threshold=threshold,
                    )
                    if boundary is None:
                        continue
                    score = left.score + right.score + boundary
                    if best is None or score > best.score:
                        best = _PartitionResult(
                            intervals=left.intervals + right.intervals,
                            score=score,
                        )
            return best

        for cluster_count in range(max_clusters, 0, -1):
            best = best_partition(0, len(sizes), cluster_count)
            if best is None:
                continue
            tokens = self._tokens_from_intervals(sizes, best.intervals)
            if len(tokens) == cluster_count:
                return tokens
        return [self._round_step(median(sizes))]

    def _score_boundary(
        self,
        sizes: list[float],
        lower_interval: tuple[int, int],
        upper_interval: tuple[int, int],
        *,
        threshold: float,
    ) -> float | None:
        lower_start, lower_end = lower_interval
        upper_start, upper_end = upper_interval
        lower = sizes[lower_start:lower_end]
        upper = sizes[upper_start:upper_end]
        lower_median = median(lower)
        upper_median = median(upper)
        ratio = upper_median / max(lower_median, 0.01)
        if ratio < threshold:
            return None

        lower_token = self._round_step(lower_median)
        upper_token = self._round_step(upper_median)
        if lower_token == upper_token:
            return None

        boundary_gap = upper[0] - lower[-1]
        if boundary_gap < 0:
            return None

        gap_ratio = upper[0] / max(lower[-1], 0.01)
        lower_spread = lower[-1] - lower[0]
        upper_spread = upper[-1] - upper[0]
        spread = lower_spread + upper_spread
        separation = boundary_gap / max(spread, 0.5)
        balance = min(len(lower), len(upper)) / max(len(lower), len(upper))
        return ratio + (gap_ratio * 0.1) + (separation * 0.35) + (balance * 0.05)

    def _tokens_from_intervals(self, sizes: list[float], intervals: tuple[tuple[int, int], ...]) -> list[float]:
        tokens: list[float] = []
        for start, end in intervals:
            token = self._round_step(median(sizes[start:end]))
            if not tokens or token != tokens[-1]:
                tokens.append(token)
        return tokens

    @classmethod
    def _round_step(cls, value: float) -> float:
        return math.floor((value / cls._STEP_PT) + 0.5) * cls._STEP_PT

    @staticmethod
    def _clean_text(text: str) -> str:
        return _SPACE_RE.sub(" ", text.replace("\n", " ").strip())


def normalize_presentation_fonts(spec: PresentationRenderSpec) -> PresentationRenderSpec:
    return FontNormalizer(dpi=spec.dpi).normalize(spec)
