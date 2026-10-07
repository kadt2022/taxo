"""Les faits de l'evaluateur des appels Java, dans la forme du contrat v1 (ARCHITECTURE § 5, § 14).

Une identite n'est ecrite qu'une fois par execution : deux preuves d'un meme fait (deux sites d'un meme appel, une
declaration vue dans deux fichiers) sont deux preuves de la meme assertion.
"""
from app.facts import content_hash

from . import implementations, resolution

DECLARATION = 'java.declaration'
CALL_SITE = 'java.call-site'
_DIAGNOSTIC_KEYS = ('method', 'receiver', 'receiver_type', 'external_supertypes', 'candidates')


class Facts:
    def __init__(self, snapshot, contents):
        self.snapshot, self.contents = snapshot, contents
        self._assertions = {}

    def declaration(self, subject, relation, target, path, line):
        """Une declaration ecrite (`OBSERVED`), prouvee par la ligne qui l'ecrit."""
        evidence = self._evidence(path, line, line, DECLARATION, target if relation == 'CONTAINS' else subject)
        self._add(subject, relation, target, 'OBSERVED', evidence)

    def call(self, subject, target, path, site, premises, counter_examples):
        """Un appel (`INFERRED`), prouve par son site ; les sites d'un meme appel s'ajoutent a la meme assertion."""
        evidence = {**self._evidence(path, site.line_start, site.line_end, CALL_SITE, subject),
                    'column_start': site.column_start, 'column_end': site.column_end, 'role': 'call-site'}
        self._inferred(subject, 'CALLS', target, evidence, resolution, premises, counter_examples)

    def implementation(self, found):
        """Une implementation de methode (`INFERRED`), prouvee par la ligne du nom de la methode qui implemente."""
        evidence = self._evidence(found.path, found.line, found.line, DECLARATION, found.subject)
        self._inferred(found.subject, 'IMPLEMENTS', found.target, evidence, implementations, found.premises, ())

    def assertions(self):
        return tuple(self._assertions[key] for key in sorted(self._assertions))

    def _add(self, subject, relation, target, status, evidence):
        key = (subject, relation, target)
        fact = self._assertions.setdefault(key, {
            'contract_version': 1, 'kind': 'ASSERTION', 'status': status, 'validity': 'VALID', 'subject': subject,
            'relation': relation, 'object': target, 'qualifiers': {}, 'evidence': []})
        if evidence not in fact['evidence']:
            fact['evidence'].append(evidence)
        return fact

    def _inferred(self, subject, relation, target, evidence, rule, premises, counter_examples):
        """Une deduction de la regle `rule` (son module : `RULE`, `KNOWN_GAPS`) ; ses preuves et ses premisses
        s'ajoutent a celles deja ecrites pour la meme identite."""
        fact = self._add(subject, relation, target, 'INFERRED', evidence)
        derivation = fact.setdefault('derivation', {'premises': [], 'rule': rule.RULE, 'counter_examples_checked': [],
                                                    'known_gaps': list(rule.KNOWN_GAPS)})
        _extend(derivation['premises'], premises)
        _extend(derivation['counter_examples_checked'], counter_examples)

    def _evidence(self, path, line_start, line_end, method, symbol):
        return {'repository': self.snapshot.repository, 'commit': self.snapshot.commit, 'path': path,
                'line_start': line_start, 'line_end': line_end, 'symbol': symbol, 'method': method,
                'content_hash': content_hash(self.contents[path], line_start, line_end)}


def coverage(subject, coverage_type, scope, reason=None, diagnostic=None, exclude=()):
    fact = {'contract_version': 1, 'kind': 'COVERAGE', 'status': 'OBSERVED', 'validity': 'VALID',
            'subject': subject, 'coverage_type': coverage_type,
            'scope': {'include': [scope], **({'exclude': sorted(exclude)} if exclude else {})}}
    if reason:
        fact['reason'] = reason
    if diagnostic:
        fact['diagnostic'] = diagnostic
    return fact


def site_diagnostic(site, outcome):
    """Un site non interprete, tel que le `diagnostic` d'une couverture le decrit (ARCHITECTURE § 14)."""
    return {'role': 'call-site', 'line_start': site.line_start, 'line_end': site.line_end,
            'column_start': site.column_start, 'column_end': site.column_end, 'reason': outcome.reason,
            **{key: outcome.details[key] for key in _DIAGNOSTIC_KEYS if outcome.details.get(key)}}


def _extend(values, more):
    values.extend(item for item in more if item not in values)
