from bananaslides.utils.geometry import pixels_to_emu, pixels_to_points
from bananaslides.utils.text import contains_korean, count_non_empty_lines


def test_contains_korean() -> None:
    assert contains_korean("한글 title")
    assert not contains_korean("English title")


def test_count_non_empty_lines() -> None:
    assert count_non_empty_lines("a\n\nb") == 2
    assert count_non_empty_lines("") == 1


def test_pixel_conversions_are_positive() -> None:
    assert pixels_to_emu(96) == 914400
    assert pixels_to_points(96) == 72
