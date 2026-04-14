from __future__ import annotations

import json
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

from bananaslides.domain.models import OCRLine, OCRResult


_SPACE_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[^\w\s%./:+-]")


@dataclass(slots=True)
class TextCorrection:
    box_id: str
    original_text: str
    corrected_text: str
    expected_text: str | None
    match_score: float
    applied: bool


def load_expected_texts_from_deck_plan(deck_plan_path: Path, slide_number: int) -> list[str]:
    payload = json.loads(deck_plan_path.read_text(encoding="utf-8"))
    slides = payload.get("slides", [])
    for slide in slides:
        if int(slide.get("slide_number", -1)) != slide_number:
            continue
        candidates = [
            slide.get("title", ""),
            slide.get("subtitle", ""),
            *slide.get("on_slide_copy", []),
            *slide.get("quantified_points", []),
        ]
        return _dedupe_expected_texts(candidates)
    raise ValueError(f"Slide {slide_number} not found in deck plan: {deck_plan_path}")


def load_expected_texts_file(path: Path) -> list[str]:
    if path.suffix.lower() == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            return _dedupe_expected_texts(str(item) for item in payload)
        if isinstance(payload, dict) and isinstance(payload.get("texts"), list):
            return _dedupe_expected_texts(str(item) for item in payload["texts"])
        raise ValueError(f"Unsupported expected-text JSON shape: {path}")
    return _dedupe_expected_texts(path.read_text(encoding="utf-8").splitlines())


def correct_ocr_results(
    ocr_results: list[OCRResult],
    expected_texts: list[str],
    *,
    min_score: float = 0.74,
) -> tuple[list[OCRResult], list[TextCorrection]]:
    deduped_expected = _dedupe_expected_texts(expected_texts)
    used_indices: set[int] = set()
    corrected_results: list[OCRResult] = []
    corrections: list[TextCorrection] = []

    for result in ocr_results:
        original_text = _clean_display_text(result.text)
        if not original_text:
            corrected_results.append(result)
            corrections.append(
                TextCorrection(
                    box_id=result.box_id,
                    original_text=result.text,
                    corrected_text=result.text,
                    expected_text=None,
                    match_score=0.0,
                    applied=False,
                )
            )
            continue

        best_index = -1
        best_candidate: str | None = None
        best_score = 0.0
        for index, candidate in enumerate(deduped_expected):
            if index in used_indices:
                continue
            score = _similarity_score(original_text, candidate)
            if score > best_score:
                best_index = index
                best_candidate = candidate
                best_score = score

        if best_candidate is not None and best_score >= min_score:
            corrected = _apply_corrected_text(result, best_candidate)
            corrected_results.append(corrected)
            corrections.append(
                TextCorrection(
                    box_id=result.box_id,
                    original_text=result.text,
                    corrected_text=best_candidate,
                    expected_text=best_candidate,
                    match_score=best_score,
                    applied=True,
                )
            )
            used_indices.add(best_index)
            continue

        corrected_results.append(result)
        corrections.append(
            TextCorrection(
                box_id=result.box_id,
                original_text=result.text,
                corrected_text=result.text,
                expected_text=best_candidate,
                match_score=best_score,
                applied=False,
            )
        )

    return corrected_results, corrections


def _apply_corrected_text(result: OCRResult, corrected_text: str) -> OCRResult:
    corrected_lines = _clean_lines(corrected_text.splitlines())
    if result.lines:
        if len(result.lines) == 1 and len(corrected_lines) <= 1:
            lines = [
                OCRLine(
                    text=corrected_text,
                    bbox=result.lines[0].bbox,
                    confidence=result.lines[0].confidence,
                )
            ]
        elif len(corrected_lines) == len(result.lines):
            lines = [
                OCRLine(
                    text=text,
                    bbox=line.bbox,
                    confidence=line.confidence,
                )
                for text, line in zip(corrected_lines, result.lines, strict=True)
            ]
        else:
            lines = []
    else:
        lines = []

    return OCRResult(
        box_id=result.box_id,
        text=corrected_text,
        lines=lines,
        language=result.language,
        confidence=result.confidence,
    )


def _clean_display_text(text: str) -> str:
    return _SPACE_RE.sub(" ", text.replace("\n", " ").strip())


def _clean_lines(lines: list[str]) -> list[str]:
    return [line.strip() for line in lines if line.strip()]


def _normalise_for_match(text: str) -> str:
    text = _clean_display_text(text).casefold()
    text = _PUNCT_RE.sub("", text)
    return _SPACE_RE.sub(" ", text).strip()


def _token_set(text: str) -> set[str]:
    return {token for token in _normalise_for_match(text).split(" ") if token}


def _similarity_score(left: str, right: str) -> float:
    norm_left = _normalise_for_match(left)
    norm_right = _normalise_for_match(right)
    if not norm_left or not norm_right:
        return 0.0
    if norm_left == norm_right:
        return 1.0

    ratio = SequenceMatcher(a=norm_left, b=norm_right).ratio()
    left_tokens = _token_set(norm_left)
    right_tokens = _token_set(norm_right)
    if left_tokens and right_tokens:
        overlap = len(left_tokens & right_tokens) / max(len(left_tokens), len(right_tokens))
    else:
        overlap = 0.0

    digits_left = re.findall(r"\d+(?:\.\d+)?", norm_left)
    digits_right = re.findall(r"\d+(?:\.\d+)?", norm_right)
    digit_bonus = 0.0
    if digits_left and digits_left == digits_right:
        digit_bonus = 0.08

    containment_bonus = 0.0
    if norm_left in norm_right or norm_right in norm_left:
        containment_bonus = 0.05

    return min(1.0, ratio * 0.7 + overlap * 0.3 + digit_bonus + containment_bonus)


def _dedupe_expected_texts(items) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = _clean_display_text(str(item))
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(text)
    return cleaned
