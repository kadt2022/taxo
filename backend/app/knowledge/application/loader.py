"""Construire ce qu'une analyse sait d'elle-meme, depuis ce qu'elle a enregistre (TAXO-ARCH-REF-01, tranche C2).

Une analyse anterieure a TAXO-COV-01 n'enregistre pas ses langages : ils sont relus dans ses faits `WRITTEN_IN`,
sans rien reconstruire. Les analyseurs se lisent de deux facons, nommees ici et nulle part ailleurs :

- depuis ses couvertures (`from_coverage`) : ce que lisent le verdict et l'enveloppe, perimetres compris ;
- depuis son resume (`from_summary`) : ce que lit le voisinage, qui reste borne et ne parcourt aucun fait.

Dans les deux cas, une couverture se juge selon le contrat de catalogue de son producteur, jamais selon le
catalogue actuel de son analyseur.
"""
from app.evaluations.domain.capability import WRITTEN_IN, Reads, languages_in, present_languages
from app.knowledge.domain.knowledge import Analyzer

_LANGUAGES = 'languages'
_TYPE = 'coverage_type'


def recorded_languages(scan):
    """Les langages enregistres avec l'analyse ; `None` pour une analyse anterieure a TAXO-COV-01."""
    recorded = scan.result.get(_LANGUAGES)
    return None if recorded is None else tuple(recorded)


def analysis_languages(scan, facts):
    """Les langages de l'analyse : enregistres avec elle, sinon relus dans ses faits."""
    recorded = recorded_languages(scan)
    if recorded is not None:
        return recorded
    if hasattr(facts, 'objects'):
        return languages_in(facts.objects(scan.id, WRITTEN_IN))
    return present_languages(facts.query(scan.id, relation=WRITTEN_IN, kind='ASSERTION'))


def _relations(evaluation, catalogs):
    return catalogs.get(evaluation['evaluator_id'], frozenset(evaluation.get('relations', {})))


def _catalog(fact):
    produced = fact.get('produced_by', {})
    return produced.get('catalog_id'), produced.get('catalog_version')


def from_coverage(evaluations, coverage, catalogs, read_contract):
    """Les analyseurs d'apres leurs couvertures enregistrees : `catalogs` donne les relations de chaque
    analyseur, `read_contract(catalog_id, catalog_version)` ce que lit un contrat, demande seulement pour un
    analyseur qui a des couvertures. Un contrat de catalogue inconnu ne justifie aucun « non trouve » : il ne
    lit rien de connu."""
    found = []
    for item in evaluations:
        identifier = item['evaluator_id']
        own = tuple(fact for fact in coverage if fact.get('produced_by', {}).get('producer_id') == identifier)
        # Une seule regle si plusieurs executions s'y melent : leur contrat commun, sinon inconnu.
        reads = Reads.combined([read_contract(*key) for key in dict.fromkeys(_catalog(fact) for fact in own)],
                               Reads.unknown())
        found.append(Analyzer(identifier, _relations(item, catalogs), item.get('status') == 'FAILED', own, reads,
                              item.get('status') == 'UNSUPPORTED'))
    return found


def from_summary(evaluations, catalogs, reads_of, executions):
    """Les analyseurs tels que le resume de l'analyse les decrit : statut, relations, types de couverture et
    contrat de catalogue. `reads_of` lit le contrat qu'une execution nomme ; `executions` rend celles qui sont
    enregistrees, lues seulement si un resume anterieur ne nomme pas son catalogue."""
    found, recorded = [], None
    for evaluation in evaluations:
        identifier = evaluation['evaluator_id']
        # Le resume ne garde que les types de couverture : assez pour savoir si l'execution a analyse.
        coverage = tuple({_TYPE: item[_TYPE]} for item in evaluation.get('coverage', []))
        if evaluation.get('catalog_id') is None and recorded is None:
            recorded = recorded_contracts(executions(), reads_of)
        reads = (recorded.get(identifier, Reads.unknown()) if evaluation.get('catalog_id') is None
                 else reads_of(evaluation))
        found.append(Analyzer(identifier, _relations(evaluation, catalogs), evaluation['status'] == 'FAILED',
                              coverage, reads, evaluation['status'] == 'UNSUPPORTED'))
    return found


def recorded_contracts(executions, reads_of):
    """Un resume anterieur a TAXO-COV-01 ne nomme pas son catalogue : chaque execution est lue selon le contrat
    enregistre avec elle, celui que portent ses couvertures et que lisent les verdicts, jamais selon le
    catalogue actuel de son analyseur. Une lecture bornee : une ligne par execution, aucun fait. Sans
    execution enregistree, son contrat est inconnu : il ne lit rien de connu. Une analyse n'a qu'une execution
    par evaluateur (par construction, pas par la base) ; si plusieurs executions d'un producteur nommaient des
    contrats differents, aucun ne serait choisi a la place des autres : le contrat serait inconnu."""
    found = {}
    for execution in executions:
        if execution.producer_type == 'EVALUATOR':
            found.setdefault(execution.producer_id, []).append(reads_of(vars(execution)))
    return {producer: Reads.combined(readings, Reads.unknown()) for producer, readings in found.items()}
