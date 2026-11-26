from artwork.pixels import PixelGrid
from composition.viewports import Viewport


def render_viewport(source: PixelGrid, viewport: Viewport) -> PixelGrid:
    return tuple(
        row[viewport.x0:viewport.x1]
        for row in source[viewport.y0:viewport.y1]
    )
