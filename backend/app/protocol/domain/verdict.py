"""Verdict de Taxo sur une affirmation structuree (ARCHITECTURE § 12.4) : Minia propose, Taxo prouve.

- `CONFIRMED` : un fait etabli affirme la meme chose.
- `REFUTED` : un fait etabli la contredit, sur une relation que le vocabulaire declare exclusive (un
  commit n'a qu'un auteur, un fichier qu'un langage). La refutation par un fait `ABSENCE` attend le
  premier analyseur qui en produit : aucun n'en produit encore, et la correspondance entre un motif
  d'absence et une affirmation sera fixee avec lui.
- `NOT_PROVEN` : ni l'un ni l'autre, avec l'une des trois fins de parcours d'ARCHITECTURE § 5.

« Non trouve » n'est jamais « faux ».
"""
from dataclasses import dataclass, field

from app.evaluations.domain.capability import unread

CONFIRMED, REFUTED, NOT_PROVEN = 'CONFIRMED', 'REFUTED', 'NOT_PROVEN'
NOT_FOUND_IN_ANALYSED_SCOPE = 'NOT_FOUND_IN_ANALYSED_SCOPE'
NOT_INTERPRETED = 'NOT_INTERPRETED'
NOT_ANALYSED = 'NOT_ANALYSED'

# Relations dont un sujet n'a qu'un objet : un autre objet etabli contredit l'affirmation.
EXCLUSIVE = frozenset({'AUTHORED_BY', 'WRITTEN_IN'})
_UNREADABLE = frozenset({'NOT_INTERPRETED', 'READ_ERROR'})
_SCOPES = ('repository', 'module', 'directory', 'file')
_TYPE = 'coverage_type'


@dataclass(frozen=True)
class Analyzer:
    """Un analyseur de l'analyse : ce qu'il sait produire, s'il a abouti, et sa couverture.

    `languages` : ce que son catalogue lit pour produire ses relations (TAXO-COV-01), `None` s'il est
    independant du langage. `unsupported` : il n'avait rien a lire et n'a pas ete execute."""

    analyzer_id: str
    relations: frozenset
    failed: bool = False
    coverage: tuple = field(default=())
    languages: frozenset | None = None
    unsupported: bool = False

    def reads_present(self, present):
        """A-t-il lu quelque chose ? Lie a des langages, il faut qu'un d'eux soit present."""
        return self.languages is None or bool(self.languages & set(present))


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
        analysed = [item for item in analyzer.coverage if item[_TYPE] == 'ANALYSED']
        if analyzer.failed or not analysed or any(_covers(item, subject) for item in analysed):
            found.append(analyzer)
    return found


def reaching(analyzers, relation, present, subject=None):
    """Executions abouties, capables de `relation`, qui ont lu un langage present et dont la couverture
    `ANALYSED` englobe `subject` (ou existe, sans sujet) : celles qui peuvent justifier un « non trouve »."""
    found = []
    for analyzer in analyzers:
        if relation not in analyzer.relations or analyzer.failed or analyzer.unsupported:
            continue
        analysed = [item for item in analyzer.coverage if item[_TYPE] == 'ANALYSED']
        if analysed and analyzer.reads_present(present) and (subject is None or any(_covers(item, subject)
                                                                                     for item in analysed)):
            found.append(analyzer)
    return found


def not_analysed(analyzers, relation, present, needed=None, subject=None):
    """Les langages concernes qu'aucune execution capable de `relation` n'a lus (TAXO-COV-01)."""
    readers = [None if item.languages is None else item.languages
               for item in reaching(analyzers, relation, present, subject)]
    return unread(present if needed is None else needed, readers)


def _unreadable(analyzer, references):
    return analyzer.failed or any(item[_TYPE] in _UNREADABLE and item['subject'] in references
                                  for item in analyzer.coverage)


def judge(claim, established, analyzers, present=(), needed=None):
    """Verdict sur `claim` ({subject, relation, object?}) d'apres les faits etablis `established` de meme
    sujet et relation, et les analyseurs de l'analyse.

    `present` : les langages de l'analyse ; `needed` : ceux ou le sujet aurait pu etre etabli (ceux de
    son fichier, sinon tous les langages presents : le sujet n'a pas a exister dans le graphe). Un « non
    trouve » exige que chacun ait ete lu par une execution capable de la relation (TAXO-COV-01)."""
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
    if not reaching(analyzers, relation, present, claim['subject']) or not_analysed(
            analyzers, relation, present, needed, claim['subject']):
        return Verdict(NOT_PROVEN, NOT_ANALYSED)
    return Verdict(NOT_PROVEN, NOT_FOUND_IN_ANALYSED_SCOPE)
