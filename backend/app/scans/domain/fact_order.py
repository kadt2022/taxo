"""Stable, reconstructible adjacency keys; these are not new fact identities."""
import hashlib
import json
import unicodedata

import rfc8785

from app.facts.domain.identity import canonical_identity, _IDENTITY_DOMAIN


def adjacency_keys(fact):
    identity = hashlib.sha256(_IDENTITY_DOMAIN + rfc8785.dumps(canonical_identity(fact))).hexdigest()
    occurrence = hashlib.sha256(json.dumps(fact, sort_keys=True, ensure_ascii=False,
                                          separators=(',', ':')).encode()).hexdigest()
    def key(reference):
        # Hex is independent of database locale; '!' sorts before every hex digit (prefix first).
        ordered = unicodedata.normalize('NFC', reference or '').encode('utf-16-be').hex()
        return f'{ordered}!{identity}!{occurrence}'
    return key(fact.get('object')), key(fact.get('subject'))
