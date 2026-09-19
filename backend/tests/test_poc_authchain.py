"""TAXO-POC-01 : la chaine d'autorisation, sur un projet Spring neutre puis sur le banc.

Le projet neutre prouve le mecanisme et tourne partout, y compris en CI. Le banc
prouve la verite de reference et ne tourne que la ou le depot est present.
"""
import os
from pathlib import Path

import pytest

from app.evaluations.application.run_evaluator import RunEvaluator
from app.evaluations.domain.status import EvaluationStatus
from app.snapshots.domain.mode import COMMIT
from app.snapshots.domain.snapshot import Snapshot, SnapshotFile
from poc.authchain import AuthorizationChainPoc

CONTROLLER = '''package com.example.api;

@RestController
@RequestMapping("/api/v2/shops/{shopCode}/orders")
public class OrderController {

    private final OrderQuery orderQuery;

    @GetMapping
    @Operation(summary = "List the orders of a shop")
    public OrderPage list(@PathVariable("shopCode") String shopCode) {
        return orderQuery.list(shopCode);
    }
}
'''

SECURITY = '''package com.example.config;

public class SecurityConfiguration {

    private final PolicyAuthorizationManager policyAuthorizationManager;

    public SecurityFilterChain chain(HttpSecurity http) throws Exception {
        http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.OPTIONS, "/**").permitAll()
                        .requestMatchers(
                                "/error",
                                "/docs/**"
                        ).permitAll()
                        .requestMatchers(HttpMethod.POST, "/api/v2/sessions").permitAll()
                        .requestMatchers("/api/admin/**").hasAuthority(ADMIN)
                        .requestMatchers("/api/shops/**").access(policyAuthorizationManager)
                        .requestMatchers("/api/v2/**").access(policyAuthorizationManager)
                        .anyRequest().authenticated()
                );
        return http.build();
    }
}
'''

MANAGER = '''package com.example.security;

public class PolicyAuthorizationManager implements AuthorizationManager<RequestAuthorizationContext> {

    private final DecisionEvaluator decisionEvaluator;
    private final AuditTrail auditTrail;

    @Override
    public AuthorizationDecision check(Supplier<Authentication> authentication, RequestAuthorizationContext context) {
        Decision decision = decisionEvaluator.evaluate(subject, resource);
        return new AuthorizationDecision(decision.permitted());
    }
}
'''

BOUNDARY_FILTER = '''package com.example.security;

public class ShopBoundaryFilter extends OncePerRequestFilter {

    private final List<PathPattern> shopScopedPatterns = List.of(
            parser.parse("/api/shops/{shopId}/**"),
            parser.parse("/api/organizations/{orgId}/shops/{shopId}/**")
    );
}
'''

SOURCES = {
    'api/src/main/java/com/example/api/OrderController.java': CONTROLLER,
    'config/src/main/java/com/example/config/SecurityConfiguration.java': SECURITY,
    'security/src/main/java/com/example/security/PolicyAuthorizationManager.java': MANAGER,
    'security/src/main/java/com/example/security/ShopBoundaryFilter.java': BOUNDARY_FILTER,
}

ENDPOINT = 'endpoint:GET /api/v2/shops/{shopCode}/orders'
COMMIT_ID = 'b' * 40


class Sources:
    def __init__(self, sources):
        self.sources = sources

    def read_many(self, paths):
        for path in paths:
            yield path, self.sources[path].encode('utf-8')


def snapshot(sources=None):
    sources = SOURCES if sources is None else sources
    files = tuple(SnapshotFile(path, len(text.encode('utf-8')))
                  for path, text in sorted(sources.items()))
    return Snapshot('shop-platform', COMMIT_ID, COMMIT, files, content=Sources(sources))


def execute(target, sources=None):
    return RunEvaluator()(AuthorizationChainPoc(target), snapshot(sources))


def relation(execution, name):
    return next(fact for fact in execution.facts if fact.get('relation') == name)


def relations(execution):
    return [fact.get('relation') for fact in execution.facts]


@pytest.fixture(name='chain', scope='module')
def chain_fixture():
    return execute('GET /api/v2/shops/{shopCode}/orders')


def test_the_chain_is_complete_and_its_execution_succeeds(chain):
    assert chain.status is EvaluationStatus.SUCCESS
    assert {'HANDLED_BY', 'AUTHORIZED_BY', 'MATCHED_BY', 'PROTECTED_BY', 'CALLS'} <= set(relations(chain))


def test_handled_by_points_at_the_handler_with_three_evidences(chain):
    handled = relation(chain, 'HANDLED_BY')
    assert handled['subject'] == ENDPOINT
    assert handled['object'] == 'symbol:OrderController#list'
    lines = CONTROLLER.split('\n')
    cited = [lines[evidence['line_start'] - 1] for evidence in handled['evidence']]
    assert '@RequestMapping' in cited[0]
    assert '@GetMapping' in cited[1]
    assert 'public OrderPage list(' in cited[2]


def test_the_first_matching_rule_wins_over_the_similar_earlier_one(chain):
    matched = relation(chain, 'MATCHED_BY')
    assert matched['status'] == 'INFERRED'
    assert matched['object'] == 'route-pattern:/api/v2/**'
    checked = ' | '.join(matched['derivation']['counter_examples_checked'])
    assert '/api/shops/**' in checked, 'la regle voisine doit etre citee comme ecartee'
    assert matched['derivation']['premises'][-1].endswith('/api/v2/** -> access')


def test_protected_by_derives_from_matched_by_then_authorized_by_never_from_handled_by(chain):
    protected = relation(chain, 'PROTECTED_BY')
    assert protected['status'] == 'INFERRED'
    assert protected['object'] == 'symbol:PolicyAuthorizationManager'
    premises = protected['derivation']['premises']
    assert [premise.split(' :')[0] for premise in premises] == ['MATCHED_BY', 'AUTHORIZED_BY']
    assert 'HANDLED_BY' not in ' '.join(premises)
    assert protected['derivation']['known_gaps'], 'une inference doit declarer ce qui lui manque'


def test_authorized_by_is_observed_on_the_rule_line(chain):
    authorized = relation(chain, 'AUTHORIZED_BY')
    assert authorized['status'] == 'OBSERVED'
    assert authorized['subject'] == 'route-pattern:/api/v2/**'
    line = SECURITY.split('\n')[authorized['evidence'][0]['line_start'] - 1]
    assert '/api/v2/**' in line
    assert 'access(' in line


def test_the_manager_calls_the_policy_evaluator(chain):
    called = {fact['object'] for fact in chain.facts if fact.get('relation') == 'CALLS'}
    assert 'symbol:DecisionEvaluator' in called
    assert 'symbol:AuditTrail' not in called, 'une dependance jamais appelee ne produit pas CALLS'


def test_a_filter_whose_patterns_miss_the_route_is_an_absence_not_a_silence(chain):
    absences = [fact for fact in chain.facts if fact['kind'] == 'ABSENCE']
    assert [absence['pattern']['value'].split(' ')[0] for absence in absences] == ['ShopBoundaryFilter']


def test_the_undecidable_parts_are_declared_as_coverage(chain):
    declared = {(fact['subject'], fact['coverage_type']) for fact in chain.coverage}
    assert (ENDPOINT, 'OUT_OF_SCOPE') in declared, 'les roles exiges ne viennent pas du code'
    assert any(subject.endswith('ShopBoundaryFilter.java') and kind == 'NOT_INTERPRETED'
               for subject, kind in declared)


def test_a_public_route_is_permitted_not_protected():
    execution = execute('POST /api/v2/sessions', {**SOURCES, 'api/src/main/java/com/example/api/SessionController.java': '''package com.example.api;

@RestController
@RequestMapping("/api/v2/sessions")
public class SessionController {

    @PostMapping
    public TokenResponse open(@RequestBody Credentials credentials) {
        return tokens.open(credentials);
    }
}
'''})
    assert 'PROTECTED_BY' not in relations(execution)
    permitted = relation(execution, 'PERMITS_ALL')
    assert permitted['subject'] == 'route-pattern:/api/v2/sessions'
    assert 'object' not in permitted


def test_an_unreadable_earlier_rule_forbids_the_inference():
    blinded = SOURCES.copy()
    blinded['config/src/main/java/com/example/config/SecurityConfiguration.java'] = SECURITY.replace(
        '.requestMatchers("/api/admin/**")', '.requestMatchers(ADMIN_MATCHERS)')
    execution = execute('GET /api/v2/shops/{shopCode}/orders', blinded)
    assert execution.status is EvaluationStatus.PARTIAL
    matched = relation(execution, 'MATCHED_BY')
    assert matched['derivation']['known_gaps'], 'la regle non lue doit etre declaree'


def test_an_unknown_route_concludes_nothing():
    execution = execute('GET /api/v2/unknown')
    assert execution.status is EvaluationStatus.PARTIAL
    assert not execution.facts
    assert execution.coverage[0]['coverage_type'] == 'NOT_INTERPRETED'


BENCH_ROOT = os.environ.get('TAXO_POC_BENCH_ROOT', 'D:/Takibu/Takibo-IAM')
BENCH_COMMIT = '032788fb6db90470ce2a7cd71193f99f6ec1e57d'
BENCH_TARGET = 'GET /api/v1/orgs/{orgCode}/spaces/{spaceCode}/users'
REFERENCE = {
    'HANDLED_BY': ('symbol:ReadableUserQueryController#list', (31, 39, 46)),
    'AUTHORIZED_BY': ('symbol:PolicyBasedAuthorizationManager', (85,)),
}


@pytest.mark.skipif(not Path(BENCH_ROOT, '.git').exists(),
                    reason=f'depot du banc absent : {BENCH_ROOT}')
def test_the_bench_reproduces_the_reference_truth():
    from app.snapshots.infrastructure.git.reader import open_snapshot

    opened = open_snapshot(BENCH_ROOT, 'takibo-iam', COMMIT, BENCH_COMMIT)
    execution = RunEvaluator()(AuthorizationChainPoc(BENCH_TARGET), opened)
    assert execution.status is EvaluationStatus.SUCCESS
    for name, (expected, lines) in REFERENCE.items():
        fact = relation(execution, name)
        assert fact['object'] == expected
        assert tuple(evidence['line_start'] for evidence in fact['evidence']) == lines
    call = next(fact for fact in execution.facts
                if fact.get('relation') == 'CALLS' and fact['object'] == 'symbol:PolicyEvaluator')
    assert tuple(evidence['line_start'] for evidence in call['evidence']) == (45, 101)
    protected = relation(execution, 'PROTECTED_BY')
    assert protected['object'] == 'symbol:PolicyBasedAuthorizationManager'
    assert 'HANDLED_BY' not in ' '.join(protected['derivation']['premises'])
    absences = {fact['pattern']['value'].split(' ')[0] for fact in execution.facts
                if fact['kind'] == 'ABSENCE'}
    assert 'OrgBoundaryFilter' in absences, "le filtre ne s'applique pas, et cela doit etre dit"
