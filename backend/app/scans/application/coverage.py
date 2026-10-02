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
    """`contracts` : (catalog_id, catalog_version) -> langages lus, `None` pour un catalogue independant du
    langage. Rend les langages de l'analyse, si l'inventaire a tout lu, et pour chaque analyseur ce qu'il lit
    et ce qu'il n'a pas lu."""
    require_project(projects, project_id)
    scan = scans.get(project_id, scan_id)
    if scan is None:
        raise ProjectError('NOT_FOUND', 'Analyse introuvable.')
    languages = _languages(scan, facts)
    evaluations = scan.result.get('evaluations') or []
    recorded = None
    entries = []
    for item in evaluations:
        key = (item.get('catalog_id'), item.get('catalog_version'))
        if key[0] is None:
            recorded = _recorded_contracts(scan, facts) if recorded is None else recorded
            key = recorded.get(item['evaluator_id'], (None, None))
        known = key in contracts
        reads = contracts[key] if known else ()
        entries.append({'evaluator_id': item['evaluator_id'], 'status': item.get('status'),
                        'contract': 'KNOWN' if known else 'UNKNOWN',
                        'reads': None if reads is None else sorted(reads),
                        'unread': [] if reads is None else sorted(set(languages) - set(reads))})
    return {'languages': list(languages), 'complete': languages_complete(scan.result.get('evaluation_summary')),
            'evaluators': entries}
