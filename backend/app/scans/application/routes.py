"""Les routes d'une analyse, lues dans les seuls faits de Taxo (TAXO-UI-02).

Pour chaque endpoint etabli (HANDLED_BY), la projection reunit ce que les evaluateurs ont conclu : la
methode qui le traite, l'application qui le sert (SERVED_BY), la regle qui le capture (MATCHED_BY, puis la
regle PERMITS_ALL ou AUTHORIZED_BY de la meme chaine de filtres), ses protections (PROTECTED_BY, par une regle
d'URL ou par `@PreAuthorize`), et chaque
zone non interpretee avec sa raison. Elle ne deduit rien : un etat n'est affiche que si un fait le porte.
"""
from app.evaluations.domain.capability import UNREAD_COVERAGE
from app.projects.application.queries import require_project
from app.projects.domain.project import ProjectError

ENDPOINTS = 'taxo.spring-api'
ENDPOINT = 'endpoint:'
EVALUATORS = ('taxo.spring-api', 'taxo.spring-boot', 'taxo.spring-security')
RELATIONS = ('HANDLED_BY', 'SERVED_BY', 'MATCHED_BY', 'PROTECTED_BY')
RULES = ('PERMITS_ALL', 'AUTHORIZED_BY')
# L'etat d'une route, du plus etabli au moins etabli : protegee, capturee par permitAll(), non interpretee.
PROTECTED, PERMITTED, NOT_INTERPRETED, NO_CONCLUSION = 'PROTECTED', 'PERMITS_ALL', 'NOT_INTERPRETED', 'NO_CONCLUSION'


def analysis_routes(project_id, scan_id, projects, scans, facts):
    require_project(projects, project_id)
    if scans.get(project_id, scan_id) is None:
        raise ProjectError('NOT_FOUND', 'Analyse introuvable.')
    by_relation = {relation: facts.query(scan_id, relation=relation) for relation in (*RELATIONS, *RULES)}
    gaps = [fact for evaluator in EVALUATORS
            for fact in facts.query(scan_id, evaluator_id=evaluator, kind='COVERAGE')
            if fact['coverage_type'] in UNREAD_COVERAGE]
    return project_routes(by_relation, gaps)


def project_routes(by_relation, gaps):
    """Les lignes du tableau des routes, et les zones ou des routes ont pu echapper a l'analyse."""
    grouped = {relation: _by_subject(items) for relation, items in by_relation.items()}
    rules = {}
    for relation in RULES:
        for fact in by_relation.get(relation, []):
            rules.setdefault((fact['subject'], fact['qualifiers'].get('filter_chain')), []).append(fact)
    endpoint_gaps = {}
    unestablished = []
    for fact in gaps:
        entry = {'subject': fact['subject'], 'type': fact['coverage_type'], 'reason': fact.get('reason', ''),
                 'evaluator': fact.get('produced_by', {}).get('producer_id', '')}
        if fact['subject'].startswith(ENDPOINT):
            endpoint_gaps.setdefault(fact['subject'], []).append(entry)
        elif entry['evaluator'] == ENDPOINTS:
            unestablished.append(entry)
    routes = [_route(endpoint, grouped, rules, endpoint_gaps.get(endpoint, []))
              for endpoint in sorted(grouped.get('HANDLED_BY', {}), key=_order)]
    return {'routes': routes, 'unestablished': sorted(unestablished, key=lambda item: item['subject'])}


def _route(endpoint, grouped, rules, gaps):
    matched = grouped.get('MATCHED_BY', {}).get(endpoint, [])
    applied = [rule for fact in matched
               for rule in rules.get((fact['object'], fact['qualifiers'].get('filter_chain')), [])]
    protections = grouped.get('PROTECTED_BY', {}).get(endpoint, [])
    if protections:
        state = PROTECTED
    elif any(rule['relation'] == 'PERMITS_ALL' for rule in applied):
        state = PERMITTED
    else:
        state = NOT_INTERPRETED if gaps else NO_CONCLUSION
    verb, _, path = endpoint.removeprefix(ENDPOINT).partition(' ')
    return {'endpoint': endpoint, 'verb': verb, 'path': path, 'state': state,
            'handlers': grouped['HANDLED_BY'][endpoint], 'applications': grouped.get('SERVED_BY', {}).get(endpoint, []),
            'matched': matched, 'rules': applied, 'protections': protections, 'gaps': gaps}


def _by_subject(items):
    found = {}
    for fact in items:
        found.setdefault(fact['subject'], []).append(fact)
    return found


def _order(endpoint):
    verb, _, path = endpoint.removeprefix(ENDPOINT).partition(' ')
    return path, verb
