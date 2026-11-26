from dataclasses import asdict

from artwork.catalog import ArtCatalog
from artwork.importer import import_artwork


def handle_import_art(catalog: ArtCatalog, body: object) -> tuple[int, dict]:
    if not isinstance(body, dict):
        return 400, {'error': 'expected an artwork object'}
    try:
        revision = import_artwork(catalog, body.get('art_id'), body.get('pixels'))
    except ValueError as error:
        return 400, {'error': str(error)}
    return 200, {
        'revision_id': revision.revision_id,
        'art_id': revision.art_id,
        'width': revision.width,
        'height': revision.height,
    }


def handle_get_revision(catalog: ArtCatalog, revision_id: int) -> tuple[int, dict]:
    revision = catalog.get_revision(revision_id)
    if revision is None:
        return 404, {'error': 'unknown revision'}
    return 200, asdict(revision)
