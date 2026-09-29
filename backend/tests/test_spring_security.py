"""TAXO-05 : la regle d'autorisation d'URL de chaque endpoint, et jamais une route declaree protegee ou publique a tort."""
from app.evaluations.application.run_evaluator import RunEvaluator
from app.evaluations.domain.status import EvaluationStatus
from app.evaluators.spring_security import rules
from app.evaluators.spring_security.evaluator import SpringSecurityEvaluator
from test_spring_api import snapshot

ROOT = 'svc/src/main/java/com/example'

MANAGER = '''package com.example.security;

public class PolicyManager implements AuthorizationManager<RequestAuthorizationContext> {
}
'''


SPRING = ('import org.springframework.http.HttpMethod;\n'
          'import org.springframework.security.config.annotation.web.builders.HttpSecurity;\n')


def config(body, imports=SPRING, extra=''):
    return f'''package com.example.security;

{imports}
@Configuration
public class SecurityConfig {{
    private final PolicyManager manager;
{extra}
    @Bean
    SecurityFilterChain chain(HttpSecurity http) throws Exception {{
        return http.csrf(csrf -> csrf.disable())
            .authorizeHttpRequests(auth -> auth
{body})
            .build();
    }}
}}
'''


RULES = '''                .dispatcherTypeMatchers(DispatcherType.FORWARD, DispatcherType.ERROR).permitAll()
                .requestMatchers(HttpMethod.POST, "/api/v1/auth/login").permitAll()
                .requestMatchers("/api/orgs/**").hasRole("ADMIN")
                .requestMatchers("/api/v1/**").access(manager)
                .anyRequest().authenticated()'''


def controller(name, prefix, methods):
    mapping = f'@RequestMapping("{prefix}")\n' if prefix else ''
    return f'''package com.example.web;

import org.springframework.web.bind.annotation.*;

@RestController
{mapping}public class {name} {{
{methods}
}}
'''


USERS = controller('UserController', '/api/v1/orgs/{orgCode}/users', '''
    @GetMapping
    public String list() { return ""; }
''')
AUTH = controller('AuthController', None, '''
    @PostMapping("/api/v1/auth/login")
    public String login() { return ""; }

    @RequestMapping("/api/v1/auth/{step}")
    public String step() { return ""; }

    @GetMapping("/health")
    public String health() { return ""; }
''')


def files(security=RULES, **extra):
    found = {f'{ROOT}/security/PolicyManager.java': MANAGER,
             f'{ROOT}/web/UserController.java': USERS, f'{ROOT}/web/AuthController.java': AUTH}
    if security is not None:
        found[f'{ROOT}/security/SecurityConfig.java'] = config(security)
    found.update({f'{ROOT}/{name}': text for name, text in extra.items()})
    return found


def evaluate(sources):
    return SpringSecurityEvaluator().evaluate(snapshot(sources))


def facts(output, relation):
    return {fact['subject']: fact for fact in output.facts if fact['relation'] == relation}


def gaps(output):
    return {item['subject'] for item in output.coverage if item['coverage_type'] == 'NOT_INTERPRETED'}


def test_the_winning_rule_is_the_first_that_captures_every_request_of_the_route():
    output = evaluate(files())
    matched = facts(output, 'MATCHED_BY')
    users = matched['endpoint:GET /api/v1/orgs/{orgCode}/users']
    assert users['status'] == 'INFERRED'
    assert users['object'] == 'route-pattern:/api/v1/**'
    # La regle /api/orgs/** ne capture pas /api/v1/orgs/... : elle est un contre-exemple, jamais la raison.
    checked = users['derivation']['counter_examples_checked']
    assert any('/api/orgs/**' in item for item in checked)
    assert any('POST /api/v1/auth/login' in item for item in checked)
    assert users['derivation']['rule'] == 'spring-security.first-matching-pattern'
    assert matched['endpoint:POST /api/v1/auth/login']['object'] == 'route-pattern:POST /api/v1/auth/login'
    assert matched['endpoint:GET /health']['object'] == 'route-pattern:/**'


def test_protection_rests_on_matched_by_then_authorized_by_never_on_handled_by():
    output = evaluate(files())
    protected = facts(output, 'PROTECTED_BY')
    users = protected['endpoint:GET /api/v1/orgs/{orgCode}/users']
    assert users['object'] == 'symbol:java:com.example.security.PolicyManager'
    assert users['derivation']['premises'] == [
        'MATCHED_BY : endpoint:GET /api/v1/orgs/{orgCode}/users -> route-pattern:/api/v1/**',
        'AUTHORIZED_BY : route-pattern:/api/v1/** -> symbol:java:com.example.security.PolicyManager']
    assert all('HANDLED_BY' not in premise for premise in users['derivation']['premises'])
    assert users['derivation']['known_gaps'], 'la decision du gestionnaire n est pas lue, et c est dit'
    assert protected['endpoint:GET /health']['object'] == 'policy-rule:authenticated()'
    assert 'endpoint:POST /api/v1/auth/login' not in protected, 'une route ouverte a tous n est pas protegee'


def test_each_readable_rule_is_an_observed_fact_with_its_line():
    output = evaluate(files())
    assert set(facts(output, 'PERMITS_ALL')) == {'route-pattern:POST /api/v1/auth/login'}
    authorized = {subject: fact['object'] for subject, fact in facts(output, 'AUTHORIZED_BY').items()}
    assert authorized == {'route-pattern:/api/orgs/**': 'hasRole("ADMIN")',
                          'route-pattern:/api/v1/**': 'symbol:java:com.example.security.PolicyManager',
                          'route-pattern:/**': 'authenticated()'}
    chains = {fact['qualifiers']['filter_chain'] for fact in output.facts}
    assert chains == {'symbol:java:com.example.security.SecurityConfig#chain(HttpSecurity)'}, 'chaque regle dit sa chaine de filtres'
    evidence = facts(output, 'AUTHORIZED_BY')['route-pattern:/api/orgs/**']['evidence'][0]
    lines = config(RULES).splitlines()
    assert '"/api/orgs/**"' in lines[evidence['line_start'] - 1]
    assert 'hasRole' in lines[evidence['line_end'] - 1]


def test_a_rule_that_captures_only_part_of_the_route_forbids_any_conclusion():
    output = evaluate(files())
    # POST /api/v1/auth/login est public, mais pas GET : la route ANY n'a pas une seule regle.
    step = 'endpoint:ANY /api/v1/auth/{step}'
    assert step not in facts(output, 'MATCHED_BY')
    assert step not in facts(output, 'PROTECTED_BY')
    assert step in gaps(output)
    assert output.status == EvaluationStatus.PARTIAL
    special = controller('MeController', '/users', '''
    @GetMapping("/{id}")
    public String one() { return ""; }
''')
    output = evaluate(files('''                .requestMatchers("/users/me").permitAll()
                .anyRequest().authenticated()''', **{'web/MeController.java': special}))
    assert 'endpoint:GET /users/{id}' in gaps(output), '/users/me est public : /users/{id} ne l est qu en partie'
    assert 'endpoint:GET /users/{id}' not in facts(output, 'PROTECTED_BY')


def test_an_unread_rule_blocks_every_conclusion_after_it_but_not_before():
    output = evaluate(files('''                .requestMatchers(HttpMethod.POST, "/api/v1/auth/login").permitAll()
                .requestMatchers(Unknown.PATHS).permitAll()
                .anyRequest().authenticated()'''))
    assert 'endpoint:POST /api/v1/auth/login' in facts(output, 'MATCHED_BY')
    assert 'endpoint:GET /health' not in facts(output, 'MATCHED_BY')
    assert {'endpoint:GET /health', 'endpoint:GET /api/v1/orgs/{orgCode}/users',
            'symbol:java:com.example.security.SecurityConfig#chain(HttpSecurity)'} <= gaps(output)
    assert not any('Unknown' in fact['subject'] for fact in output.facts), 'un motif non lu n est pas invente'


def test_an_expression_is_read_only_if_it_can_only_restrict():
    users = 'endpoint:GET /api/v1/orgs/{orgCode}/users'
    for permissive in ('"true"', '"hasRole(\'ADMIN\') or true"', '"permitAll"', 'new Custom()', 'unknownManager'):
        output = evaluate(files(f'''                .requestMatchers("/api/**").access({permissive})
                .anyRequest().authenticated()'''))
        assert users not in facts(output, 'PROTECTED_BY'), permissive
        assert users in gaps(output), permissive
    output = evaluate(files('''                .requestMatchers("/api/**").access("hasRole('ADMIN') and isAuthenticated()")
                .anyRequest().authenticated()'''))
    assert facts(output, 'PROTECTED_BY')[users]['object'] == \
        '''policy-rule:access("hasRole('ADMIN') and isAuthenticated()")'''


def test_only_spring_http_security_chains_are_security_configurations():
    home_made = config(RULES, imports='import com.example.dsl.HttpSecurity;\n')
    output = evaluate(files(None, **{'security/SecurityConfig.java': home_made}))
    assert output.facts == (), 'une API maison au meme nom n est pas Spring Security'
    unknown = config(RULES).replace('return http.csrf', 'return this.http().csrf')
    output = evaluate(files(None, **{'security/SecurityConfig.java': unknown}))
    assert not facts(output, 'PROTECTED_BY')
    assert 'endpoint:GET /health' in gaps(output), \
        'un receveur de type inconnu est peut-etre HttpSecurity : aucune conclusion'


def test_routes_the_endpoint_analysis_could_not_establish_stay_not_interpreted():
    broken = controller('BrokenController', None, '''
    @GetMapping(Unknown.PATH)
    public String hidden() { return ""; }
''')
    output = evaluate(files(**{'web/BrokenController.java': broken}))
    assert 'symbol:java:com.example.web.BrokenController#hidden()' in gaps(output)
    assert output.status == EvaluationStatus.PARTIAL


def test_several_candidate_filter_chains_forbid_a_conclusion_unless_their_scope_separates_them():
    second = '''package com.example.security;

import org.springframework.security.config.annotation.web.builders.*;

@Configuration
public class ApiSecurity {
    @Bean
    SecurityFilterChain api(HttpSecurity http) throws Exception {
        return http.securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth.anyRequest().permitAll())
            .build();
    }
}
'''
    output = evaluate(files(**{'security/ApiSecurity.java': second}))
    assert 'endpoint:GET /api/v1/orgs/{orgCode}/users' in gaps(output), 'deux chaines candidates : ordre non lu'
    assert 'endpoint:GET /health' in facts(output, 'PROTECTED_BY'), 'seule la chaine globale vise /health'
    unread = second.replace('http.securityMatcher("/api/**")', 'http.securityMatcher(Paths.API)')
    output = evaluate(files(**{'security/ApiSecurity.java': unread}))
    assert 'endpoint:GET /health' in gaps(output), 'un perimetre non lu peut viser toute route'


def test_routes_excluded_by_web_ignoring_are_not_concluded():
    ignoring = '''package com.example.security;

@Configuration
public class WebConfig {
    @Bean
    WebSecurityCustomizer customizer() {
        return web -> web.ignoring().requestMatchers("/health");
    }
}
'''
    output = evaluate(files(**{'security/WebConfig.java': ignoring}))
    assert 'endpoint:GET /health' in gaps(output)
    assert 'endpoint:GET /health' not in facts(output, 'PROTECTED_BY')
    assert 'endpoint:GET /api/v1/orgs/{orgCode}/users' in facts(output, 'PROTECTED_BY')


def test_method_security_and_home_made_mechanisms_are_declared_not_interpreted():
    guarded = controller('AdminController', '/api/v1/admin', '''
    @PreAuthorize("hasRole('ADMIN')")
    @DeleteMapping("/{id}")
    public void remove() {}
''')
    output = evaluate(files(**{'web/AdminController.java': guarded}))
    assert 'endpoint:DELETE /api/v1/admin/{id}' in gaps(output)
    assert 'endpoint:DELETE /api/v1/admin/{id}' in facts(output, 'PROTECTED_BY'), 'la regle d URL reste un fait'
    assert 'symbol:java:com.example.security.PolicyManager' in gaps(output)


def test_the_spring_security_5_chain_is_read_up_to_and():
    legacy = f'''package com.example.security;

import org.springframework.security.config.annotation.web.builders.HttpSecurity;

@Configuration
public class LegacyConfig extends WebSecurityConfigurerAdapter {{
    @Override
    protected void configure(HttpSecurity http) throws Exception {{
        http.authorizeRequests()
            .antMatchers("/health").permitAll()
            .anyRequest().hasAuthority("SCOPE_api")
            .and()
            .formLogin();
    }}
}}
'''
    output = evaluate(files(None, **{'security/LegacyConfig.java': legacy}))
    health = facts(output, 'MATCHED_BY')['endpoint:GET /health']
    assert health['derivation']['known_gaps'], 'antMatchers : les variantes d URL non modelisees sont dites'
    users = facts(output, 'PROTECTED_BY')['endpoint:GET /api/v1/orgs/{orgCode}/users']
    assert users['object'] == 'policy-rule:hasAuthority("SCOPE_api")'
    assert users['derivation']['known_gaps'], 'les autorites des utilisateurs sont des donnees'


def test_without_security_configuration_nothing_is_asserted_and_it_is_said():
    sources = {path: text for path, text in files(None).items() if not path.endswith('PolicyManager.java')}
    output = evaluate(sources)
    assert output.facts == ()
    assert output.status == EvaluationStatus.SUCCESS
    assert any('authorizeHttpRequests' in warning for warning in output.warnings)
    assert [item['coverage_type'] for item in output.coverage] == ['ANALYSED']
    empty = evaluate({'README.md': '# rien'})
    assert (empty.facts, empty.status, empty.warnings) == ((), EvaluationStatus.SUCCESS, ())


def test_every_fact_satisfies_the_contract():
    execution = RunEvaluator()(SpringSecurityEvaluator(), snapshot(files()))
    assert execution.status == EvaluationStatus.PARTIAL, execution.error
    assert {fact['status'] for fact in execution.facts} == {'OBSERVED', 'INFERRED'}
    assert all(fact['produced_by']['catalog_id'] == 'spring-security' for fact in execution.facts)
    assert {fact['produced_by']['catalog_version'] for fact in execution.facts} == {'2'}, \
        'filter_chain porte une signature : schema d identite en version 2'


def test_pattern_matching_has_three_outcomes():
    assert rules.match('/api/**', '/api') == rules.ALL
    assert rules.match('/api/*/users', '/api/{org}/users') == rules.ALL
    assert rules.match('/api/v1/**', '/api/orgs/x') == rules.NONE
    assert rules.match('/users/me', '/users/{id}') == rules.SOME
    assert rules.match('/files/*.json', '/files/a.json') == rules.ALL
    assert rules.match('/files/*.json', '/files/{name}') == rules.SOME
    assert rules.match('/files/**', '/files/{*path}') == rules.ALL
    assert rules.match('/files/x', '/files/{*path}') == rules.SOME
    assert not rules.readable_pattern('/api/{id:\\d+}')
    assert not rules.readable_pattern('api/**')


def test_an_application_that_does_not_establish_what_it_loads_forbids_any_route_conclusion():
    def application(name):
        return f'''package com.example.{name};

@SpringBootApplication
public class {name.capitalize()}Application {{
}}
'''
    output = evaluate(files(**{'app/one/OneApplication.java': application('one'),
                               'app/two/TwoApplication.java': application('two')}))
    assert not facts(output, 'MATCHED_BY')
    assert not facts(output, 'PROTECTED_BY')
    assert 'endpoint:GET /health' in gaps(output), 'la chaine d une application ne vaut pas pour l autre'
    assert facts(output, 'AUTHORIZED_BY'), 'les regles lues restent des faits observes'


def test_an_established_application_attaches_its_routes_to_the_chains_it_loads():
    boot = """package com.example;

import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ShopApplication {
}
"""
    imports = SPRING + 'import org.springframework.context.annotation.*;\n'
    sources = files(**{'ShopApplication.java': boot, 'security/SecurityConfig.java': config(RULES, imports)})
    output = evaluate({**sources, 'svc/build.gradle': ''})
    health = facts(output, 'MATCHED_BY')['endpoint:GET /health']
    assert 'SERVED_BY : endpoint:GET /health -> application:svc/src/main/java/com/example/ShopApplication.java' \
           '#ShopApplication' in health['derivation']['premises']
    assert 'endpoint:GET /health' in facts(output, 'PROTECTED_BY')


def test_a_manager_built_by_a_method_of_the_configuration_is_the_one_that_decides():
    extra = """
    AuthorizationManager<RequestAuthorizationContext> policy() { return manager; }
"""
    source = config('                .anyRequest().access(policy())', extra=extra)
    output = evaluate(files(security=None, **{'security/SecurityConfig.java': source}))
    target = 'symbol:java:com.example.security.SecurityConfig#policy()'
    assert facts(output, 'PROTECTED_BY')['endpoint:GET /health']['object'] == target
    assert f'la décision de {target} n’est pas lue' in facts(output, 'PROTECTED_BY')['endpoint:GET /health'][
        'derivation']['known_gaps']
    unknown = config('                .anyRequest().access(elsewhere())')
    assert not facts(evaluate(files(security=None, **{'security/SecurityConfig.java': unknown})), 'PROTECTED_BY'), \
        'une methode absente du type (heritee, statique importee) ne se devine pas'
