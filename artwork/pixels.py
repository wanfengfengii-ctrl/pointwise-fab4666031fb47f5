from typing import TypeAlias

RGB: TypeAlias = tuple[int, int, int]
PixelGrid: TypeAlias = tuple[tuple[RGB, ...], ...]


class PixelFormatError(ValueError):
    pass


def freeze_pixels(value: object) -> PixelGrid:
    if not isinstance(value, (list, tuple)) or not value:
        raise PixelFormatError('pixels must contain at least one row')
    rows = []
    width = None
    for row in value:
        if not isinstance(row, (list, tuple)) or not row:
            raise PixelFormatError('pixel rows must be nonempty')
        if width is None:
            width = len(row)
        if len(row) != width:
            raise PixelFormatError('pixel rows must have equal widths')
        colors = []
        for pixel in row:
            if not isinstance(pixel, (list, tuple)) or len(pixel) != 3:
                raise PixelFormatError('each pixel must have three RGB components')
            if any(type(component) is not int or not 0 <= component <= 255 for component in pixel):
                raise PixelFormatError('RGB components must be integers from 0 to 255')
            colors.append((pixel[0], pixel[1], pixel[2]))
        rows.append(tuple(colors))
    return tuple(rows)


def pixel_dimensions(grid: PixelGrid) -> tuple[int, int]:
    return len(grid[0]), len(grid)
