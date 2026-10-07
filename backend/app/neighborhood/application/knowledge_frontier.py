"""Ce qu'une Tuile ne peut pas montrer faute de connaissance ou de capacité (ARCHITECTURE § 9.3, TAXO-COV-01).

Lu dans le résumé de l'analyse, sans parcourir ses faits : la couverture de chaque analyseur des relations
suivies, ses lacunes, les relations qu'aucune exécution capable ne produit (frontière de contexte), et les
langages présents qu'aucune exécution capable n'a lus (frontière de connaissance).

Les lacunes locales (TAXO-01J) se lisent ensuite, sur la Tuile construite : une couverture non lue qui porte sur
un nœud rendu, ou sur un fichier cité dans une preuve d'un élément qui l'atteint. Une lecture par l'ancre du
sujet, bornée ; au-delà de la borne, rien n'est localisé et la Tuile le dit : la lacune reste à l'échelle de
l'analyse, où elle est toujours dite.
"""
from dataclasses import dataclass

from app.evaluations.domain.capability import UNREAD_COVERAGE, languages_complete
from app.knowledge.domain.knowledge import AnalysisKnowledge

_TYPE = 'coverage_type'
# Références dont la couverture locale est lue au plus : les nœuds et les fichiers cités par les preuves.
MAX_LOCAL_REFERENCES = 2000
FILE = 'file:'


@dataclass(frozen=True)
class AnalysisFrontier:
    coverage: list
    frontier: list
    capable: frozenset


def analysis_frontier(summary, root, relations) -> AnalysisFrontier:
    coverage, frontier, capabilities = _summaries(summary, relations)
    for relation in relations:
        if relation not in capabilities:
            frontier.append({'nature': 'CONTEXT', 'node': root, 'relation': relation,
                             'reason': 'NO_ANALYZER', 'count': {'kind': 'UNKNOWN'}})
    frontier += _unread_languages(summary, [relation for relation in relations if relation in capabilities])
    return AnalysisFrontier(coverage, frontier, frozenset(capabilities))


def _summaries(summary, relations):
    """Ce que le résumé de l'analyse dit des analyseurs des relations suivies : leur couverture, leurs
    lacunes, et les relations qu'ils rendent disponibles."""
    coverage, frontier, capabilities = [], [], set()
    for evaluation in summary.evaluations:
        identifier = evaluation['evaluator_id']
        produced = summary.catalogs.get(identifier, frozenset(evaluation.get('relations', {})))
        if not set(relations).intersection(produced):
            continue
        # TAXO-COV-01 : un analyseur qui n'avait rien a lire n'est pas une capacite de cette analyse.
        if evaluation['status'] != 'UNSUPPORTED':
            capabilities.update(produced)
        coverage.append({'producer': identifier, 'scope': 'ANALYSIS_SUMMARY',
                         'status': evaluation['status'], 'coverage': evaluation.get('coverage', [])})
        gaps = [item for item in evaluation.get('coverage', [])
                if item[_TYPE] in UNREAD_COVERAGE]
        if evaluation['status'] in ('FAILED', 'PARTIAL') or gaps:
            frontier.append(_knowledge('ANALYSIS_INCOMPLETE', producer=identifier))
    return coverage, frontier, capabilities


def _unread_languages(summary, relations):
    """Les langages presents qu'aucune execution capable n'a lus, relation par relation : ce qui s'y trouve
    est inconnu (TAXO-COV-01). Lus dans le resume de l'analyse, sans parcourir ses faits ; une analyse
    anterieure a TAXO-COV-01 les relit dans ses faits ; sans resume d'inventaire, rien n'en est dit."""
    result = summary.result
    present = result.get('languages')
    if present is None and 'evaluation_summary' in result:
        # Une analyse anterieure a TAXO-COV-01 : ses langages sont relus dans ses faits, comme pour les verdicts.
        present = summary.languages
    if present is None:
        return []
    knowledge = AnalysisKnowledge(present, languages_complete(result.get('evaluation_summary')),
                                  tuple(summary.summary_analyzers()))
    frontier = []
    for relation in relations:
        unread = knowledge.not_analysed(relation)
        if unread:
            frontier.append(_knowledge('NOT_ANALYSED', relation=relation, languages=list(unread)))
        if knowledge.languages_unknown(relation):
            frontier.append(_knowledge('LANGUAGES_UNKNOWN', relation=relation))
    return frontier


def _knowledge(reason, **fields):
    """Une frontiere de connaissance : ce que seule une capacite d'analyse amelioree ferait connaitre."""
    return {'nature': 'KNOWLEDGE', 'scope': 'ANALYSIS', **fields, 'reason': reason, 'count': {'kind': 'UNKNOWN'}}


def local_frontier(reader, scan_id, tile):
    """Les lacunes de connaissance rattachées aux nœuds de la Tuile, dans l'ordre des nœuds."""
    if not tile.known:
        return []
    order = {node.reference: index for index, node in enumerate(tile.nodes)}
    concerned = _concerned(tile, order)
    if len(concerned) > MAX_LOCAL_REFERENCES:
        return [_knowledge('LOCAL_COVERAGE_NOT_READ')]
    entries = {}
    for gap in reader.unread(scan_id, sorted(concerned)):
        for node in concerned[gap['subject']]:
            key = (order[node], gap['subject'], gap[_TYPE], gap['producer'] or '')
            entries[key] = {'nature': 'KNOWLEDGE', 'scope': 'NODE', 'node': node, 'subject': gap['subject'],
                            'reason': gap[_TYPE], 'producer': gap['producer'], 'count': {'kind': 'UNKNOWN'},
                            **({'causes': gap['reasons']} if gap.get('reasons') else {})}
    return [entries[key] for key in sorted(entries)]


def _concerned(tile, order):
    """Chaque référence dont une lacune concernerait un nœud rendu, et les nœuds qu'elle concerne : le nœud
    lui-même, et les fichiers cités par les preuves des éléments qui l'atteignent."""
    concerned = {reference: [reference] for reference in order}
    for element in tile.elements:
        fact = element.adjacent.fact
        reached = tile.request.steps[element.step].far_end(fact)
        if reached in order:
            for path in dict.fromkeys(proof['path'] for proof in fact.get('evidence', []) if proof.get('path')):
                concerned.setdefault(FILE + path, []).append(reached)
    return concerned
