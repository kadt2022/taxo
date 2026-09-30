"""A fact split into its identity and its occurrence in one analysis, then rebuilt (TAXO-01E).

The identity is shared by every analysis. The occurrence keeps what belongs to this analysis:
status, validity, producer, evidence and the remaining contract fields. The snapshot, and the
repository and commit of each evidence, are those of the analysis: they are not repeated. A split
is only accepted if rebuilding it gives back exactly the submitted fact.
"""
import hashlib
import json
from dataclasses import dataclass

import rfc8785

from app.facts.domain.identity import _IDENTITY_DOMAIN, _IDENTITY_FIELDS, canonical_identity

EVIDENCE_FIELDS = ('path', 'line_start', 'line_end', 'symbol', 'method', 'content_hash', 'object')
_OCCURRENCE_FIELDS = {'snapshot', 'produced_by', 'evidence', 'status', 'validity'}


class OccurrenceError(ValueError):
    """The fact cannot be kept without loss or without contradicting its analysis."""


@dataclass(frozen=True)
class Occurrence:
    identity_hash: str
    identity: dict
    raw_identity: dict | None
    status: str
    validity: str
    evidence: tuple[dict, ...] | None
    details: dict


def identity_hash(identity):
    return 'sha256:' + hashlib.sha256(_IDENTITY_DOMAIN + rfc8785.dumps(identity)).hexdigest()


def same(left, right):
    """Strict JSON equality: 1 and 1.0, or 0.0 and -0.0, are different spellings."""
    return _spelling(left) == _spelling(right)


def _spelling(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'))


def _identity_values(fact):
    return {key: fact[key] for key in _IDENTITY_FIELDS[fact['kind']] if key in fact}


def _stated(identity):
    """Identity fields as a fact states them: the coverage producer lives in produced_by."""
    return {key: value for key, value in identity.items() if key != 'producer_id'}


def _evidence_of(fact, snapshot):
    if 'evidence' not in fact:
        return None
    evidence = []
    for item in fact['evidence']:
        if item.get('repository') != snapshot['repository'] or item.get('commit') != snapshot['commit']:
            raise OccurrenceError("Une preuve ne vient pas de l'instantané de l'analyse.")
        if not set(item) <= {'repository', 'commit', *EVIDENCE_FIELDS}:
            raise OccurrenceError('Une preuve porte un champ que la mémoire ne sait pas conserver.')
        evidence.append({key: value for key, value in item.items() if key not in ('repository', 'commit')})
    return tuple(evidence)


def split(fact, snapshot):
    if not isinstance(fact, dict) or fact.get('kind') not in _IDENTITY_FIELDS:
        raise OccurrenceError('Nature de fait inconnue.')
    if fact.get('snapshot') != snapshot:
        raise OccurrenceError("L'instantané du fait n'est pas celui de l'analyse.")
    if not isinstance(fact.get('produced_by'), dict):
        raise OccurrenceError('Le fait ne nomme pas son producteur.')
    # Stored in its RFC 8785 form, so the shared row never depends on which fact came first.
    identity = json.loads(rfc8785.dumps(canonical_identity(fact)))
    raw = _identity_values(fact)
    evidence = _evidence_of(fact, snapshot)
    details = {key: value for key, value in fact.items() if key not in _OCCURRENCE_FIELDS and key not in raw}
    occurrence = Occurrence(identity_hash(identity), identity, None if same(raw, _stated(identity)) else raw,
                            fact.get('status'), fact.get('validity'), evidence, details)
    if not same(rebuild(occurrence, snapshot, fact['produced_by']), fact):
        raise OccurrenceError('Le fait ne peut pas être conservé sans perte.')
    return occurrence


def rebuild(occurrence, snapshot, produced_by):
    fact = {**(occurrence.raw_identity or _stated(occurrence.identity)), **occurrence.details,
            'status': occurrence.status, 'validity': occurrence.validity,
            'snapshot': dict(snapshot), 'produced_by': dict(produced_by)}
    if occurrence.evidence is not None:
        fact['evidence'] = [{'repository': snapshot['repository'], 'commit': snapshot['commit'], **item}
                            for item in occurrence.evidence]
    return fact
