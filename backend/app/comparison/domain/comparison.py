"""Comparing two analyses from their recorded facts (TAXO-01F).

Facts are compared by identity, evaluator by evaluator. A fact present on both sides is unchanged as a
fact; what may still differ between its occurrences (evidence, status, number of occurrences) is
reported as separate signals. Nothing is paired arbitrarily: occurrences are compared one to one only
when each side has exactly one.
"""
from dataclasses import dataclass

ADDED, REMOVED, MODIFIED = 'ADDED', 'REMOVED', 'MODIFIED'
EVIDENCE_CHANGED, STATUS_CHANGED = 'EVIDENCE_CHANGED', 'STATUS_CHANGED'
OCCURRENCE_COUNT_CHANGED, OCCURRENCES_CHANGED = 'OCCURRENCE_COUNT_CHANGED', 'OCCURRENCES_CHANGED'
CATEGORIES = (ADDED, REMOVED, MODIFIED, EVIDENCE_CHANGED, STATUS_CHANGED, OCCURRENCE_COUNT_CHANGED,
              OCCURRENCES_CHANGED)

ABSENT_BEFORE, ABSENT_AFTER = 'ABSENT_BEFORE', 'ABSENT_AFTER'
FAILED_BEFORE, FAILED_AFTER = 'FAILED_BEFORE', 'FAILED_AFTER'
NOT_SUPPORTED_BEFORE, NOT_SUPPORTED_AFTER = 'NOT_SUPPORTED_BEFORE', 'NOT_SUPPORTED_AFTER'
CATALOG_CHANGED = 'CATALOG_CHANGED'
REASONS = {
    ABSENT_BEFORE: "Absent de l'analyse de départ.",
    ABSENT_AFTER: "Absent de l'analyse d'arrivée.",
    FAILED_BEFORE: "Exécution en échec dans l'analyse de départ : ses faits ne sont pas comparés.",
    FAILED_AFTER: "Exécution en échec dans l'analyse d'arrivée : ses faits ne sont pas comparés.",
    NOT_SUPPORTED_BEFORE: ("Rien à lire pour cet analyseur dans l'analyse de départ : aucun fichier dans "
                           "les langages qu'il lit. Ses faits ne sont pas comparés ; ce n'est pas une absence "
                           "de changement."),
    NOT_SUPPORTED_AFTER: ("Rien à lire pour cet analyseur dans l'analyse d'arrivée : aucun fichier dans "
                          "les langages qu'il lit. Ses faits ne sont pas comparés ; ce n'est pas une absence "
                          "de changement."),
    CATALOG_CHANGED: 'Catalogue différent. Cause possible : évolution du producteur, pas du logiciel.',
}


@dataclass(frozen=True)
class Side:
    """What one analysis says about one producer: its executions, whether one of them failed, and whether
    it had anything to read (TAXO-COV-01: an unsupported side is never an absence of change)."""
    catalogs: frozenset
    versions: frozenset
    failed: bool
    supported: bool = True


@dataclass(frozen=True)
class Occurrence:
    id: int
    status: str
    validity: str
    evidence: tuple | None
    content: str = ''  # everything else the occurrence says: derivation, validation, reason, spelling


def comparability(before, after):
    """None when the producer's facts can be compared, else the reason why not."""
    if before is None:
        return ABSENT_BEFORE
    if after is None:
        return ABSENT_AFTER
    if before.failed:
        return FAILED_BEFORE
    if after.failed:
        return FAILED_AFTER
    if not before.supported:
        return NOT_SUPPORTED_BEFORE
    if not after.supported:
        return NOT_SUPPORTED_AFTER
    if before.catalogs != after.catalogs:
        return CATALOG_CHANGED
    return None


def pair_modified(removed, added):
    """Removed and added identities, with the assertions of one slot (kind, subject, relation) that changed.

    A slot with exactly one identity on each side is one modified fact (existing impact rule); anything
    else stays removed or added. `removed` and `added` map identity_hash to its slot (None if no slot).
    Returns (removed hashes, added hashes, [(before hash, after hash)]), each sorted.
    """
    by_slot = {}
    for side, identities in (('removed', removed), ('added', added)):
        for identity_hash, slot in identities.items():
            if slot is not None:
                by_slot.setdefault(slot, {'removed': [], 'added': []})[side].append(identity_hash)
    pairs = sorted((group['removed'][0], group['added'][0]) for group in by_slot.values()
                   if len(group['removed']) == 1 and len(group['added']) == 1)
    paired_removed, paired_added = {left for left, _ in pairs}, {right for _, right in pairs}
    return (sorted(set(removed) - paired_removed), sorted(set(added) - paired_added), pairs)


def signals(before, after):
    """Signals of an identity present on both sides; never pairs occurrences arbitrarily."""
    if len(before) != len(after):
        return [OCCURRENCE_COUNT_CHANGED]
    if len(before) == 1:
        found = []
        if before[0].evidence != after[0].evidence:
            found.append(EVIDENCE_CHANGED)
        if (before[0].status, before[0].validity) != (after[0].status, after[0].validity):
            found.append(STATUS_CHANGED)
        if before[0].content != after[0].content:
            found.append(OCCURRENCES_CHANGED)
        return found

    def signature(occurrence):
        return repr((occurrence.status, occurrence.validity, occurrence.evidence, occurrence.content))
    if sorted(map(signature, before)) != sorted(map(signature, after)):
        return [OCCURRENCES_CHANGED]
    return []
