"""Protocole Taxo, operations v1 (TAXO-QUERY-02, ARCHITECTURE § 12).

Un echange est ouvert sur un projet et sa derniere analyse : l'instantane est fixe a l'ouverture et ne
change plus. Chaque operation est en lecture seule, deterministe, et repond dans l'enveloppe commune.
Les faits recoivent une reference courte (`F1`…), leurs preuves aussi (`E1`…), stables dans l'echange :
seules les references effectivement transmises existent.

Le protocole ne connait ni langage, ni framework, ni projet : il interroge des relations et des
references du contrat (ARCHITECTURE § 5). Ce que sait chaque analyseur vient de son catalogue.
"""
import json
import logging

from app.evaluations.domain.capability import (INCOMPLETE, LANGUAGE, UNREAD_COVERAGE, WRITTEN_IN, CatalogContracts,
                                               languages_complete, present_languages)
from app.facts.domain.fact import RELATIONS
from app.history.domain.errors import UNKNOWN_COMMIT, UNKNOWN_PATH, HistoryError
from app.projects.application.queries import require_project
from app.projection.domain.errors import NO_ANALYSIS, QueryError
from app.protocol.domain.envelope import (BUDGET_EXHAUSTED, INTERNAL, INVALID_ARGUMENT, MAX_ERROR_BYTES,
                                          NO_CONSENT, NOT_AVAILABLE, OUT_OF_SCOPE, PROTOCOL, OperationError,
                                          Response, error)
from app.knowledge.application.loader import analysis_languages, from_coverage, from_summary
from app.protocol.application.commits import HISTORY as _HISTORY, CommitOperations
from app.protocol.application.ports import FactReading
from app.protocol.application.arguments import claim_object as _claim_object, no_other as _no_other
from app.protocol.application.arguments import reference as _reference, relation as _relation, text as _text
from app.knowledge.domain.knowledge import AnalysisKnowledge, contains
from app.protocol.domain.verdict import judge
from app.neighborhood.application.references import find_references
from app.neighborhood.domain import handle, references
from app.protocol.application.neighborhood_operation import neighborhood

logger = logging.getLogger(__name__)

DEFAULT_OPERATION_BYTES = 8_000
MAX_OPERATION_BYTES = 32_000
DEFAULT_EXCHANGE_BYTES = 64_000
MAX_EXCHANGE_BYTES = 200_000
MAX_OPERATIONS = 20
# Chaque operation encore possible garde de quoi repondre par un refus : le budget n'est jamais depasse.
ERROR_RESERVE = MAX_OPERATIONS * MAX_ERROR_BYTES
MIN_EXCHANGE_BYTES = ERROR_RESERVE + 6_000

_ASSERTION, _LANGUAGES = 'ASSERTION', 'languages'
# Les types de reference que le vocabulaire peut nommer, de part et d'autre de ses relations.
_REFERENCE_TYPES = frozenset(kind for sources, targets, _ in RELATIONS.values() for kind in (*sources, *targets))
NATURES = (_ASSERTION, 'ABSENCE', 'COVERAGE')
V1 = ('describe', 'find_facts', 'get_evidence', 'get_coverage', 'get_commit', 'get_diff', 'verify_claim')
# Operations reservees d'ARCHITECTURE § 12 que Taxo sait deja servir : `diff_facts` s'appuie sur l'impact d'un
# commit (comparaison des faits des evaluateurs de contenu entre le parent et le commit, TAXO-HIST-01).
ACTIVATED = ('diff_facts', 'get_neighborhood', 'find_references')
OPERATIONS = V1 + ACTIVATED
RESERVED = ('find_endpoint', 'trace_access_control', 'find_callers', 'find_callees', 'find_dependencies',
            'find_configuration', 'get_source')
# Ce que `describe` dit des arguments de chaque operation.
_COMMIT_ARGUMENT = {'commit': 'identifiant, 7 caracteres ou plus'}
_CLAIM_ARGUMENTS = {'subject': 'reference', 'relation': 'relation', 'object': 'reference ou valeur'}
_ARGUMENTS = {
    'describe': {},
    'find_facts': {**_CLAIM_ARGUMENTS, 'nature': '|'.join(NATURES)},
    'get_evidence': {'fact': 'F… de cet échange', 'occurrence': 'poignée d’occurrence (au lieu de fact)'},
    'get_coverage': {'scope': 'reference (facultatif)'},
    'get_commit': _COMMIT_ARGUMENT,
    'get_diff': {**_COMMIT_ARGUMENT, 'path': 'chemin d’un fichier touche'},
    'verify_claim': _CLAIM_ARGUMENTS,
    'diff_facts': _COMMIT_ARGUMENT,
    'get_neighborhood': {'engine': 'neighborhood/1|neighborhood/2 (facultatif ; sinon neighborhood/1 pour une '
                                   'demande qui y est valide, neighborhood/2 pour toute autre)',
                         'analysis': 'identifiant de l’analyse', 'root': 'reference',
                         'steps': 'liste de {relation, direction} (neighborhood/2 ; exclut follow, direction, '
                                  'priority)',
                         'follow': 'liste de relations', 'direction': 'INCOMING|OUTGOING|BOTH (BOTH : neighborhood/2)',
                         'depth': '1..4 (au-delà de 1 : neighborhood/2)',
                         'priority': 'ordre de follow (facultatif)',
                         'max_nodes': '1..200', 'max_edges': '1..400 (au-delà de 200 : neighborhood/2)',
                         'max_work': '1..2000 (au-delà de 1000 : neighborhood/2)',
                         'max_fanout': '1..200 (neighborhood/2, facultatif)',
                         'evidence': 'NONE|SUMMARY (neighborhood/2)',
                         'form': 'FULL|COMPACT (neighborhood/2 ; COMPACT : instantané et provenance une fois, '
                                 'renvois par indice)',
                         'continuation': 'reprise d’une adjacence coupée (facultatif)'},
    'find_references': {'analysis': 'identifiant de l’analyse', 'prefix': 'début de la clé (après le type), 1..200',
                        'type': 'type de référence (facultatif)', 'limit': '1..50', 'after': 'reprise (facultatif)'},
}


def _without_evidence(fact):
    return {key: value for key, value in fact.items() if key != 'evidence'}


def _coverage_entry(fact, reads):
    """Une couverture, et les langages que son producteur lit quand il en lit en propre : elle ne vaut que
    pour eux (TAXO-COV-01). Un producteur independant du langage n'en porte pas ; un contrat inconnu n'en
    nomme aucun."""
    entry = {'subject': fact['subject'], 'type': fact['coverage_type'], 'scope': fact['scope'],
             'producer': fact.get('produced_by', {}).get('producer_id')}
    return entry if reads.independent else {**entry, _LANGUAGES: reads.listed()}


class References:
    """References courtes d'un echange : un meme fait, une meme reference."""

    def __init__(self):
        self.facts, self.by_key, self.evidence = {}, {}, {}

    @staticmethod
    def _key(fact):
        return json.dumps(fact, sort_keys=True, ensure_ascii=False)

    def fact(self, fact):
        """Reference du fait, et si elle vient d'etre creee."""
        key = self._key(fact)
        if key in self.by_key:
            return self.by_key[key], False
        ref = f'F{len(self.facts) + 1}'
        self.facts[ref], self.by_key[key] = fact, ref
        return ref, True

    def preview(self, keys):
        """Les references qu'auraient ces faits, donnes par leur cle (`key`), sans en creer aucune : une reponse
        provisoire se mesure avec les references qu'elle aurait."""
        refs, pending = [], {}
        for key in keys:
            ref = self.by_key.get(key) or pending.get(key)
            if ref is None:
                ref = pending[key] = f'F{len(self.facts) + len(pending) + 1}'
            refs.append(ref)
        return refs

    @classmethod
    def key(cls, fact):
        return cls._key(fact)

    def forget(self, ref):
        """Retire la derniere reference creee : son fait n'a pas ete transmis."""
        fact = self.facts.pop(ref)
        del self.by_key[self._key(fact)]

    def proof(self, fact_ref, index):
        key = (fact_ref, index)
        if key not in self.evidence:
            self.evidence[key] = f'E{len(self.evidence) + 1}'
        return self.evidence[key]


class TaxoQuery:
    """Ouvre des echanges du protocole sur les projets analyses."""

    def __init__(self, projects, scans, facts: FactReading, history, analyzers, source_context, contracts=None):
        # `facts` : le port de lecture des faits (`FactReading`). `analyzers` : les evaluateurs enregistres ;
        # seuls leur identifiant et leur catalogue servent.
        self.projects, self.scans, self.facts, self.history = projects, scans, facts, history
        self.catalogs = {item.evaluator_id: frozenset(item.catalog.relations) for item in analyzers}
        # Ce que chaque contrat de catalogue lit (TAXO-COV-01), par identite et version : une couverture
        # enregistree s'interprete selon le contrat du producteur qui l'a ecrite. La composition fournit la
        # meme valeur a toutes les operations ; a defaut, elle se deduit des evaluateurs.
        self.contracts = contracts if contracts is not None else CatalogContracts(item.catalog for item in analyzers)
        self.source_context = source_context

    def reads_of(self, evaluation):
        """Ce que lit le contrat de catalogue qu'une execution resumee nomme ; inconnu s'il n'en nomme aucun."""
        return self.contracts.reads(evaluation.get('catalog_id'), evaluation.get('catalog_version'))

    def open(self, project_id, diff_consent=False, max_bytes=None, analysis_id=None):
        project = require_project(self.projects, project_id)
        analyses = ([self.scans.get(project_id, analysis_id)] if analysis_id is not None
                    else self.scans.list(project_id))
        if not analyses or analyses[0] is None:
            raise QueryError(NO_ANALYSIS, "Aucune analyse globale pour ce projet : lancez-la d'abord.")
        budget = max(MIN_EXCHANGE_BYTES, min(max_bytes or DEFAULT_EXCHANGE_BYTES, MAX_EXCHANGE_BYTES))
        return Exchange(self, project.id, analyses[0], diff_consent, budget)


class Exchange:
    """Un echange : un projet, une analyse, un budget, des references."""

    def __init__(self, service, project_id, scan, diff_consent, budget):
        self.service, self.project_id, self.scan = service, project_id, scan
        self.diff_allowed = service.source_context == 'diff'
        self.diff_consent = bool(diff_consent) and self.diff_allowed
        self.budget, self.used, self.calls = budget, 0, 0
        self.refs = References()
        evaluations = scan.result.get('evaluations', [])
        reference = next((item['snapshot'] for item in evaluations if item.get('snapshot')), {})
        self.snapshot = {'analysis': scan.id, 'commit': reference.get('commit')}
        self.repository = f'repository:{reference["repository"]}' if reference.get('repository') else None
        self.evaluations = evaluations
        self._coverage = None
        self._languages = None
        self._commits = None

    # --- Contexte commun -------------------------------------------------------------------------

    @property
    def facts(self):
        """Le port des faits de l'analyse."""
        return self.service.facts

    @property
    def catalogs(self):
        """Les relations que chaque analyseur enregistre sait produire, d'apres son catalogue."""
        return self.service.catalogs

    def reads_of(self, evaluation):
        """Ce que lit le contrat de catalogue qu'une execution resumee nomme."""
        return self.service.reads_of(evaluation)

    @property
    def commits(self):
        """L'historique et le diff : un collaborateur avec son propre etat (les limites du diff, pour tout
        l'echange), cree au premier usage ; l'historique du projet n'est lu que par ces operations."""
        if self._commits is None:
            self._commits = CommitOperations(self, self.service.history)
        return self._commits

    def query(self, **filters):
        return self.service.facts.query(self.scan.id, **filters)

    def own(self, *references):
        """Un echange ne franchit jamais la frontiere de son projet : un autre depot est hors perimetre."""
        for value in references:
            if value and value.startswith('repository:') and value != self.repository:
                raise OperationError(OUT_OF_SCOPE, 'Ce dépôt n’est pas celui de cet échange.')

    @property
    def coverage(self):
        if self._coverage is None:
            self._coverage = self.query(kind='COVERAGE')
        return self._coverage

    @property
    def languages(self):
        """Les langages de l'analyse (TAXO-COV-01) ; une analyse anterieure les relit dans ses faits."""
        if self._languages is None:
            self._languages = analysis_languages(self.scan, self.service.facts)
        return self._languages

    @property
    def complete(self):
        """L'inventaire a-t-il tout lu ? Sinon ses langages ne disent pas ce qui est absent."""
        return languages_complete(self.scan.result.get('evaluation_summary'))

    def needed(self, subject):
        """Ou un sujet aurait pu etre etabli : les langages de son fichier ; sinon `None`, tous les langages
        presents, et ceux des fichiers que l'inventaire n'a pas lus."""
        if subject.startswith('file:'):
            return present_languages(self.query(subject=subject, relation=WRITTEN_IN, kind=_ASSERTION))
        return None

    def analyzers(self):
        """Les analyseurs de l'analyse, d'apres leurs couvertures enregistrees."""
        return from_coverage(self.evaluations, self.coverage, self.service.catalogs,
                             lambda *catalog: self.service.contracts.reads(*catalog))

    def summary_analyzers(self):
        """Les analyseurs tels que le resume de l'analyse les decrit : une lecture bornee, sans aucun fait.
        Le contrat et les executions ne sont lus que s'ils servent : une execution qui nomme son catalogue, un
        resume anterieur qui ne le nomme pas."""
        return from_summary(self.evaluations, self.catalogs, lambda evaluation: self.reads_of(evaluation),
                            lambda: self.facts.executions(self.scan.id))

    def knowledge(self, analyzers=None):
        """Ce que l'analyse sait d'elle-meme : langages presents, inventaire complet, analyseurs vus."""
        return AnalysisKnowledge(self.languages, self.complete,
                                 tuple(self.analyzers() if analyzers is None else analyzers))

    def envelope_coverage(self, relation=None, concerned=()):
        """Ou Taxo a cherche : la couverture du depot des analyseurs concernes, et celle des references
        visees. Toujours presente, meme pour un resultat vide. Pour une relation, chaque langage present
        qu'aucune execution capable n'a lu est nomme : une absence de preuve, jamais une preuve d'absence."""
        analyzers = self.analyzers()
        chosen = [item for item in analyzers if relation is None or relation in item.relations]
        entries = [_coverage_entry(fact, analyzer.reads) for analyzer in chosen for fact in analyzer.coverage
                   if fact['subject'].startswith('repository:') or fact['subject'] in concerned]
        if relation is not None and chosen:
            # Les langages ne sont lus que pour une relation : une analyse anterieure les relit dans ses faits.
            knowledge = self.knowledge(analyzers)
            entries += [{'subject': f'{LANGUAGE}{language}', 'type': 'NOT_ANALYSED', 'scope': None,
                         'producer': None, 'relation': relation}
                        for language in knowledge.not_analysed(relation)]
            if knowledge.languages_unknown(relation):
                entries.append({'subject': None, 'type': 'NOT_ANALYSED', 'scope': None, 'producer': None,
                                'relation': relation, 'reason': INCOMPLETE})
        return entries or [{'subject': None, 'type': 'NOT_ANALYSED', 'scope': None, 'producer': None,
                            'relation': relation}]

    def _history_available(self):
        return any(item.get('status') != 'FAILED' and _HISTORY in self.service.catalogs.get(
            item['evaluator_id'], frozenset(item.get('relations', {}))) for item in self.evaluations)

    def available(self):
        operations = ['describe', 'find_facts', 'get_evidence', 'get_coverage', 'verify_claim', 'get_neighborhood',
                      'find_references']
        if self._history_available():
            operations += ['get_commit', 'diff_facts']
            if self.diff_allowed:
                operations.append('get_diff')
        return [name for name in OPERATIONS if name in operations]

    def response(self, operation, coverage, max_bytes, **fields):
        response = Response(operation, self.snapshot, coverage, max_bytes, **fields)
        if not response.fits:
            raise OperationError(BUDGET_EXHAUSTED, 'Plus assez de place pour cette réponse et sa couverture.')
        return response

    def _add_fact(self, response, fact, evidence=False):
        """Ajoute un fait (et, sur demande, ses preuves) ; rend False s'il n'a pas tenu."""
        ref, new = self.refs.fact(fact)
        item = {'ref': ref, 'fact': _without_evidence(fact), 'evidence_count': len(fact.get('evidence', []))}
        if not response.add('items', item):
            if new:
                self.refs.forget(ref)
            return False
        if evidence:
            self._add_evidence(response, ref, fact)
        return True

    def _add_evidence(self, response, ref, fact):
        for index, proof in enumerate(fact.get('evidence', [])):
            entry = {'ref': self.refs.proof(ref, index), 'fact': ref, 'location': proof}
            if not response.add('evidence', entry):
                response.skip('evidence', len(fact['evidence']) - index - 1)
                return

    def add_facts(self, response, facts, evidence=False):
        for index, fact in enumerate(facts):
            if not self._add_fact(response, fact, evidence):
                response.skip('items', len(facts) - index - 1)
                return

    # --- Appel ---------------------------------------------------------------------------------------

    def call(self, request):
        """Rend la reponse d'une operation. Au plus MAX_OPERATIONS appels par echange : au-dela, l'echange
        est clos et l'appel est une erreur de programmation de l'appelant, pas une reponse du protocole."""
        if self.calls >= MAX_OPERATIONS:
            raise RuntimeError(f'Échange clos : au plus {MAX_OPERATIONS} opérations.')
        self.calls += 1
        operation = _operation(request)
        try:
            arguments, max_bytes = self._admitted(request, operation)
            result = _SERVED[operation](self, arguments, max_bytes).close()
        except Exception as exc:  # noqa: BLE001 - chaque echec devient un resultat de l'enveloppe
            result = self._failure(operation, exc)
        self.used += result['bytes']
        return result

    def _admitted(self, request, operation):
        """Les arguments et la taille permise d'une requete recevable ; sinon le refus du protocole."""
        if not isinstance(request, dict) or request.get('protocol', PROTOCOL) != PROTOCOL:
            raise OperationError(INVALID_ARGUMENT, f'Protocole attendu : {PROTOCOL}.')
        arguments = request.get('arguments') or {}
        if not isinstance(arguments, dict):
            raise OperationError(INVALID_ARGUMENT, 'Les arguments forment un objet.')
        max_bytes = self._max_bytes(request.get('max_bytes'))
        if operation in RESERVED:
            raise OperationError(NOT_AVAILABLE, f'{operation} attend un analyseur qui le rende possible.')
        if operation is None:
            raise OperationError(INVALID_ARGUMENT, f'Opération inconnue : {str(request.get("operation"))[:100]}.')
        if operation not in self.available():
            if operation == 'get_diff' and self._history_available():
                raise OperationError(NO_CONSENT, 'La lecture du diff est désactivée pour ce Taxo.')
            raise OperationError(NOT_AVAILABLE, f'{operation} : aucun analyseur ne le nourrit pour ce projet.')
        return arguments, max_bytes

    def _failure(self, operation, exc):
        """Un echec devient un resultat de l'enveloppe ; une panne de Taxo reste un resultat, jamais une
        instruction ni un detail interne. Appele pendant le traitement de l'exception, pour la tracer."""
        if isinstance(exc, OperationError):
            return error(operation, self.snapshot, exc.code, str(exc))
        if isinstance(exc, HistoryError):
            code = OUT_OF_SCOPE if exc.code in {UNKNOWN_COMMIT, UNKNOWN_PATH} else NOT_AVAILABLE
            return error(operation, self.snapshot, code, str(exc))
        logger.exception('Opération %s en échec', operation)
        return error(operation, self.snapshot, INTERNAL, 'Taxo n’a pas pu servir cette opération.')

    def _max_bytes(self, requested):
        if requested is not None and (type(requested) is not int or requested < 1):
            raise OperationError(INVALID_ARGUMENT, 'max_bytes doit être un entier positif.')
        # Ce qui reste, moins la reserve des refus pour les operations suivantes ; toujours >= MAX_ERROR_BYTES.
        remaining = self.budget - self.used - (MAX_OPERATIONS - self.calls) * MAX_ERROR_BYTES
        return min(requested or DEFAULT_OPERATION_BYTES, MAX_OPERATION_BYTES, remaining)

    # --- Operations ----------------------------------------------------------------------------------

    def get_neighborhood(self, arguments, max_bytes):
        return neighborhood(self, arguments, max_bytes)

    def describe(self, arguments, max_bytes):
        _no_other(arguments, ())
        response = self.response('describe', self.envelope_coverage(), max_bytes,
                                  consent={'diff': self.diff_consent})
        for name in self.available():
            response.add('items', {'kind': 'operation', 'operation': name, 'arguments': _ARGUMENTS[name]})
        response.add('items', {'kind': _LANGUAGES, 'present': list(self.languages),
                                'complete': self.complete})
        for analyzer, evaluation in zip(self.analyzers(), self.evaluations):
            response.add('items', {'kind': 'analyzer', 'analyzer': analyzer.analyzer_id,
                                   'status': evaluation.get('status'), 'relations': sorted(analyzer.relations),
                                   _LANGUAGES: analyzer.reads.listed()})
        present = {}
        for evaluation in self.evaluations:
            for relation, count in evaluation.get('relations', {}).items():
                present[relation] = present.get(relation, 0) + count
        for relation in sorted(present):
            sources, targets, _ = RELATIONS.get(relation, (set(), set(), set()))
            response.add('items', {'kind': 'relation', 'relation': relation, 'count': present[relation],
                                   'subject_types': sorted(sources), 'object_types': sorted(targets)})
        return response

    def find_facts(self, arguments, max_bytes):
        _no_other(arguments, ('subject', 'relation', 'object', 'nature'))
        subject, relation = _reference(arguments, 'subject'), _relation(arguments)
        target, nature = _text(arguments, 'object'), _text(arguments, 'nature')
        if nature is not None and nature not in NATURES:
            raise OperationError(INVALID_ARGUMENT, f'nature : {", ".join(NATURES)}.')
        if not any((subject, relation, target, nature)):
            raise OperationError(INVALID_ARGUMENT, 'Au moins un de subject, relation, object ou nature.')
        self.own(subject, target)
        facts = self.query(subject=subject, relation=relation, object=target, kind=nature)
        coverage = self.envelope_coverage(relation, {subject, target} - {None})
        response = self.response('find_facts', coverage, max_bytes, count=len(facts))
        self.add_facts(response, facts)
        return response

    def get_evidence(self, arguments, max_bytes):
        _no_other(arguments, ('fact', 'occurrence'))
        if ('fact' in arguments) == ('occurrence' in arguments):
            raise OperationError(INVALID_ARGUMENT, 'fact (F… de cet échange) ou occurrence (poignée), l’un des deux.')
        if 'occurrence' in arguments:
            fact = self._handled(arguments['occurrence'])
            ref, _ = self.refs.fact(fact)
        else:
            ref = _text(arguments, 'fact', required=True)
            if ref not in self.refs.facts:
                raise OperationError(INVALID_ARGUMENT, f'{ref} n’a pas été transmis dans cet échange.')
            fact = self.refs.facts[ref]
        producer = fact.get('produced_by', {}).get('producer_id')
        coverage = [entry for entry in self.envelope_coverage(fact.get('relation'), {fact.get('subject')})
                    if entry['producer'] in (producer, None)]
        response = self.response('get_evidence', coverage, max_bytes, fact=ref)
        self._add_evidence(response, ref, fact)
        return response

    def _handled(self, value):
        """Le fait d'une poignée d'occurrence (TAXO-01J) : seulement de l'analyse de cet échange, à sa génération
        de faits, fixée avant la lecture et vérifiée après ; le même refus quelle que soit la raison."""
        revision = self.facts.revision(self.scan.id)
        try:
            key = handle.decode(value, self.scan.id, revision)
        except handle.HandleError as exc:
            raise OperationError(INVALID_ARGUMENT, str(exc)) from exc
        fact = self.facts.occurrence(self.scan.id, key)
        # La génération est vérifiée encore après la lecture : un ajout entre-temps fait refuser la poignée.
        if fact is None or self.facts.revision(self.scan.id) != revision:
            raise OperationError(INVALID_ARGUMENT, handle.REFUSED)
        return fact

    def find_references(self, arguments, max_bytes):
        """Les references de l'analyse qui commencent par un prefixe (TAXO-01J) : une page bornee, dans l'ordre
        de leur cle, avec une reprise. Une liste ordonnee : ni score ni compte de degre."""
        prefix, kind, limit = _search(arguments, self.scan.id)
        revision = self.facts.revision(self.scan.id)
        try:
            folded = references.prefix_key(prefix)
            after = references.decode(arguments.get('after'), self.scan.id, revision, folded, kind)
        except references.ReferenceSearchError as exc:
            raise OperationError(INVALID_ARGUMENT, str(exc)) from exc
        rows, more = find_references(self.facts, self.scan.id, prefix, kind, after, limit)
        if self.facts.revision(self.scan.id) != revision:
            # Comme une Tuile : une page ne mêle jamais deux générations, et sa reprise ne lie que la sienne.
            raise OperationError(INVALID_ARGUMENT, 'Les faits de cette analyse ont changé pendant la recherche ; '
                                                   'recommencer sans reprise.')
        coverage = self.envelope_coverage()
        # La page la plus longue qui tient avec sa reprise : celle-ci est mesuree avec la page, jamais ajoutee apres.
        for count in range(len(rows), 0 if rows else -1, -1):
            last = rows[count - 1][:2] if count < len(rows) or more else None
            token = references.encode(self.scan.id, revision, folded, kind, last) if last else None
            response = self.response('find_references', coverage, max_bytes, prefix=prefix, type=kind, next=token)
            if all(response.add('items', {'reference': row[2], 'type': row[3]}) for row in rows[:count]):
                response.skip('items', len(rows) - count)
                return response
        raise OperationError(BUDGET_EXHAUSTED, 'Le budget ne contient pas une seule référence.')

    def get_coverage(self, arguments, max_bytes):
        _no_other(arguments, ('scope',))
        scope = _reference(arguments, 'scope')
        self.own(scope)
        facts = [fact for fact in self.coverage if scope is None or contains(scope, fact['subject'])]
        # Ce qui n'a pas ete lu passe avant ce qui l'a ete : c'est la limite de ce que Taxo sait.
        facts.sort(key=lambda fact: fact['coverage_type'] not in UNREAD_COVERAGE)
        response = self.response('get_coverage', self.envelope_coverage(), max_bytes, count=len(facts))
        self.add_facts(response, facts)
        return response

    def get_commit(self, arguments, max_bytes):
        return self.commits.get_commit(arguments, max_bytes)

    def get_diff(self, arguments, max_bytes):
        return self.commits.get_diff(arguments, max_bytes)

    def diff_facts(self, arguments, max_bytes):
        return self.commits.diff_facts(arguments, max_bytes)

    def verify_claim(self, arguments, max_bytes):
        _no_other(arguments, ('subject', 'relation', 'object'))
        subject = _reference(arguments, 'subject', required=True)
        relation = _relation(arguments, required=True)
        target = _text(arguments, 'object')
        sources, _, _ = RELATIONS[relation]
        if subject.split(':', 1)[0] not in sources:
            raise OperationError(INVALID_ARGUMENT, f'{relation} ne s’applique pas à ce type de sujet.')
        _claim_object(relation, target)
        self.own(subject, target)
        claim = {'subject': subject, 'relation': relation}
        if target is not None:
            claim['object'] = target
        established = [fact for fact in self.query(subject=subject, relation=relation, kind=_ASSERTION)
                       if fact.get('validity', 'VALID') == 'VALID']
        verdict = judge(claim, established, self.knowledge(self.analyzers()), self.needed(subject))
        response = self.response('verify_claim', self.envelope_coverage(relation, {subject, target} - {None}),
                                  max_bytes, claim=claim, verdict=verdict.verdict, reason=verdict.reason)
        self.add_facts(response, list(verdict.facts), evidence=True)
        return response


def _search(arguments, analysis):
    """Les arguments d'une recherche de references, verifies : prefixe, type, taille de page."""
    _no_other(arguments, ('analysis', 'prefix', 'type', 'limit', 'after'))
    if arguments.get('analysis') != analysis:
        raise OperationError(INVALID_ARGUMENT, 'analysis doit identifier l’analyse de cet échange (describe).')
    prefix = arguments.get('prefix')
    if not isinstance(prefix, str) or not 1 <= len(prefix) <= references.MAX_PREFIX:
        raise OperationError(INVALID_ARGUMENT, f'prefix : de 1 à {references.MAX_PREFIX} caractères.')
    kind = arguments.get('type')
    if kind is not None and kind not in _REFERENCE_TYPES:
        raise OperationError(INVALID_ARGUMENT, 'type : un type de référence du vocabulaire.')
    limit = arguments.get('limit', references.DEFAULT_LIMIT)
    if type(limit) is not int or not 1 <= limit <= references.MAX_LIMIT:
        raise OperationError(INVALID_ARGUMENT, f'limit doit être un entier entre 1 et {references.MAX_LIMIT}.')
    return prefix, kind, limit


def _operation(request):
    """Le nom de l'operation demandee, s'il est du protocole : jamais une valeur arbitraire de l'appelant."""
    operation = request.get('operation') if isinstance(request, dict) else None
    return operation if operation in OPERATIONS or operation in RESERVED else None


# Chaque operation du protocole et ce qui la sert : une table explicite, jamais un nom recu de l'appelant.
_SERVED = {
    'describe': Exchange.describe,
    'find_facts': Exchange.find_facts,
    'get_evidence': Exchange.get_evidence,
    'get_coverage': Exchange.get_coverage,
    'get_commit': Exchange.get_commit,
    'get_diff': Exchange.get_diff,
    'verify_claim': Exchange.verify_claim,
    'diff_facts': Exchange.diff_facts,
    'get_neighborhood': Exchange.get_neighborhood,
    'find_references': Exchange.find_references,
}
