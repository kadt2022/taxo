import re
from .errors import FactValidationError, ValidationIssue
from .identity import _IDENTITY_FIELDS, _normalize_identity_value

# Reserved type:key syntax of entity references; never read as a literal expression.
_REFERENCE_SYNTAX = re.compile(r'[a-z][a-z0-9-]*:')

# Source/target types and permitted statuses are the v1 relation vocabulary.
RELATIONS = {
    'CONTAINS': ({'repository', 'module'}, {'module', 'file'}, {'OBSERVED'}),
    'WRITTEN_IN': ({'file'}, {'language'}, {'OBSERVED'}),
    'USES_TECHNOLOGY': ({'repository', 'module'}, {'technology'}, {'OBSERVED'}),
    'DECLARED_BY': ({'technology'}, {'file'}, {'OBSERVED'}),
    'ANNOTATED_WITH': ({'symbol'}, {'annotation'}, {'OBSERVED'}),
    'CALLS': ({'symbol'}, {'symbol'}, {'OBSERVED'}),
    'IMPLEMENTS': ({'symbol'}, {'symbol'}, {'OBSERVED'}),
    'DISPATCHES_TO': ({'symbol'}, {'symbol'}, {'INFERRED'}),
    'HANDLED_BY': ({'endpoint'}, {'symbol'}, {'OBSERVED'}),
    'ACCEPTS': ({'endpoint'}, {'symbol'}, {'OBSERVED'}),
    'RETURNS': ({'endpoint'}, {'symbol'}, {'OBSERVED'}),
    'PERMITS_ALL': ({'route-pattern'}, set(), {'OBSERVED'}),
    'AUTHORIZED_BY': ({'route-pattern'}, {'symbol'}, {'OBSERVED'}),
    'MATCHED_BY': ({'endpoint'}, {'route-pattern'}, {'INFERRED'}),
    'PROTECTED_BY': ({'endpoint'}, {'symbol', 'policy-rule'}, {'INFERRED', 'HUMAN_VALIDATED'}),
    # Historique Git (ADR 0007) : un commit, son auteur, ses parents et les fichiers qu'il change.
    'HAS_COMMIT': ({'repository'}, {'commit'}, {'OBSERVED'}),
    'AUTHORED_BY': ({'commit'}, {'person'}, {'OBSERVED'}),
    'CHILD_OF': ({'commit'}, {'commit'}, {'OBSERVED'}),
    'CHANGES': ({'commit'}, {'file'}, {'OBSERVED'}),
}
# Un commit est designe par son identifiant Git complet, comme l'instantane (ADR 0007).
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
            if reference(fact['object'], '/object') not in targets:
                reject('RELATION_OBJECT', '/object', 'Object type is not permitted by this relation.')

    for index, evidence in enumerate(fact.get('evidence', [])):
        path = f'/evidence/{index}'
        if any(evidence[k] != fact['snapshot'][k] for k in ('repository', 'commit')):
            reject('EVIDENCE_SNAPSHOT', path, 'Evidence must belong to the same repository and commit as the fact.')
        if 'line_start' in evidence and evidence['line_end'] < evidence['line_start']:
            reject('EVIDENCE_LINES', path, 'End line must not precede start line.')
        if 'symbol' in evidence:
            reference(evidence['symbol'], path + '/symbol')
        # Une preuve Git (objet commit) prouve l'historique, et l'historique ne se prouve que par elle.
        history = fact['kind'] == 'ASSERTION' and fact['relation'] in _GIT_RELATIONS
        if ('object' in evidence) != history:
            reject('EVIDENCE_OBJECT', path, 'Git history relations need Git object evidence, and only they accept it.')
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
