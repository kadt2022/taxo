"""Ce qu'une analyse sait d'elle-meme (TAXO-ARCH-REF-01, tranche C2) : un seul foyer pour ce que TAXO-COV-01 a nomme.

Trois dimensions, jamais confondues : les langages presents (l'inventaire), ce que lit le contrat de chaque
analyseur (`Reads`) et ce qu'il a effectivement couvert (statut et couvertures). Les predicats qui en decoulent,
« a-t-il lu un langage present », « atteint-il la relation pour ce sujet », « quels langages restent non lus »,
« des langages peuvent-ils manquer », sont definis ici une fois ; le verdict, l'enveloppe et le voisinage les
lisent. Absence de preuve n'est jamais preuve d'absence. Aucun langage ni analyseur n'est nomme ici.
"""
from dataclasses import dataclass, field

from app.evaluations.domain.capability import Reads, unread

_SCOPES = ('repository', 'module', 'directory', 'file')
_TYPE = 'coverage_type'
ANALYSED = 'ANALYSED'


@dataclass(frozen=True)
class Analyzer:
    """Un analyseur de l'analyse : ce qu'il sait produire, s'il a abouti, et sa couverture.

    `reads` : ce que son contrat de catalogue lit pour produire ses relations (TAXO-COV-01) : independant du
    langage, ces langages, ou inconnu. `unsupported` : il n'avait rien a lire et n'a pas ete execute."""

    analyzer_id: str
    relations: frozenset
    failed: bool = False
    coverage: tuple = field(default=())
    reads: Reads = Reads.any()
    unsupported: bool = False

    def analysed(self):
        return [item for item in self.coverage if item[_TYPE] == ANALYSED]


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


def covers(coverage, reference):
    """Une couverture `ANALYSED` du depot inclut `reference` et ne l'exclut pas."""
    scope = coverage.get('scope', {})
    return (any(contains(item, reference) for item in scope.get('include', []))
            and not any(contains(item, reference) for item in scope.get('exclude', [])))


@dataclass(frozen=True)
class AnalysisKnowledge:
    """Les langages presents, si l'inventaire a tout lu, et les analyseurs tels que l'analyse les a vus."""

    languages: tuple = ()
    complete: bool = True
    analyzers: tuple = ()

    def capable(self, relation, subject):
        """Analyseurs qui savent etablir `relation` et dont le perimetre couvre `subject`."""
        found = []
        for analyzer in self.analyzers:
            if relation not in analyzer.relations:
                continue
            analysed = analyzer.analysed()
            if analyzer.failed or not analysed or any(covers(item, subject) for item in analysed):
                found.append(analyzer)
        return found

    def reaching(self, relation, subject=None):
        """Executions abouties, capables de `relation`, qui ont lu un langage present et dont la couverture
        `ANALYSED` englobe `subject` (ou existe, sans sujet) : celles qui peuvent justifier un « non trouve »."""
        found = []
        for analyzer in self.analyzers:
            if relation not in analyzer.relations or analyzer.failed or analyzer.unsupported:
                continue
            analysed = analyzer.analysed()
            if analysed and analyzer.reads.reads_present(self.languages) and (
                    subject is None or any(covers(item, subject) for item in analysed)):
                found.append(analyzer)
        return found

    def not_analysed(self, relation, needed=None, subject=None):
        """Les langages concernes qu'aucune execution capable de `relation` n'a lus (TAXO-COV-01) : ceux de
        `needed`, sinon tous les langages presents."""
        readers = [item.reads for item in self.reaching(relation, subject)]
        return unread(self.languages if needed is None else needed, readers)

    def languages_unknown(self, relation, subject=None):
        """L'inventaire n'a pas tout lu : des langages presents peuvent manquer. Seule une execution capable et
        independante du langage peut alors repondre de tout le depot."""
        return not self.complete and not any(item.reads.independent for item in self.reaching(relation, subject))
