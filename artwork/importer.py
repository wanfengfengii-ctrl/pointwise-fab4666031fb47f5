from artwork.catalog import ArtCatalog, ArtRevision
from artwork.pixels import freeze_pixels


def import_artwork(catalog: ArtCatalog, art_id: object, pixels: object) -> ArtRevision:
    if not isinstance(art_id, str) or not art_id.strip() or not art_id.isprintable():
        raise ValueError('art_id must be a nonempty printable string')
    return catalog.append_revision(art_id, freeze_pixels(pixels))
