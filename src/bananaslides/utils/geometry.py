from __future__ import annotations

EMU_PER_INCH = 914400
POINTS_PER_INCH = 72


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def pixels_to_emu(pixels: float, dpi: int = 96) -> int:
    return round((pixels / dpi) * EMU_PER_INCH)


def pixels_to_points(pixels: float, dpi: int = 96) -> float:
    return (pixels / dpi) * POINTS_PER_INCH


def bbox_bounds(points: list[list[float]]) -> tuple[float, float, float, float]:
    if not points:
        raise ValueError("Bounding box points must not be empty.")
    xs = [float(point[0]) for point in points]
    ys = [float(point[1]) for point in points]
    return min(xs), min(ys), max(xs), max(ys)
