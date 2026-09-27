"""Evaluateur Spring Boot (TAXO-E1, tranche 2 ; ADR 0012) : les applications et les routes qu'elles servent.

Il reprend les endpoints de l'evaluateur Spring API et la structure du depot (modules, dependances), et
produit :

- `application:<fichier>#<Type>` BUILT_FROM `module:<dossier>` pour chaque `@SpringBootApplication` des
  sources principales d'un module : `OBSERVED`, preuve a l'annotation ;
- `endpoint` SERVED_BY `application` quand l'application charge le controleur de la route : `INFERRED`, sur
  le classpath (BUILT_FROM, DEPENDS_ON) et le balayage (ou l'import) du controleur, sans condition.

Une application dont le classpath ou le balayage ne s'etablit pas, un controleur dont le chargement reste
inconnu (condition, auto-configuration, annotation non resolue) : NOT_INTERPRETED, jamais une route
attribuee par paquetage, proximite ou nom.
"""
from app.evaluations.domain.evaluator import EvaluationOutput
from app.evaluations.domain.progress import silent
from app.evaluations.domain.status import EvaluationStatus
from app.evaluators.spring_api.evaluator import analyse
from app.facts import content_hash
from .applications import UNKNOWN, YES, Deployment
from .catalog import CATALOG

ENTRY_METHOD = 'java.spring-boot.application'
COMPONENT_METHOD = 'java.spring-boot.component'
SERVES = 'spring-boot.application-loads-controller'


class SpringBootEvaluator:
    evaluator_id = 'taxo.spring-boot'
    producer_version = '0.1.0'
    catalog = CATALOG

    def evaluate(self, snapshot, progress=silent):
        repository = f'repository:{snapshot.repository}'
        analysis = analyse(snapshot, progress)
        deployment = Deployment(snapshot, analysis)
        run = _Run(snapshot, analysis, deployment)
        run.evaluate()
        progress('applications', 'Applications Spring Boot', len(deployment.applications))
        coverage = [{**_coverage(repository, 'ANALYSED', repository), 'scope': analysis.scope(repository)}]
        coverage += [_coverage(subject, 'NOT_INTERPRETED', scope) for subject, (scope, _) in sorted(run.gaps.items())]
        coverage += [_coverage(subject, 'READ_ERROR', subject) for subject in analysis.read_errors]
        warnings = analysis.warnings + run.warnings + [
            f'{subject} : {" ; ".join(reasons)}' for subject, (_, reasons) in sorted(run.gaps.items())]
        status = EvaluationStatus.PARTIAL if run.gaps or analysis.read_errors else EvaluationStatus.SUCCESS
        legacy = {'applications': len(deployment.applications), 'served': run.served}
        return EvaluationOutput(tuple(run.facts), tuple(coverage), status, tuple(warnings), legacy)


class _Run:
    def __init__(self, snapshot, analysis, deployment):
        self.snapshot, self.analysis, self.deployment = snapshot, analysis, deployment
        self.facts, self.gaps, self.warnings = [], {}, []
        self.served = 0

    def evaluate(self):
        for subject, (path, message) in self.analysis.run.gaps.items():
            # Une route que l'analyse des endpoints n'a pas etablie n'est servie par personne a coup sur.
            self._gap(subject, f'file:{path}', f'routes non établies par l’analyse des endpoints ({message})')
        for application in self.deployment.applications:
            scope = f'file:{application.path}'
            if application.module is not None:
                evidence = [self._evidence(application.path, application.annotation, ENTRY_METHOD)]
                self.facts.append(_assertion(application.reference, f'module:{application.module}', evidence))
            if application.reason:
                self._gap(application.reference, scope, application.reason)
        if not self.deployment.applications:
            if self.analysis.run.facts:
                self.warnings.append('Aucune application @SpringBootApplication : l’application qui sert chaque '
                                     'route n’est pas établie.')
            return
        for endpoint in self.analysis.endpoints():
            self._endpoint(endpoint)

    def _endpoint(self, endpoint):
        qualified = endpoint.java_type.qualified_name
        serving = False
        for application in self.deployment.applications:
            loading = self.deployment.loads(application, qualified)
            if loading.outcome == UNKNOWN:
                self._gap(endpoint.reference, f'file:{endpoint.path}',
                          f'servie peut-être par {application.reference} ({loading.reason})')
            elif loading.outcome == YES:
                serving = True
                self.facts.append(self._served(endpoint, application, loading))
        if serving:
            self.served += 1

    def _served(self, endpoint, application, loading):
        java_file, java_type = self.deployment.types[endpoint.java_type.qualified_name]
        stereotype = next((item for item in java_type.annotations
                          if self.deployment.resolve(java_file, item.name) in _CONTROLLERS), java_type.annotations[0])
        evidence = [self._evidence(application.path, application.annotation, ENTRY_METHOD),
                    self._evidence(endpoint.path, stereotype, COMPONENT_METHOD)]
        return {'contract_version': 1, 'kind': 'ASSERTION', 'status': 'INFERRED', 'validity': 'VALID',
                'subject': endpoint.reference, 'relation': 'SERVED_BY', 'object': application.reference,
                'qualifiers': {}, 'evidence': evidence,
                'derivation': {'premises': [f'HANDLED_BY : {endpoint.reference} -> {endpoint.handler}',
                                            *loading.premises],
                               'rule': SERVES, 'counter_examples_checked': [], 'known_gaps': []}}

    def _gap(self, subject, scope, reason):
        _, reasons = self.gaps.setdefault(subject, (scope, []))
        if reason not in reasons:
            reasons.append(reason)

    def _evidence(self, path, annotation, method):
        data = self.analysis.contents[path]
        return {'repository': self.snapshot.repository, 'commit': self.snapshot.commit, 'path': path,
                'line_start': annotation.line_start, 'line_end': annotation.line_end, 'method': method,
                'content_hash': content_hash(data, annotation.line_start, annotation.line_end)}


_CONTROLLERS = {'org.springframework.web.bind.annotation.RestController', 'org.springframework.stereotype.Controller'}


def _assertion(application, module, evidence):
    return {'contract_version': 1, 'kind': 'ASSERTION', 'status': 'OBSERVED', 'validity': 'VALID',
            'subject': application, 'relation': 'BUILT_FROM', 'object': module, 'qualifiers': {},
            'evidence': evidence}


def _coverage(subject, coverage_type, scope):
    return {'contract_version': 1, 'kind': 'COVERAGE', 'status': 'OBSERVED', 'validity': 'VALID',
            'subject': subject, 'coverage_type': coverage_type, 'scope': {'include': [scope]}}
