"""Stable, reconstructible adjacency keys; these are not new fact identities."""
import hashlib
import json
import unicodedata

import rfc8785

from app.facts.domain.identity import canonical_identity, _IDENTITY_DOMAIN


def occurrence_fingerprint(fact):
    """Fixed-size fingerprint of one submitted occurrence, the last tie-breaker of the order."""
    return hashlib.sha256(json.dumps(fact, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':')).encode()).hexdigest()


def order_key(reference, identity, occurrence):
    """Neighbour reference (NFC, UTF-16 order), then identity digest, then occurrence fingerprint."""
    # Hex is independent of database locale; '!' sorts before every hex digit (prefix first).
    ordered = unicodedata.normalize('NFC', reference or '').encode('utf-16-be').hex()
    return f'{ordered}!{identity}!{occurrence}'


def adjacency_keys(fact):
    identity = hashlib.sha256(_IDENTITY_DOMAIN + rfc8785.dumps(canonical_identity(fact))).hexdigest()
    occurrence = occurrence_fingerprint(fact)
    return order_key(fact.get('object'), identity, occurrence), order_key(fact.get('subject'), identity, occurrence)
