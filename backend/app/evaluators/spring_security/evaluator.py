"""Evaluateur Spring Security (TAXO-05) : quelle regle d'autorisation d'URL s'applique a chaque endpoint.

Il reprend les endpoints de l'evaluateur Spring API (qui reste proprietaire du concept d'endpoint) et lit
les configurations `authorizeHttpRequests` dans les sources Java. Il produit :

- pour chaque regle lue, `route-pattern:<motif>` PERMITS_ALL, ou AUTHORIZED_BY l'expression ecrite
  (`hasRole("ADMIN")`) ou le type qui decide (`access(manager)`) : `OBSERVED`, preuve a la ligne ;
- pour chaque endpoint dont la regle gagnante est sure, `endpoint` MATCHED_BY `route-pattern` : `INFERRED`,
  premiere regle correspondante dans l'ordre de declaration, les regles anterieures en contre-exemples ;
- puis, si cette regle exige une autorisation, `endpoint` PROTECTED_BY `policy-rule:<expression>` ou
  `symbol:java:<type>` : `INFERRED`, sur MATCHED_BY et AUTHORIZED_BY, jamais sur HANDLED_BY.

Securite de methode et CSRF (TAXO-MINIA-SEC-01, E2) :

- le type qui active la securite de methode est ANNOTATED_WITH `annotation:<EnableMethodSecurity>` (`OBSERVED`) ;
- la methode, ou le type, garde par `@PreAuthorize` est AUTHORIZED_BY l'expression ecrite (`OBSERVED`) ;
- l'endpoint traite par cette methode est PROTECTED_BY `policy-rule:<expression>` (`INFERRED`, regle
  `spring-security.method-authorization-applies`) sur HANDLED_BY, AUTHORIZED_BY et ANNOTATED_WITH, si
  l'application qui sert la route charge le type qui active et si l'expression ne peut que restreindre ;
- la methode qui desactive CSRF CONFIGURES `policy-rule:csrf.disable()` (`OBSERVED`).

Critere anti-faux-positif : il ne conclut que si la conclusion vaut pour toute requete de la route. Une
regle anterieure non lue ou qui ne correspond qu'a une partie des requetes, plusieurs chaines de filtres
candidates, un perimetre non lu, `web.ignoring()` : l'endpoint est NOT_INTERPRETED, jamais declare
protege ni public a tort. Les autres annotations de securite de methode (`@Secured`...), une expression
`@PreAuthorize` non lue, une activation non etablie, une configuration CSRF autre que sa desactivation et
les filtres ou gestionnaires d'autorisation maison sont declares NOT_INTERPRETED : la protection reelle
peut s'y trouver.

Applications (E1, tranche 2 ; ARCHITECTURE § 7.6) : des qu'une `@SpringBootApplication` est vue, une route n'est
rattachee qu'aux chaines de filtres chargees par l'application qui la sert (SERVED_BY), et les chaines d'une
autre application sont ecartees avec leur raison. Une application qui la sert peut-etre, une chaine dont le
chargement n'est pas etabli, plusieurs applications aux chaines differentes : l'endpoint est NOT_INTERPRETED.
"""
from dataclasses import dataclass, field

from app.evaluations.domain.evaluator import EvaluationOutput
from app.evaluations.domain.progress import silent
from app.evaluations.domain.status import EvaluationStatus
from app.evaluators.spring_api.evaluator import analyse
from app.evaluators.spring_boot.applications import NO, OTHER_ROUTES, UNKNOWN, YES, Deployment
from app.facts import content_hash
from . import methods, rules
from .catalog import CATALOG

MATCHER_METHOD = 'java.spring-security.request-matcher'
ORDER_METHOD = 'java.spring-security.authorize-http-requests'
FIRST_MATCH = 'spring-security.first-matching-pattern'
APPLIES = 'spring-security.route-authorization-applies'
METHOD_APPLIES = 'spring-security.method-authorization-applies'
# Modificateurs qui soustraient une methode au proxy de la securite de methode.
UNADVISABLE = frozenset({'final', 'private', 'static'})
PRE_AUTHORIZE_METHOD = 'java.spring-security.pre-authorize'
ENABLING_METHOD = 'java.spring-security.enable-method-security'
CSRF_METHOD = 'java.spring-security.csrf'
# Annotations de securite de methode : la regle d'URL n'est alors pas toute la protection. Seule `@PreAuthorize`
# est lue ; les autres restent declarees non interpretees.
METHOD_SECURITY = {'PreAuthorize', 'PostAuthorize', 'PreFilter', 'PostFilter', 'Secured', 'RolesAllowed',
                   'DenyAll', 'PermitAll'}
PRE_AUTHORIZE = 'PreAuthorize'
# Supertypes d'un mecanisme maison : filtre de servlet, gestionnaire d'autorisation.
CUSTOM = {'OncePerRequestFilter', 'GenericFilterBean', 'Filter', 'AuthorizationManager'}
ROLE_ACTIONS = ('hasRole', 'hasAnyRole', 'hasAuthority', 'hasAnyAuthority')
DATA_GAP = 'les rôles et autorités des utilisateurs sont des données, hors du code'


class SpringSecurityEvaluator:
    evaluator_id = 'taxo.spring-security'
    producer_version = '0.4.0'
    catalog = CATALOG

    def evaluate(self, snapshot, progress=silent):
        repository = f'repository:{snapshot.repository}'
        analysis = analyse(snapshot, progress)
        run = _Run(snapshot, analysis, Deployment(snapshot, analysis))
        run.evaluate()
        progress('security', 'Routes rattachées à une règle', run.matched)
        coverage = [{**_coverage(repository, 'ANALYSED', repository), 'scope': analysis.scope(repository)}]
        coverage += [_coverage(subject, 'NOT_INTERPRETED', scope, ' ; '.join(reasons))
                     for subject, (scope, reasons) in sorted(run.gaps.items())]
        coverage += [_coverage(subject, 'READ_ERROR', subject) for subject in analysis.read_errors]
        warnings = analysis.warnings + run.warnings + [
            f'{subject} : {" ; ".join(reasons)}' for subject, (_, reasons) in sorted(run.gaps.items())]
        partial = run.gaps or analysis.read_errors
        status = EvaluationStatus.PARTIAL if partial else EvaluationStatus.SUCCESS
        legacy = {'configurations': len(run.configurations), 'matched': run.matched, 'protected': run.protected,
                  'method_protected': run.method_protected}
        return EvaluationOutput(tuple(run.facts.values()), tuple(coverage), status, tuple(warnings), legacy)


@dataclass
class _Serving:
    """Pourquoi une route est rattachee a ces chaines : l'application qui la sert, ce qu'elle charge, ce
    qu'elle ecarte."""
    premises: list = field(default_factory=list)
    checked: list = field(default_factory=list)
    gaps: list = field(default_factory=list)
    applications: list = field(default_factory=list)


class _Run:
    def __init__(self, snapshot, analysis, deployment):
        self.snapshot, self.analysis, self.deployment = snapshot, analysis, deployment
        self.facts, self.gaps, self.warnings = {}, {}, []
        self.configurations, self.ignored, self.enablings, self.csrf = [], [], [], []
        self.matched = self.protected = self.method_protected = 0
        for java_file in analysis.parsed:
            data = analysis.contents[java_file.path]
            if b'authorize' in data or b'ignoring' in data:
                found, ignored = rules.configurations(java_file)
                self.configurations += found
                self.ignored += [(java_file.path, *item) for item in ignored]
            if b'MethodSecurity' in data:
                self.enablings += methods.enablings(java_file, deployment.types)
            if b'csrf' in data:
                self.csrf += methods.csrf(java_file, deployment.types)

    def evaluate(self):
        for subject, (path, message) in self.analysis.run.gaps.items():
            # Une route que l'analyse des endpoints n'a pas etablie n'a pas de regle : ce n'est pas une absence.
            self._gap(subject, f'file:{path}', f'routes non établies par l’analyse des endpoints ({message})')
        for java_file in self.analysis.parsed:
            self._custom(java_file)
        for configuration in self.configurations:
            self._configuration_facts(configuration)
        for enabling in self.enablings:
            self._enabling_facts(enabling)
        for setting in self.csrf:
            self._csrf_facts(setting)
        endpoints = list(self.analysis.endpoints())
        if endpoints and not self.configurations:
            self.warnings.append('Aucune règle authorizeHttpRequests trouvée : la protection des routes n’est pas '
                                 'établie (configuration par défaut, XML ou Kotlin non lus).')
        for endpoint in endpoints:
            self._method_security(endpoint)
            if not self.deployment.applications:
                # Aucune application vue (bibliotheque, deploiement hors Spring Boot) : toutes les chaines lues.
                if self.configurations:
                    self._endpoint(endpoint, self.configurations, _Serving())
                continue
            served = self._served(endpoint)
            if served is not None:
                self._endpoint(endpoint, *served)

    def _served(self, endpoint):
        """Les chaines chargees par l'application qui sert la route, et pourquoi ; ou None (raison declaree)."""
        scope = f'file:{endpoint.path}'
        serving = []
        for application in self.deployment.applications:
            loading = self.deployment.loads(application, endpoint.java_type.qualified_name)
            if loading.outcome == UNKNOWN:
                self._gap(endpoint.reference, scope,
                          f'servie peut-être par {application.reference} ({loading.reason})')
                return None
            if loading.outcome == YES:
                serving.append(application)
        if not serving:
            self._gap(endpoint.reference, scope, 'aucune application établie ne sert cette route')
            return None
        chosen = None
        for application in serving:
            loaded, context = self._loaded(endpoint, application)
            if loaded is None:
                return None
            if chosen is not None and loaded != chosen[0]:
                self._gap(endpoint.reference, f'repository:{self.snapshot.repository}',
                          f'servie par {len(serving)} applications qui chargent des chaînes différentes')
                return None
            chosen = (loaded, context) if chosen is None else (chosen[0], _merge(chosen[1], context))
        if not chosen[0]:
            self._gap(endpoint.reference, f'file:{serving[0].path}',
                      'aucune chaîne de filtres lue n’est chargée par l’application : chaîne par défaut non lue')
            return None
        return chosen

    def _loaded(self, endpoint, application):
        """Chaines chargees par `application`, et le contexte de la conclusion ; (None, None) si l'une reste inconnue."""
        context = _Serving([f'SERVED_BY : {endpoint.reference} -> {application.reference}'], applications=[application])
        loaded = []
        for configuration in self.configurations:
            owner, _, signature = configuration.symbol.removeprefix('symbol:java:').partition('#')
            loading = self.deployment.loads_bean(application, owner, signature)
            if loading.outcome == YES:
                loaded.append(configuration)
                context.premises.append(f'{application.reference} charge {configuration.symbol}')
            elif loading.outcome == UNKNOWN and configuration.applies(endpoint.route) != rules.NONE:
                self._gap(endpoint.reference, f'file:{configuration.path}',
                          f'chargement de {configuration.symbol} par {application.reference} non établi '
                          f'({loading.reason})')
                return None, None
            elif loading.outcome == NO:
                context.checked.append(f'{configuration.symbol} : non chargée par {application.reference} '
                                       f'({loading.reason})')
                if 'hors du classpath' not in loading.reason and OTHER_ROUTES not in context.gaps:
                    context.gaps.append(OTHER_ROUTES)
        return tuple(loaded), context

    def _gap(self, subject, scope, reason):
        _, reasons = self.gaps.setdefault(subject, (scope, []))
        if reason not in reasons:
            reasons.append(reason)

    def _add(self, fact):
        key = (fact['subject'], fact['relation'], fact.get('object'), tuple(sorted(fact['qualifiers'].items())))
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

    def _enabling_facts(self, enabling):
        annotation = enabling.annotation
        evidence = self._evidence(enabling.path, annotation.line_start, annotation.line_end, ENABLING_METHOD)
        qualifiers = {methods.PRE_POST: enabling.written} if enabling.written is not None else {}
        self._add(_observed(enabling.symbol, 'ANNOTATED_WITH', enabling.reference, [evidence], qualifiers))
        if enabling.state == methods.UNKNOWN:
            self._gap(enabling.symbol, f'file:{enabling.path}',
                      f'activation de la sécurité de méthode non établie ({enabling.unread})')

    def _csrf_facts(self, setting):
        if not setting.disabled:
            self._gap(setting.symbol, f'file:{setting.path}', f'configuration CSRF non interprétée (ligne '
                                                              f'{setting.line_start})')
            return
        evidence = self._evidence(setting.path, setting.line_start, setting.line_end, CSRF_METHOD)
        self._add(_observed(setting.symbol, 'CONFIGURES', f'policy-rule:{methods.CSRF_DISABLED}', [evidence], {}))

    def _method_security(self, endpoint):
        """La garde `@PreAuthorize` de la methode qui traite l'endpoint, et ce qu'elle protege ; les autres
        annotations de securite de methode sont declarees non interpretees."""
        scope = f'file:{endpoint.path}'
        annotations = [item for method in endpoint.methods for item in method.annotations]
        annotations += endpoint.java_type.annotations
        others = sorted({item.simple_name for item in annotations
                         if item.simple_name in METHOD_SECURITY and item.simple_name != PRE_AUTHORIZE})
        if others:
            self._gap(endpoint.reference, scope,
                      f'sécurité de méthode non interprétée ({", ".join("@" + name for name in others)})')
        if not endpoint.methods:
            return
        java_file = self.analysis.run.types[endpoint.java_type.qualified_name][0]
        if not any(item.simple_name == PRE_AUTHORIZE for item in annotations):
            hidden = methods.hidden(java_file, endpoint.java_type, endpoint.methods[0], self.deployment.types)
            if hidden:
                self._gap(endpoint.reference, scope, f'sécurité de méthode non interprétée ({", ".join(hidden)})')
            return
        guard = methods.guard(java_file, endpoint.java_type, endpoint.methods[0], endpoint.handler,
                              self.deployment.types)
        if guard is None:
            self._gap(endpoint.reference, scope, 'sécurité de méthode non interprétée (@PreAuthorize non résolue '
                                                 'vers Spring)')
            return
        if guard.expression is None:
            self._gap(endpoint.reference, scope, 'sécurité de méthode non interprétée (expression @PreAuthorize '
                                                 'non résolue)')
            return
        annotation = guard.annotation
        evidence = [self._evidence(endpoint.path, annotation.line_start, annotation.line_end, PRE_AUTHORIZE_METHOD)]
        qualifiers = {'annotation': PRE_AUTHORIZE}
        self._add(_observed(guard.symbol, 'AUTHORIZED_BY', guard.expression, evidence, qualifiers))
        if not guard.restrictive:
            self._gap(endpoint.reference, scope,
                      'sécurité de méthode non interprétée (@PreAuthorize : expression non évaluée)')
            return
        sealed = sorted(UNADVISABLE & _modifiers(endpoint.java_type, endpoint.methods[0]))
        if sealed:
            # Un proxy Spring (sous-classe CGLIB ou interface) n'intercepte pas une methode final, private ou static.
            self._gap(endpoint.reference, scope, f'sécurité de méthode non interprétée (méthode {" ".join(sealed)} : '
                                                 'non interceptée par un proxy Spring)')
            return
        if 'final' in endpoint.java_type.modifiers:
            # Spring Boot proxie par sous-classe : une classe final ne peut pas l'etre.
            self._gap(endpoint.reference, scope, 'sécurité de méthode non interprétée (classe final : non proxiable '
                                                 'par sous-classe)')
            return
        enabling = self._enabling(endpoint)
        if enabling is None:
            return
        premises = [f'HANDLED_BY : {endpoint.reference} -> {endpoint.handler}',
                    f'AUTHORIZED_BY : {guard.symbol} -> {guard.expression}', *enabling[0]]
        # Une liste neuve : les preuves de l'AUTHORIZED_BY observe restent celles de l'annotation seule.
        evidence = [*evidence, *enabling[1]]
        gaps = [DATA_GAP] if any(f'{action}(' in guard.expression for action in ROLE_ACTIONS) else []
        self._add({**_observed(endpoint.reference, 'PROTECTED_BY', f'policy-rule:{guard.expression.strip()}',
                               evidence, qualifiers), 'status': 'INFERRED',
                   'derivation': {'premises': premises, 'rule': METHOD_APPLIES, 'counter_examples_checked': [],
                                  'known_gaps': gaps}})
        self.method_protected += 1

    def _enabling(self, endpoint):
        """(premisses, preuves) de l'activation de la securite de methode pour l'application qui sert l'endpoint ;
        None, la raison declaree, si elle n'est pas etablie."""
        scope = f'file:{endpoint.path}'
        enabled = [item for item in self.enablings if item.state == methods.ENABLED]
        if not enabled:
            self._gap(endpoint.reference, scope, 'sécurité de méthode : activation non établie (aucune '
                                                 '@EnableMethodSecurity lue qui active @PreAuthorize)')
            return None
        if not self.deployment.applications:
            # Sans application Spring Boot lue, rien ne dit qu'une activation lue est chargee avec cette route.
            self._gap(endpoint.reference, scope, 'sécurité de méthode : application qui sert la route non établie '
                                                 '(aucune application Spring Boot lue)')
            return None
        outcomes = [(application, self.deployment.loads(application, endpoint.java_type.qualified_name).outcome)
                    for application in self.deployment.applications]
        if any(outcome == UNKNOWN for _, outcome in outcomes):
            self._gap(endpoint.reference, scope, 'sécurité de méthode : application qui sert la route non établie')
            return None
        serving = [application for application, outcome in outcomes if outcome == YES]
        chosen = []
        for application in serving:
            loaded = [item for item in enabled if self.deployment.loads(application, item.owner).outcome == YES]
            if not loaded:
                self._gap(endpoint.reference, scope, f'sécurité de méthode : activation par '
                                                     f'{application.reference} non établie')
                return None
            chosen += [item for item in loaded if item not in chosen]
        if not chosen:
            self._gap(endpoint.reference, scope, 'sécurité de méthode : aucune application établie ne sert '
                                                 'cette route')
            return None
        premises = [f'ANNOTATED_WITH : {item.symbol} -> {item.reference}' for item in chosen]
        evidence = [self._evidence(item.path, item.annotation.line_start, item.annotation.line_end, ENABLING_METHOD)
                    for item in chosen]
        return premises, evidence

    def _endpoint(self, endpoint, configurations, serving):
        """Rattache l'endpoint a sa regle gagnante, ou dit pourquoi il ne le peut pas."""
        if self._ignored(endpoint, serving.applications):
            return
        configuration = self._configuration(endpoint, configurations)
        if configuration is None:
            return
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
            self._conclude(endpoint, configuration, checked, rule, serving)
            return
        self._gap(endpoint.reference, scope, 'aucune règle ne capture la route')

    def _ignored(self, endpoint, applications):
        """Vrai si une exclusion `web.ignoring()` peut viser la route : elle est alors declaree, pas conclue."""
        for path, patterns, line, owner, method in self.ignored:
            if applications and all(self.deployment.loads_bean(application, owner, method).outcome == NO
                                    for application in applications):
                # Une exclusion qu'aucune application qui sert la route ne charge ne s'y applique pas.
                continue
            if patterns is None or max(rules.match(pattern, endpoint.route) for pattern in patterns) != rules.NONE:
                self._gap(endpoint.reference, f'file:{path}', f'exclusion web.ignoring() ligne {line} non écartée')
                return True
        return False

    def _configuration(self, endpoint, configurations):
        """La seule chaine de filtres qui traite toute requete de la route, ou None (et la raison declaree)."""
        candidates = [(item, item.applies(endpoint.route)) for item in configurations]
        candidates = [(item, applies) for item, applies in candidates if applies != rules.NONE]
        if len(candidates) == 1 and candidates[0][1] == rules.ALL:
            return candidates[0][0]
        if len(candidates) == 1:
            self._gap(endpoint.reference, f'file:{candidates[0][0].path}',
                      'périmètre de la chaîne de filtres non établi pour cette route')
        else:
            self._gap(endpoint.reference, f'repository:{self.snapshot.repository}',
                      f'{len(candidates)} chaînes de filtres candidates')
        return None

    def _conclude(self, endpoint, configuration, checked, winner, serving):
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
            premises=[f'HANDLED_BY : {endpoint.reference} -> {endpoint.handler}', *serving.premises,
                      *[rule.describe() for rule in (*checked, winner)]],
            rule=FIRST_MATCH, checked=[*serving.checked, *[f'{rule.describe()} : ne correspond pas' for rule in checked]],
            gaps=[*serving.gaps, *([winner.note] if winner.note else [])])
        self._add(matched)
        self.matched += 1
        if winner.permits:
            return
        target = winner.target or f'policy-rule:{winner.expression}'
        gaps = _protection_gaps(winner)
        self._add(_inference(
            endpoint.reference, 'PROTECTED_BY', target, evidence, chain,
            premises=[f'MATCHED_BY : {endpoint.reference} -> {pattern}',
                      f'AUTHORIZED_BY : {pattern} -> {winner.target or winner.expression}'],
            rule=APPLIES, checked=[], gaps=[*serving.gaps, *gaps]))
        self.protected += 1

    def _evidence(self, path, line_start, line_end, method):
        data = self.analysis.contents[path]
        return {'repository': self.snapshot.repository, 'commit': self.snapshot.commit, 'path': path,
                'line_start': line_start, 'line_end': line_end, 'method': method,
                'content_hash': content_hash(data, line_start, line_end)}


def _merge(first, second):
    """Contexte de plusieurs applications qui chargent les memes chaines : leurs premisses reunies."""
    unique = lambda items: list(dict.fromkeys(items))
    return _Serving(unique(first.premises + second.premises), unique(first.checked + second.checked),
                    unique(first.gaps + second.gaps), first.applications + second.applications)


def _protection_gaps(winner):
    """Ce que la protection deduite ne dit pas : la decision d'un gestionnaire, les roles effectifs."""
    if winner.target:
        return [f'la décision de {winner.target} n’est pas lue']
    if winner.action in ROLE_ACTIONS:
        return [DATA_GAP]
    if winner.action == 'access':
        return ['l’expression d’autorisation n’est pas évaluée']
    return []


def _assertion(subject, relation, target, evidence, chain):
    """PERMITS_ALL est la seule relation sans objet (ARCHITECTURE § 5). Le qualificatif `filter_chain` nomme la chaine de
    filtres qui porte la regle : deux chaines peuvent traiter le meme motif differemment."""
    fact = {'contract_version': 1, 'kind': 'ASSERTION', 'status': 'OBSERVED', 'validity': 'VALID',
            'subject': subject, 'relation': relation, 'qualifiers': {'filter_chain': chain}, 'evidence': evidence}
    if target is not None:
        fact['object'] = target
    return fact


def _modifiers(java_type, method):
    """Les modificateurs ecrits de la methode, lus sur sa declaration (les methodes annotees n'en portent pas)."""
    return next((item.modifiers for item in java_type.declarations
                 if item.signature == method.signature and item.line_start == method.line_start), frozenset())


def _observed(subject, relation, target, evidence, qualifiers):
    """Un fait ecrit dans le code, hors regle d'URL : ses qualificatifs ne nomment pas de chaine de filtres."""
    return {'contract_version': 1, 'kind': 'ASSERTION', 'status': 'OBSERVED', 'validity': 'VALID',
            'subject': subject, 'relation': relation, 'object': target, 'qualifiers': qualifiers,
            'evidence': evidence}


def _inference(subject, relation, target, evidence, chain, premises, rule, checked, gaps):
    return {'contract_version': 1, 'kind': 'ASSERTION', 'status': 'INFERRED', 'validity': 'VALID',
            'subject': subject, 'relation': relation, 'object': target, 'qualifiers': {'filter_chain': chain},
            'evidence': evidence,
            'derivation': {'premises': premises, 'rule': rule, 'counter_examples_checked': checked,
                           'known_gaps': gaps}}


def _coverage(subject, coverage_type, scope, reason=None):
    """Une couverture ; `reason` dit pourquoi une zone n'est pas interpretee (hors identite du fait)."""
    fact = {'contract_version': 1, 'kind': 'COVERAGE', 'status': 'OBSERVED', 'validity': 'VALID',
            'subject': subject, 'coverage_type': coverage_type, 'scope': {'include': [scope]}}
    return {**fact, 'reason': reason} if reason else fact
