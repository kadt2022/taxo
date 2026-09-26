"""Verdict de Taxo sur une affirmation structuree (ADR 0009, section 6) : Minia propose, Taxo prouve.

- `CONFIRMED` : un fait etabli affirme la meme chose.
- `REFUTED` : un fait etabli la contredit, sur une relation que le vocabulaire declare exclusive (un
  commit n'a qu'un auteur, un fichier qu'un langage). La refutation par un fait `ABSENCE` attend le
  premier analyseur qui en produit : aucun n'en produit encore, et la correspondance entre un motif
  d'absence et une affirmation sera fixee avec lui.
- `NOT_PROVEN` : ni l'un ni l'autre, avec l'une des trois fins de parcours de l'ADR 0002.

« Non trouve » n'est jamais « faux ».
"""
from dataclasses import dataclass, field

CONFIRMED, REFUTED, NOT_PROVEN = 'CONFIRMED', 'REFUTED', 'NOT_PROVEN'
NOT_FOUND_IN_ANALYSED_SCOPE = 'NOT_FOUND_IN_ANALYSED_SCOPE'
NOT_INTERPRETED = 'NOT_INTERPRETED'
NOT_ANALYSED = 'NOT_ANALYSED'

# Relations dont un sujet n'a qu'un objet : un autre objet etabli contredit l'affirmation.
EXCLUSIVE = frozenset({'AUTHORED_BY', 'WRITTEN_IN'})
_UNREADABLE = frozenset({'NOT_INTERPRETED', 'READ_ERROR'})
_SCOPES = ('repository', 'module', 'directory', 'file')


@dataclass(frozen=True)
class Analyzer:
    """Un analyseur de l'analyse : ce qu'il sait produire, s'il a abouti, et sa couverture."""

    analyzer_id: str
    relations: frozenset
    failed: bool = False
    coverage: tuple = field(default=())


@dataclass(frozen=True)
class Verdict:
    verdict: str
    reason: str | None = None
    facts: tuple = ()


def contains(scope, reference):
    """Le perimetre `scope` (repository, module, directory, file) englobe-t-il `reference` ?"""
    kind, _, key = scope.partition(':')
    if scope == reference:
        return True
    if kind == 'repository':
        # Un depot contient ses entites, jamais un autre depot.
        return not reference.startswith('repository:')
    if kind == 'directory':
        _, _, target = reference.partition(':')
        return reference.split(':', 1)[0] in _SCOPES[2:] and target.startswith(key.rstrip('/') + '/')
    return False


def _covers(coverage, reference):
    """Une couverture `ANALYSED` du depot inclut `reference` et ne l'exclut pas."""
    scope = coverage.get('scope', {})
    return (any(contains(item, reference) for item in scope.get('include', []))
            and not any(contains(item, reference) for item in scope.get('exclude', [])))


def capable(analyzers, relation, subject):
    """Analyseurs qui savent etablir `relation` et dont le perimetre couvre `subject`."""
    found = []
    for analyzer in analyzers:
        if relation not in analyzer.relations:
            continue
        analysed = [item for item in analyzer.coverage if item['coverage_type'] == 'ANALYSED']
        if analyzer.failed or not analysed or any(_covers(item, subject) for item in analysed):
            found.append(analyzer)
    return found


def _unreadable(analyzer, references):
    return analyzer.failed or any(item['coverage_type'] in _UNREADABLE and item['subject'] in references
                                  for item in analyzer.coverage)


def judge(claim, established, analyzers):
    """Verdict sur `claim` ({subject, relation, object?}) d'apres les faits etablis `established` de meme
    sujet et relation, et les analyseurs de l'analyse."""
    relation, target = claim['relation'], claim.get('object')
    same = tuple(fact for fact in established if fact.get('object') == target)
    if same:
        return Verdict(CONFIRMED, facts=same)
    if relation in EXCLUSIVE and target is not None:
        other = tuple(fact for fact in established if fact.get('object') not in (None, target))
        if other:
            return Verdict(REFUTED, facts=other)
    able = capable(analyzers, relation, claim['subject'])
    if not able:
        return Verdict(NOT_PROVEN, NOT_ANALYSED)
    references = {claim['subject'], target} - {None}
    if any(_unreadable(analyzer, references) for analyzer in able):
        return Verdict(NOT_PROVEN, NOT_INTERPRETED)
    return Verdict(NOT_PROVEN, NOT_FOUND_IN_ANALYSED_SCOPE)
