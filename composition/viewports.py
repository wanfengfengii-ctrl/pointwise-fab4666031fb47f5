from dataclasses import dataclass


class ViewportError(ValueError):
    pass


@dataclass(frozen=True)
class Viewport:
    x0: int
    y0: int
    x1: int
    y1: int

    @property
    def width(self) -> int:
        return self.x1 - self.x0

    @property
    def height(self) -> int:
        return self.y1 - self.y0

    def bounds(self) -> list[int]:
        return [self.x0, self.y0, self.x1, self.y1]


def validate_viewport(value: object, width: int, height: int) -> Viewport:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        raise ViewportError('viewport needs four boundaries')
    if any(type(coordinate) is not int for coordinate in value):
        raise ViewportError('viewport boundaries must be integers')
    x0, y0, x1, y1 = value
    if not (0 <= x0 < x1 <= width and 0 <= y0 < y1 <= height):
        raise ViewportError('viewport must be nonempty and inside the revision')
    return Viewport(x0, y0, x1, y1)
