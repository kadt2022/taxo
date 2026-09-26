"""Evaluateur Spring Security (TAXO-05) : quelle regle d'autorisation d'URL s'applique a chaque endpoint.

Il reprend les endpoints de l'evaluateur Spring API (qui reste proprietaire du concept d'endpoint) et lit
les configurations `authorizeHttpRequests` dans les sources Java. Il produit :

- pour chaque regle lue, `route-pattern:<motif>` PERMITS_ALL, ou AUTHORIZED_BY l'expression ecrite
  (`hasRole("ADMIN")`) ou le type qui decide (`access(manager)`) : `OBSERVED`, preuve a la ligne ;
- pour chaque endpoint dont la regle gagnante est sure, `endpoint` MATCHED_BY `route-pattern` : `INFERRED`,
  premiere regle correspondante dans l'ordre de declaration, les regles anterieures en contre-exemples ;
- puis, si cette regle exige une autorisation, `endpoint` PROTECTED_BY `policy-rule:<expression>` ou
  `symbol:java:<type>` : `INFERRED`, sur MATCHED_BY et AUTHORIZED_BY, jamais sur HANDLED_BY.

Critere anti-faux-positif : il ne conclut que si la conclusion vaut pour toute requete de la route. Une
regle anterieure non lue ou qui ne correspond qu'a une partie des requetes, plusieurs chaines de filtres
candidates, un perimetre non lu, `web.ignoring()` : l'endpoint est NOT_INTERPRETED, jamais declare
protege ni public a tort. La securite de methode (`@PreAuthorize`...) et les filtres ou gestionnaires
d'autorisation maison sont declares NOT_INTERPRETED : la protection reelle peut s'y trouver.
"""
from app.evaluations.domain.evaluator import EvaluationOutput
from app.evaluations.domain.progress import silent
from app.evaluations.domain.status import EvaluationStatus
from app.evaluators.spring_api.evaluator import analyse
from app.facts import content_hash
from . import rules
from .catalog import CATALOG

MATCHER_METHOD = 'java.spring-security.request-matcher'
ORDER_METHOD = 'java.spring-security.authorize-http-requests'
FIRST_MATCH = 'spring-security.first-matching-pattern'
APPLIES = 'spring-security.route-authorization-applies'
# Annotations de securite de methode : la regle d'URL n'est alors pas toute la protection.
METHOD_SECURITY = {'PreAuthorize', 'PostAuthorize', 'PreFilter', 'PostFilter', 'Secured', 'RolesAllowed',
                   'DenyAll', 'PermitAll'}
# Supertypes d'un mecanisme maison : filtre de servlet, gestionnaire d'autorisation.
CUSTOM = {'OncePerRequestFilter', 'GenericFilterBean', 'Filter', 'AuthorizationManager'}
DATA_GAP = 'les rôles et autorités des utilisateurs sont des données, hors du code'


class SpringSecurityEvaluator:
    evaluator_id = 'taxo.spring-security'
    producer_version = '0.1.0'
    catalog = CATALOG

    def evaluate(self, snapshot, progress=silent):
        repository = f'repository:{snapshot.repository}'
        analysis = analyse(snapshot, progress)
        run = _Run(snapshot, analysis)
        run.evaluate()
        progress('security', 'Routes rattachées à une règle', run.matched)
        coverage = [{**_coverage(repository, 'ANALYSED', repository), 'scope': analysis.scope(repository)}]
        coverage += [_coverage(subject, 'NOT_INTERPRETED', scope) for subject, (scope, _) in sorted(run.gaps.items())]
        coverage += [_coverage(subject, 'READ_ERROR', subject) for subject in analysis.read_errors]
        warnings = analysis.warnings + run.warnings + [
            f'{subject} : {" ; ".join(reasons)}' for subject, (_, reasons) in sorted(run.gaps.items())]
        partial = run.gaps or analysis.read_errors
        status = EvaluationStatus.PARTIAL if partial else EvaluationStatus.SUCCESS
        legacy = {'configurations': len(run.configurations), 'matched': run.matched, 'protected': run.protected}
        return EvaluationOutput(tuple(run.facts.values()), tuple(coverage), status, tuple(warnings), legacy)


class _Run:
    def __init__(self, snapshot, analysis):
        self.snapshot, self.analysis = snapshot, analysis
        self.facts, self.gaps, self.warnings = {}, {}, []
        self.configurations, self.ignored = [], []
        self.matched = self.protected = 0
        for java_file in analysis.parsed:
            if b'authorize' in analysis.contents[java_file.path] or b'ignoring' in analysis.contents[java_file.path]:
                found, ignored = rules.configurations(java_file)
                self.configurations += found
                self.ignored += [(java_file.path, patterns, line) for patterns, line in ignored]

    def evaluate(self):
        for subject, (path, message) in self.analysis.run.gaps.items():
            # Une route que l'analyse des endpoints n'a pas etablie n'a pas de regle : ce n'est pas une absence.
            self._gap(subject, f'file:{path}', f'routes non établies par l’analyse des endpoints ({message})')
        for java_file in self.analysis.parsed:
            self._custom(java_file)
        for configuration in self.configurations:
            self._configuration_facts(configuration)
        endpoints = list(self.analysis.endpoints())
        if endpoints and not self.configurations:
            self.warnings.append('Aucune règle authorizeHttpRequests trouvée : la protection des routes n’est pas '
                                 'établie (configuration par défaut, XML ou Kotlin non lus).')
        for endpoint in endpoints:
            self._method_security(endpoint)
            if self.configurations:
                self._endpoint(endpoint)

    def _gap(self, subject, scope, reason):
        _, reasons = self.gaps.setdefault(subject, (scope, []))
        if reason not in reasons:
            reasons.append(reason)

    def _add(self, fact):
        key = (fact['subject'], fact['relation'], fact.get('object'), fact['qualifiers']['filter_chain'])
        self.facts.setdefault(key, fact)

    def _custom(self, java_file):
        """Filtres et gestionnaires d'autorisation maison : la protection peut s'y decider, hors des regles."""
        for java_type in java_file.types:
            kinds = [written.rsplit('.', 1)[-1] for written, _ in java_type.supertypes]
            custom = sorted(set(kinds) & CUSTOM)
            if custom:
                self._gap(f'symbol:java:{java_type.qualified_name}', f'file:{java_file.path}',
                          f'mécanisme maison non interprété ({", ".join(custom)})')

    def _configuration_facts(self, configuration):
        scope = f'file:{configuration.path}'
        if not configuration.readable:
            self._gap(configuration.symbol, scope, f'configuration non interprétée ({configuration.reason})')
        for rule in configuration.rules:
            if not rule.readable:
                self._gap(configuration.symbol, scope, f'règle non lue, {rule.describe()}')
                continue
            if rule.never:
                continue
            evidence = self._evidence(configuration.path, rule.line_start, rule.line_end, MATCHER_METHOD)
            for reference in rule.references():
                chain = configuration.symbol
                if rule.permits:
                    self._add(_assertion(reference, 'PERMITS_ALL', None, [evidence], chain))
                else:
                    self._add(_assertion(reference, 'AUTHORIZED_BY', rule.target or rule.expression, [evidence], chain))

    def _method_security(self, endpoint):
        annotations = [item for method in endpoint.methods for item in method.annotations]
        annotations += endpoint.java_type.annotations
        found = sorted({item.simple_name for item in annotations if item.simple_name in METHOD_SECURITY})
        if found:
            self._gap(endpoint.reference, f'file:{endpoint.path}',
                      f'sécurité de méthode non interprétée ({", ".join("@" + name for name in found)})')

    def _endpoint(self, endpoint):
        """Rattache l'endpoint a sa regle gagnante, ou dit pourquoi il ne le peut pas."""
        repository = f'repository:{self.snapshot.repository}'
        for path, patterns, line in self.ignored:
            if patterns is None or max(rules.match(pattern, endpoint.route) for pattern in patterns) != rules.NONE:
                self._gap(endpoint.reference, f'file:{path}', f'exclusion web.ignoring() ligne {line} non écartée')
                return
        candidates = [(item, item.applies(endpoint.route)) for item in self.configurations]
        candidates = [(item, applies) for item, applies in candidates if applies != rules.NONE]
        if len(candidates) != 1 or candidates[0][1] != rules.ALL:
            if len(candidates) == 1:
                self._gap(endpoint.reference, f'file:{candidates[0][0].path}',
                          'périmètre de la chaîne de filtres non établi pour cette route')
            else:
                self._gap(endpoint.reference, repository, f'{len(candidates)} chaînes de filtres candidates')
            return
        configuration = candidates[0][0]
        scope = f'file:{configuration.path}'
        if not configuration.readable:
            self._gap(endpoint.reference, scope, 'configuration non interprétée')
            return
        checked = []
        for rule in configuration.rules:
            outcome = rule.match(endpoint.verb, endpoint.route)
            if outcome == rules.NONE:
                checked.append(rule)
                continue
            if outcome == rules.SOME:
                reason = 'non lue' if not rule.readable else 'correspond à une partie des requêtes seulement'
                self._gap(endpoint.reference, scope, f'règle antérieure {reason} : {rule.describe()}')
                return
            self._conclude(endpoint, configuration, checked, rule)
            return
        self._gap(endpoint.reference, scope, 'aucune règle ne capture la route')

    def _conclude(self, endpoint, configuration, checked, winner):
        prefix = f'{winner.verb} ' if winner.verb else ''
        pattern = next(f'route-pattern:{prefix}{item}' for item in winner.patterns
                       if rules.match(item, endpoint.route) == rules.ALL)
        evidence = [self._evidence(configuration.path, winner.line_start, winner.line_end, MATCHER_METHOD)]
        first = configuration.rules[0]
        if first is not winner:
            evidence.append(self._evidence(configuration.path, first.line_start, winner.line_end, ORDER_METHOD))
        chain = configuration.symbol
        matched = _inference(
            endpoint.reference, 'MATCHED_BY', pattern, evidence, chain,
            premises=[f'HANDLED_BY : {endpoint.reference} -> {endpoint.handler}',
                      *[rule.describe() for rule in (*checked, winner)]],
            rule=FIRST_MATCH, checked=[f'{rule.describe()} : ne correspond pas' for rule in checked],
            gaps=[winner.note] if winner.note else [])
        self._add(matched)
        self.matched += 1
        if winner.permits:
            return
        target = winner.target or f'policy-rule:{winner.expression}'
        gaps = ([f'la décision de {winner.target} n’est pas lue'] if winner.target else
                [DATA_GAP] if winner.action in ('hasRole', 'hasAnyRole', 'hasAuthority', 'hasAnyAuthority') else
                ['l’expression d’autorisation n’est pas évaluée'] if winner.action == 'access' else [])
        self._add(_inference(
            endpoint.reference, 'PROTECTED_BY', target, evidence, chain,
            premises=[f'MATCHED_BY : {endpoint.reference} -> {pattern}',
                      f'AUTHORIZED_BY : {pattern} -> {winner.target or winner.expression}'],
            rule=APPLIES, checked=[], gaps=gaps))
        self.protected += 1

    def _evidence(self, path, line_start, line_end, method):
        data = self.analysis.contents[path]
        return {'repository': self.snapshot.repository, 'commit': self.snapshot.commit, 'path': path,
                'line_start': line_start, 'line_end': line_end, 'method': method,
                'content_hash': content_hash(data, line_start, line_end)}


def _assertion(subject, relation, target, evidence, chain):
    """PERMITS_ALL est la seule relation sans objet (ADR 0002). Le qualificatif `filter_chain` nomme la chaine de
    filtres qui porte la regle : deux chaines peuvent traiter le meme motif differemment."""
    fact = {'contract_version': 1, 'kind': 'ASSERTION', 'status': 'OBSERVED', 'validity': 'VALID',
            'subject': subject, 'relation': relation, 'qualifiers': {'filter_chain': chain}, 'evidence': evidence}
    if target is not None:
        fact['object'] = target
    return fact


def _inference(subject, relation, target, evidence, chain, premises, rule, checked, gaps):
    return {'contract_version': 1, 'kind': 'ASSERTION', 'status': 'INFERRED', 'validity': 'VALID',
            'subject': subject, 'relation': relation, 'object': target, 'qualifiers': {'filter_chain': chain},
            'evidence': evidence,
            'derivation': {'premises': premises, 'rule': rule, 'counter_examples_checked': checked,
                           'known_gaps': gaps}}


def _coverage(subject, coverage_type, scope):
    return {'contract_version': 1, 'kind': 'COVERAGE', 'status': 'OBSERVED', 'validity': 'VALID',
            'subject': subject, 'coverage_type': coverage_type, 'scope': {'include': [scope]}}
