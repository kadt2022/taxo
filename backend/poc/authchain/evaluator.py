"""Chaine d'autorisation d'une route, assemblee selon le contrat TAXO-01A. Jetable."""
import json
import re

from app.evaluations.domain.evaluator import EvaluationOutput
from app.evaluations.domain.status import EvaluationStatus
from app.facts import content_hash

from . import spring
from .catalog import CATALOG

JAVA = '.java'
TEST_SOURCES = '/src/test/'
MAX_BYTES = 512 * 1024
FILTER_PATTERN = re.compile(r'parse\s*\(\s*"([^"]*)"')
FILTER_CLASS = re.compile(r'\bclass\s+(\w+)\s+extends\s+\w*Filter\b')
DELEGATING_ACTIONS = ('access',)


class AuthorizationChainPoc:
    """Produit F1 a F5 pour une route donnee, ou pour chaque route, et declare ce qu'il ne sait pas."""

    evaluator_id = 'poc.spring-authorization-chain'
    producer_version = '0.0.2'
    catalog = CATALOG

    def __init__(self, target=None):
        """Sans cible, chaque route declaree est evaluee : une route oubliee n'attend pas qu'on la nomme."""
        self.verb = self.path = None
        if target is None:
            return
        verb, _, path = target.strip().partition(' ')
        if not verb or not path:
            raise ValueError("Route attendue sous la forme 'GET /chemin'.")
        self.verb, self.path = verb.upper(), path

    def evaluate(self, snapshot):
        sources = self._sources(snapshot)
        repository = f'repository:{snapshot.repository}'
        if self.verb is None:
            located = [(path, endpoint) for path in sorted(sources)
                       for endpoint in spring.endpoints(sources[path])]
        else:
            located = self._endpoint(sources)
            if located is None:
                coverage = [self._coverage(self._target(), 'NOT_INTERPRETED', [repository])]
                return self._output([], coverage, [], EvaluationStatus.PARTIAL)
            located = [located]
        facts, coverage, warnings = [], [self._coverage(repository, 'ANALYSED', [repository])], []
        status = EvaluationStatus.SUCCESS
        for path, endpoint in located:
            if not self._chain(snapshot, sources, path, endpoint, facts, coverage, warnings):
                status = EvaluationStatus.PARTIAL
        return self._output(self._unique(facts), self._unique(coverage), warnings, status)

    def _chain(self, snapshot, sources, path, endpoint, facts, coverage, warnings):
        """Ajoute la chaine d'une route ; faux si une conclusion manque ou reste incertaine."""
        facts.append(self._handled_by(snapshot, path, sources[path], endpoint))
        configurations = self._configurations(sources, endpoint)
        if len(configurations) != 1:
            include = (sorted(f'file:{name}' for name, _, _ in configurations)
                       or [f'repository:{snapshot.repository}'])
            coverage.append(self._coverage(endpoint.reference(), 'NOT_INTERPRETED', include))
            warnings.append(f'{endpoint.verb} {endpoint.path} : {len(configurations)} chaines de '
                            'filtres candidates : aucune conclusion.')
            return False
        name, rules, winner = configurations[0]
        text = sources[name]
        facts.extend(self._authorization(snapshot, name, text, rules, winner, endpoint))
        facts.extend(self._calls(snapshot, sources, winner, text))
        facts.extend(self._filters(sources, endpoint))
        coverage.extend(self._limits(sources, name, rules, winner, endpoint))
        earlier = rules[:rules.index(winner)]
        return all(rule.readable for rule in earlier)

    @staticmethod
    def _unique(items):
        return list({json.dumps(item, sort_keys=True): item for item in items}.values())

    def _target(self):
        return f'endpoint:{self.verb} {self.path}'

    def _sources(self, snapshot):
        wanted = [file.path for file in snapshot.iter_files()
                  if file.path.endswith(JAVA) and TEST_SOURCES not in file.path
                  and file.size <= MAX_BYTES]
        return {path: data.decode('utf-8', errors='replace')
                for path, data in snapshot.read_many(wanted)}

    def _endpoint(self, sources):
        for path in sorted(sources):
            for endpoint in spring.endpoints(sources[path]):
                if endpoint.verb == self.verb and endpoint.path == self.path:
                    return path, endpoint
        return None

    @staticmethod
    def _configurations(sources, endpoint):
        """Chaines de filtres dont une regle capture la route : une seule doit gagner."""
        found = []
        for path in sorted(sources):
            rules = spring.security_rules(sources[path])
            winner = next((rule for rule in rules
                           if rule.readable
                           and (rule.verb is None or rule.verb == endpoint.verb)
                           and any(spring.matches(pattern, endpoint.path)
                                   for pattern in rule.patterns)), None)
            if winner is not None:
                found.append((path, rules, winner))
        return found

    def _handled_by(self, snapshot, path, text, endpoint):
        lines = ((endpoint.class_mapping_line, 'java.spring.request-mapping'),
                 (endpoint.method_mapping_line, 'java.spring.method-mapping'),
                 (endpoint.declaration_line, 'java.method-declaration'))
        evidence = [self._evidence(snapshot, path, text, line, line, method)
                    for line, method in lines]
        return self._assertion(endpoint.reference(), 'HANDLED_BY',
                               endpoint.handler_reference(), evidence)

    def _authorization(self, snapshot, path, text, rules, winner, endpoint):
        pattern = next(candidate for candidate in winner.patterns
                       if spring.matches(candidate, endpoint.path))
        reference = f'route-pattern:{pattern}'
        method = 'java.spring.any-request' if winner.catch_all else 'java.spring.request-matcher'
        evidence = self._evidence(snapshot, path, text, winner.line_start, winner.line_end, method)
        earlier = rules[:rules.index(winner)]
        matched = self._inference(
            endpoint.reference(), 'MATCHED_BY', reference,
            premises=[rule.describe() for rule in rules[:rules.index(winner) + 1]],
            rule='la premiere regle correspondante gagne (Spring Security)',
            checked=[f'{rule.describe()} : ne correspond pas' for rule in earlier],
            gaps=[f'{rule.describe()} : motif non lu' for rule in earlier if not rule.readable],
            evidence=[self._evidence(snapshot, path, text, rules[0].line_start, rules[-1].line_end,
                                     'java.spring.authorize-http-requests')])
        if winner.action == 'permitAll':
            return [self._assertion(reference, 'PERMITS_ALL', None, [evidence]), matched]
        if winner.action not in DELEGATING_ACTIONS:
            return [matched]
        target = spring.injected_fields(text).get(winner.argument)
        if target is None:
            return [matched]
        type_name, declaration = target
        authorized = self._assertion(reference, 'AUTHORIZED_BY', f'symbol:{type_name}', [evidence])
        protected = self._inference(
            endpoint.reference(), 'PROTECTED_BY', f'symbol:{type_name}',
            premises=[f'MATCHED_BY : {endpoint.reference()} -> {reference}',
                      f'AUTHORIZED_BY : {reference} -> symbol:{type_name}'],
            rule='PROTECTED_BY prend appui sur MATCHED_BY puis AUTHORIZED_BY (ADR 0002)',
            checked=['HANDLED_BY ne peut jamais servir de premisse a PROTECTED_BY'],
            gaps=['la decision elle-meme ne vient pas du code'],
            evidence=[evidence, self._evidence(snapshot, path, text, declaration, declaration,
                                               'java.injected-field')])
        return [authorized, matched, protected]

    def _calls(self, snapshot, sources, winner, configuration):
        target = spring.injected_fields(configuration).get(winner.argument)
        if winner.action not in DELEGATING_ACTIONS or target is None:
            return []
        type_name = target[0]
        declaration = re.compile(r'\bclass\s+' + re.escape(type_name) + r'\b')
        path = next((name for name in sorted(sources)
                     if declaration.search(spring.without_comments(sources[name]))), None)
        if path is None:
            return []
        text = sources[path]
        facts = []
        for field, (called_type, line) in sorted(spring.injected_fields(text).items()):
            call_lines = spring.invocations(text, field)
            if not call_lines:
                continue
            facts.append(self._assertion(
                f'symbol:{type_name}', 'CALLS', f'symbol:{called_type}',
                [self._evidence(snapshot, path, text, line, line, 'java.injected-field'),
                 self._evidence(snapshot, path, text, call_lines[0], call_lines[0],
                                'java.method-invocation')]))
        return facts

    def _filters(self, sources, endpoint):
        """Un filtre dont aucun motif ne capture la route : une absence, pas un silence."""
        facts = []
        for path in sorted(sources):
            text = spring.without_comments(sources[path])
            declaration = FILTER_CLASS.search(text)
            if declaration is None:
                continue
            patterns = FILTER_PATTERN.findall(text)
            if not patterns or any(spring.matches(pattern, endpoint.path) for pattern in patterns):
                continue
            facts.append({
                'contract_version': 1, 'kind': 'ABSENCE', 'status': 'OBSERVED', 'validity': 'VALID',
                'pattern': {'type': 'spring.path-pattern-of-filter',
                            'value': f'{declaration.group(1)} applique a {endpoint.reference()}'},
                'method': 'java.spring.path-pattern',
                'scope': {'include': [f'file:{path}'], 'exclude': []},
            })
        return facts

    def _limits(self, sources, path, rules, winner, endpoint):
        """Les limites declarees du POC : decision de politique, regles non lues, execution."""
        limits = [self._coverage(endpoint.reference(), 'OUT_OF_SCOPE', [f'file:{path}'])]
        earlier = rules[:rules.index(winner)]
        if any(not rule.readable for rule in earlier):
            limits.append(self._coverage(f'file:{path}', 'NOT_INTERPRETED', [f'file:{path}']))
        for name in sorted(sources):
            if FILTER_CLASS.search(spring.without_comments(sources[name])):
                limits.append(self._coverage(f'file:{name}', 'NOT_INTERPRETED', [f'file:{name}']))
        return limits

    @staticmethod
    def _assertion(subject, relation, object_reference, evidence):
        """`PERMITS_ALL` est la seule relation du catalogue sans objet (ADR 0002)."""
        fact = {'contract_version': 1, 'kind': 'ASSERTION', 'status': 'OBSERVED',
                'validity': 'VALID', 'subject': subject, 'relation': relation,
                'qualifiers': {}, 'evidence': evidence}
        if object_reference is not None:
            fact['object'] = object_reference
        return fact

    @staticmethod
    def _inference(subject, relation, object_reference, premises, rule, checked, gaps, evidence):
        return {'contract_version': 1, 'kind': 'ASSERTION', 'status': 'INFERRED',
                'validity': 'VALID', 'subject': subject, 'relation': relation,
                'object': object_reference, 'qualifiers': {}, 'evidence': evidence,
                'derivation': {'premises': premises, 'rule': rule,
                               'counter_examples_checked': checked, 'known_gaps': gaps}}

    @staticmethod
    def _coverage(subject, coverage_type, include):
        return {'contract_version': 1, 'kind': 'COVERAGE', 'status': 'OBSERVED',
                'validity': 'VALID', 'subject': subject, 'coverage_type': coverage_type,
                'scope': {'include': include, 'exclude': []}}

    @staticmethod
    def _evidence(snapshot, path, text, line_start, line_end, method):
        return {'repository': snapshot.repository, 'commit': snapshot.commit, 'path': path,
                'line_start': line_start, 'line_end': line_end, 'method': method,
                'content_hash': content_hash(text.encode('utf-8'), line_start, line_end)}

    @staticmethod
    def _output(facts, coverage, warnings, status):
        return EvaluationOutput(tuple(facts), tuple(coverage), status, tuple(warnings), {})
