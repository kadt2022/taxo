import re
from .errors import FactValidationError, ValidationIssue
from .identity import _IDENTITY_FIELDS, _normalize_identity_value

# Reserved type:key syntax of entity references; never read as a literal expression.
_REFERENCE_SYNTAX = re.compile(r'[a-z][a-z0-9-]*:')

# Source/target types and permitted statuses are the v1 relation vocabulary.
RELATIONS = {
    'CONTAINS': ({'repository', 'module', 'file', 'symbol'}, {'module', 'file', 'symbol'}, {'OBSERVED'}),
    'WRITTEN_IN': ({'file'}, {'language'}, {'OBSERVED'}),
    'USES_TECHNOLOGY': ({'repository', 'module'}, {'technology'}, {'OBSERVED'}),
    'DECLARED_BY': ({'technology'}, {'file'}, {'OBSERVED'}),
    'ANNOTATED_WITH': ({'symbol'}, {'annotation'}, {'OBSERVED'}),
    # Appels et declarations Java (ARCHITECTURE § 14, TAXO-01K) : CALLS designe une declaration choisie par une regle
    # nommee, jamais le corps execute ; IMPLEMENTS est ecrit entre types et deduit entre methodes.
    'CALLS': ({'symbol'}, {'symbol'}, {'INFERRED'}),
    'IMPLEMENTS': ({'symbol'}, {'symbol'}, {'OBSERVED', 'INFERRED'}),
    'EXTENDS': ({'symbol'}, {'symbol'}, {'OBSERVED'}),
    'TYPED_AS': ({'symbol'}, {'symbol'}, {'OBSERVED'}),
    'DISPATCHES_TO': ({'symbol'}, {'symbol'}, {'INFERRED'}),
    'HANDLED_BY': ({'endpoint'}, {'symbol'}, {'OBSERVED'}),
    'ACCEPTS': ({'endpoint'}, {'symbol'}, {'OBSERVED'}),
    'RETURNS': ({'endpoint'}, {'symbol'}, {'OBSERVED'}),
    'PERMITS_ALL': ({'route-pattern'}, set(), {'OBSERVED'}),
    'AUTHORIZED_BY': ({'route-pattern'}, {'symbol'}, {'OBSERVED'}),
    'MATCHED_BY': ({'endpoint'}, {'route-pattern'}, {'INFERRED'}),
    'PROTECTED_BY': ({'endpoint'}, {'symbol', 'policy-rule'}, {'INFERRED', 'HUMAN_VALIDATED'}),
    # Historique Git (ARCHITECTURE § 7.2) : un commit, son auteur, ses parents et les fichiers qu'il change.
    'HAS_COMMIT': ({'repository'}, {'commit'}, {'OBSERVED'}),
    'AUTHORED_BY': ({'commit'}, {'person'}, {'OBSERVED'}),
    'CHILD_OF': ({'commit'}, {'commit'}, {'OBSERVED'}),
    'CHANGES': ({'commit'}, {'file'}, {'OBSERVED'}),
    # Structure du depot (ARCHITECTURE § 7.5) : modules et leurs dependances, unites deployables.
    'DEPENDS_ON': ({'module'}, {'module'}, {'OBSERVED'}),
    'BUILT_FROM': ({'application'}, {'module'}, {'OBSERVED'}),
    # L'application qui expose une route : deduite du classpath et du balayage (E1, tranche 2).
    'SERVED_BY': ({'endpoint'}, {'application'}, {'INFERRED'}),
}
# Couples sujet -> objet d'une relation dont les types ne se combinent pas librement : un fichier ou un symbole ne
# contient que des symboles, et un symbole n'est contenu que par un fichier ou un autre symbole.
RELATION_PAIRS = {
    'CONTAINS': {(subject, target) for subject in ('repository', 'module') for target in ('module', 'file')}
    | {('file', 'symbol'), ('symbol', 'symbol')},
}
# Le site d'appel est la preuve directe d'un CALLS, et il ne prouve rien d'autre.
CALL_SITE = 'call-site'
# Un commit est designe par son identifiant Git complet, comme l'instantane (ARCHITECTURE § 7.2).
_COMMIT_KEY = re.compile(r'(?:[0-9a-f]{40}|[0-9a-f]{64})')
_GIT_RELATIONS = {'HAS_COMMIT', 'AUTHORED_BY', 'CHILD_OF', 'CHANGES'}
_STATUS_PRODUCERS = {
    'OBSERVED': {'EVALUATOR'},
    'INFERRED': {'EVALUATOR', 'PROJECTION'},
    'HUMAN_VALIDATED': {'HUMAN'},
}
def validate_semantics(fact, rules, *, submission=True):
    issues = []

    def reject(code, path, message):
        issues.append(ValidationIssue(code, path, message))

    if submission and fact['validity'] != 'VALID':
        reject('SUBMISSION_VALIDITY', '/validity', 'Only the memory can set a validity other than VALID.')
    producer = fact['produced_by']['producer_type']
    if producer not in _STATUS_PRODUCERS[fact['status']]:
        reject('PRODUCER_STATUS', '/produced_by/producer_type', 'Producer is not authorized for this status.')

    def reference(value, path):
        if not rules.is_reference(value):
            reject('REFERENCE', path, 'Expected a v1 entity reference.')
            return None
        entity_type, key = value.split(':', 1)
        if key != key.strip() or any(ord(c) < 32 or ord(c) == 127 for c in key):
            reject('REFERENCE', path, 'Reference keys must be nonblank and contain no control characters.')
        if entity_type in {'file', 'directory'} and not rules.is_path(key):
            reject('REFERENCE_PATH', path, 'Expected a relative repository path with forward slashes.')
        if entity_type == 'commit' and not _COMMIT_KEY.fullmatch(key):
            reject('REFERENCE_COMMIT', path, 'Expected a full lowercase Git object id.')
        return entity_type

    if 'subject' in fact:
        reference(fact['subject'], '/subject')
    if 'scope' in fact:
        for field in ('include', 'exclude'):
            for index, value in enumerate(fact['scope'].get(field, [])):
                reference(value, f'/scope/{field}/{index}')
    if fact['kind'] == 'ASSERTION':
        _check_assertion(fact, reference, reject)
    for index, evidence in enumerate(fact.get('evidence', [])):
        _check_evidence(fact, evidence, f'/evidence/{index}', reference, reject)
    if 'diagnostic' in fact:
        for code, path, message in _diagnostic_issues(fact):
            reject(code, path, message)
        for index, site in enumerate(fact['diagnostic']['sites']):
            for position, candidate in enumerate(site.get('candidates', [])):
                reference(candidate, f'/diagnostic/sites/{index}/candidates/{position}')
    for index, anchor in enumerate(fact.get('validation', {}).get('anchors', [])):
        reference(anchor['symbol'], f'/validation/anchors/{index}/symbol')
    if issues:
        raise FactValidationError(issues)

    # Identity constraints apply at ingestion, not only when requesting a hash.
    for key in _IDENTITY_FIELDS[fact['kind']]:
        if key in fact:
            _normalize_identity_value(fact[key], (key,))
    if fact['kind'] == 'COVERAGE':
        _normalize_identity_value(fact['produced_by']['producer_id'], ('produced_by', 'producer_id'))


def _check_assertion(fact, reference, reject):
    sources, targets, statuses = RELATIONS[fact['relation']]
    if fact['subject'].split(':', 1)[0] not in sources:
        reject('RELATION_SUBJECT', '/subject', 'Subject type is not permitted by this relation.')
    if fact['status'] not in statuses:
        reject('RELATION_STATUS', '/status', 'Status is not permitted by this relation.')
    if not targets:
        if 'object' in fact:
            reject('RELATION_OBJECT', '/object', 'This relation has no object.')
    elif 'object' not in fact:
        reject('RELATION_OBJECT', '/object', 'This relation requires an object.')
    elif fact['relation'] != 'AUTHORIZED_BY' or _REFERENCE_SYNTAX.match(fact['object']):
        # AUTHORIZED_BY also accepts an uninterpreted literal expression, but a value
        # using the reserved type:key syntax is always validated as a reference.
        target = reference(fact['object'], '/object')
        if target not in targets:
            reject('RELATION_OBJECT', '/object', 'Object type is not permitted by this relation.')
        elif not _paired(fact['relation'], fact['subject'], target):
            reject('RELATION_PAIR', '/object', 'This relation does not link these two types.')
    if fact['relation'] == 'IMPLEMENTS' and 'object' in fact and not _implements_form(fact):
        reject('IMPLEMENTS_FORM', '/status', 'A type implementation is observed; a method implementation is inferred.')
    if fact['relation'] == 'CALLS' and not any(item.get('role') == CALL_SITE for item in fact.get('evidence', [])):
        reject('CALL_SITE_REQUIRED', '/evidence', 'A call is proven by at least one call-site evidence.')


def _check_evidence(fact, evidence, path, reference, reject):
    if any(evidence[k] != fact['snapshot'][k] for k in ('repository', 'commit')):
        reject('EVIDENCE_SNAPSHOT', path, 'Evidence must belong to the same repository and commit as the fact.')
    if 'symbol' in evidence:
        reference(evidence['symbol'], path + '/symbol')
    for bounds, issue in _span_issues(evidence):
        reject(f'EVIDENCE_{bounds}', path, issue)
    if evidence.get('role') == CALL_SITE:
        for issue in _call_site_issues(fact, evidence):
            reject('EVIDENCE_CALL_SITE', path, issue)
    # Une preuve Git (objet commit) prouve l'historique, et l'historique ne se prouve que par elle.
    history = fact['kind'] == 'ASSERTION' and fact['relation'] in _GIT_RELATIONS
    if ('object' in evidence) != history:
        reject('EVIDENCE_OBJECT', path, 'Git history relations need Git object evidence, and only they accept it.')


def _implements_form(fact):
    """Un type implemente un type (ecrit : `OBSERVED`) ; une methode implemente une methode (deduit : `INFERRED`)."""
    members = {'(' in reference.partition('#')[2] for reference in (fact['subject'], fact['object'])}
    types = {'#' not in reference for reference in (fact['subject'], fact['object'])}
    return members == {True} if fact['status'] == 'INFERRED' else types == {True}


def _paired(relation, subject, target_type):
    pairs = RELATION_PAIRS.get(relation)
    return pairs is None or (subject.split(':', 1)[0], target_type) in pairs


def _span_issues(span):
    """A span ends after it starts: on one line, its end column (exclusive) follows its start column."""
    if 'line_start' in span and span['line_end'] < span['line_start']:
        yield 'LINES', 'End line must not precede start line.'
    elif 'column_start' in span and span['line_start'] == span['line_end'] \
            and span['column_end'] <= span['column_start']:
        yield 'COLUMNS', 'On one line, the end column must follow the start column.'


def _call_site_issues(fact, evidence):
    if fact['kind'] != 'ASSERTION' or fact['relation'] != 'CALLS':
        yield 'Only a call is proven by a call site.'
    if 'column_start' not in evidence:
        yield 'A call site is located by its lines and columns.'
    if evidence.get('symbol') != fact.get('subject'):
        yield 'A call site names its lexical owner, the subject of the call.'


def _diagnostic_issues(fact):
    if fact['coverage_type'] != 'NOT_INTERPRETED':
        yield 'DIAGNOSTIC_COVERAGE', '/diagnostic', 'Only an uninterpreted zone carries a diagnostic.'
    diagnostic = fact['diagnostic']
    if len(diagnostic['sites']) > diagnostic['sites_seen']:
        yield 'DIAGNOSTIC_SITES', '/diagnostic/sites', 'More sites are listed than were seen.'
    classified = 'classification' in diagnostic
    for index, site in enumerate(diagnostic['sites']):
        for bounds, issue in _span_issues(site):
            yield f'DIAGNOSTIC_{bounds}', f'/diagnostic/sites/{index}', issue
        # TAXO-01M : une catégorie n'existe qu'avec la règle qui l'a donnée, et une règle classe chaque site.
        if classified and 'category' not in site:
            yield ('DIAGNOSTIC_CATEGORY', f'/diagnostic/sites/{index}',
                   'A classified diagnostic gives each site a category.')
        if not classified and 'category' in site:
            yield ('DIAGNOSTIC_CLASSIFICATION', f'/diagnostic/sites/{index}/category',
                   'A category is kept with the classification rule that gave it.')
