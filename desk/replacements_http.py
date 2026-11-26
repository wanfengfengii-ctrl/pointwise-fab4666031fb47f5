from desk.replacements import (
    ReplacementConflict, ReplacementStore, ReplacementTargetMissing,
)
from desk.session import is_label


def _integer(value: object) -> bool:
    return type(value) is int and 0 <= value <= 2**63 - 1


def handle_register_replacement(store: ReplacementStore, body: object) -> tuple[int, dict]:
    if not isinstance(body, dict):
        return 400, {'error': 'expected a replacement object'}
    session_id = body.get('session_id')
    position = body.get('position')
    screen_id = body.get('replacement_screen_id')
    request_id = body.get('request_id')
    if not all(is_label(label) for label in (session_id, position, screen_id, request_id)):
        return 400, {
            'error': 'session_id, position, replacement_screen_id and request_id '
                     'must be printable strings'
        }
    activation_pulse = body.get('activation_pulse')
    if not _integer(activation_pulse):
        return 400, {'error': 'activation_pulse must be a nonnegative integer'}
    try:
        replacement = store.register(session_id, position, screen_id,
                                     activation_pulse, request_id)
    except ReplacementTargetMissing as error:
        return 404, {'error': str(error)}
    except ReplacementConflict as error:
        return 409, {'error': str(error)}
    return 200, replacement.record()


def handle_get_replacement(store: ReplacementStore, replacement_id: int) -> tuple[int, dict]:
    replacement = store.get(replacement_id)
    if replacement is None:
        return 404, {'error': 'unknown replacement'}
    return 200, replacement.record()
