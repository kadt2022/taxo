"""Ce qu'une analyse a lu, analyseur par analyseur (TAXO-COV-01, restitution).

Les langages presents viennent de l'inventaire ; ce que chaque analyseur lit vient du contrat de son
catalogue, celui qui est enregistre avec son execution. Un langage present qu'un analyseur ne lit pas est
dit « non analyse » par lui : jamais une absence constatee. Un contrat que Taxo ne connait plus ne lit rien
de connu. Aucun langage ni analyseur n'est nomme ici.
"""
from app.evaluations.domain.capability import LANGUAGE, WRITTEN_IN, languages_complete
from app.projects.application.queries import require_project
from app.projects.domain.project import ProjectError


def _languages(scan, facts):
    recorded = scan.result.get('languages')
    if recorded is not None:
        return tuple(recorded)
    # Une analyse anterieure a TAXO-COV-01 : ses langages sont relus dans ses faits, sans en reconstruire aucun.
    return tuple(value[len(LANGUAGE):] for value in facts.objects(scan.id, WRITTEN_IN)
                 if value and value.startswith(LANGUAGE))


def _recorded_contracts(scan, facts):
    """Le catalogue de chaque execution, tel que ses couvertures l'ont enregistre."""
    found = {}
    for fact in facts.query(scan.id, kind='COVERAGE'):
        produced = fact.get('produced_by', {})
        found.setdefault(produced.get('producer_id'), (produced.get('catalog_id'), produced.get('catalog_version')))
    return found


def analysis_coverage(project_id, scan_id, projects, scans, facts, contracts):
    """`contracts` : ce que lit chaque contrat de catalogue connu (`CatalogContracts`). Rend les langages de
    l'analyse, si l'inventaire a tout lu, et pour chaque analyseur ce qu'il lit et ce qu'il n'a pas lu."""
    require_project(projects, project_id)
    scan = scans.get(project_id, scan_id)
    if scan is None:
        raise ProjectError('NOT_FOUND', 'Analyse introuvable.')
    languages = _languages(scan, facts)
    evaluations = scan.result.get('evaluations') or []
    # Un resume anterieur a TAXO-COV-01 ne nomme pas son catalogue : il est relu, une fois, dans les couvertures.
    recorded = (_recorded_contracts(scan, facts)
                if any(item.get('catalog_id') is None for item in evaluations) else {})
    return {'languages': list(languages), 'complete': languages_complete(scan.result.get('evaluation_summary')),
            'evaluators': [_reading(item, languages, contracts, recorded) for item in evaluations]}


def _reading(item, languages, contracts, recorded):
    """Ce qu'un analyseur lit selon son contrat, et les langages presents qu'il n'a pas lus."""
    key = (item.get('catalog_id'), item.get('catalog_version'))
    if key[0] is None:
        key = recorded.get(item['evaluator_id'], (None, None))
    reads = contracts.reads(*key)
    return {'evaluator_id': item['evaluator_id'], 'status': item.get('status'),
            'contract': 'KNOWN' if reads.known else 'UNKNOWN',
            'reads': reads.listed(), 'unread': list(reads.unread(languages))}
