"""Cross-platform sans-serif font lookup for the Pillow-drawn check images.

DejaVu Sans is preferred everywhere so Linux and macOS renders match; install
it on macOS with `brew install --cask font-dejavu`. Arial/Helvetica are the
macOS fallbacks, and Pillow's built-in bitmap font is the last resort.
"""
from pathlib import Path

from PIL import ImageFont

_REGULAR = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/TTF/DejaVuSans.ttf",
    "~/Library/Fonts/DejaVuSans.ttf",
    "/Library/Fonts/DejaVuSans.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/Library/Fonts/Arial.ttf",
]
_BOLD = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    "~/Library/Fonts/DejaVuSans-Bold.ttf",
    "/Library/Fonts/DejaVuSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
]


def font_path(bold=False):
    """Return the first installed candidate font path, or None."""
    for candidate in _BOLD if bold else _REGULAR:
        path = Path(candidate).expanduser()
        if path.is_file():
            return str(path)
    return None


def load_font(size, bold=False):
    path = font_path(bold)
    if path is None:
        return ImageFont.load_default(size)
    return ImageFont.truetype(path, size)
