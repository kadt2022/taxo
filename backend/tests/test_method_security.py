"""TAXO-MINIA-SEC-01, E2 : la securite de methode et CSRF dans la Maille, sans jamais conclure a tort.

La verite est etablie a la main sur un petit projet Spring synthetique : `GET /api/items` exige une
authentification par la regle `/api/**` (ligne 20 de SecurityConfig), et `@PreAuthorize` restreint en plus la
methode aux roles ADMIN et EDITOR (ligne 14 d'ItemController). `@EnableMethodSecurity` (ligne 13) l'active ;
CSRF est desactive (ligne 18).
"""
from app.evaluations.application.run_evaluator import RunEvaluator
from app.evaluations.domain.status import EvaluationStatus
from app.evaluators.spring_security.evaluator import SpringSecurityEvaluator
from test_spring_api import snapshot

ENDPOINT = 'endpoint:GET /api/items'
HANDLER = 'symbol:java:com.example.shop.web.ItemController#items()'
CONFIG = 'symbol:java:com.example.shop.config.SecurityConfig'
CHAIN = f'{CONFIG}#securityFilterChain(HttpSecurity)'
ROLES = "hasAnyRole('ADMIN','EDITOR')"
ENABLE = 'org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity'
GLOBAL = 'org.springframework.security.config.annotation.method.configuration.EnableGlobalMethodSecurity'
PRE_AUTHORIZE = 'org.springframework.security.access.prepost.PreAuthorize'
METHOD_RULE = 'spring-security.method-authorization-applies'

BUILD = """plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.6'
}
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
"""

APPLICATION = """package com.example.shop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ShopApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
"""


ENABLING = f'import {ENABLE};'


def security(enabling=ENABLING, annotation='@EnableMethodSecurity', csrf='.csrf(csrf -> csrf.disable())',
             rule='authenticated()', package='com.example.shop.config'):
    return f"""package {package};

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
{enabling}
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

/**
 * Regles d'URL et securite de methode.
 */
@Configuration
{annotation}
public class SecurityConfig {{
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {{
        return http
                {csrf}
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/api/**").{rule}
                        .anyRequest().permitAll())
                .build();
    }}
}}
"""


def controller(guard=f'@PreAuthorize("{ROLES}")', imports=f'import {PRE_AUTHORIZE};', type_guard=''):
    return f"""package com.example.shop.web;

{imports}
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
@RequestMapping("/api/items"){type_guard}
public class ItemController {{
    @GetMapping
    {guard}
    public List<String> items() {{
        return List.of();
    }}
}}
"""


def shop(config=None, web=None, **extra):
    files = {'build.gradle': BUILD,
             'src/main/java/com/example/shop/ShopApplication.java': APPLICATION,
             'src/main/java/com/example/shop/config/SecurityConfig.java': config or security(),
             'src/main/java/com/example/shop/web/ItemController.java': web or controller()}
    files.update(extra)
    return files


def evaluate(files):
    return SpringSecurityEvaluator().evaluate(snapshot(files))


def found(output, relation, subject=None):
    return [fact for fact in output.facts
            if fact['relation'] == relation and (subject is None or fact['subject'] == subject)]


def reasons(output, subject):
    return [item['reason'] for item in output.coverage
            if item['coverage_type'] == 'NOT_INTERPRETED' and item['subject'] == subject]


def method_protection(output):
    return [fact for fact in found(output, 'PROTECTED_BY', ENDPOINT) if fact['qualifiers'].get('annotation')]


def test_pre_authorize_protects_the_endpoint_its_method_handles_beside_the_url_rule():
    output = evaluate(shop())
    assert output.status == EvaluationStatus.SUCCESS and output.coverage[1:] == ()
    targets = {fact['object'] for fact in found(output, 'PROTECTED_BY', ENDPOINT)}
    assert targets == {'policy-rule:authenticated()', f'policy-rule:{ROLES}'}, 'les deux protections sont vraies'
    [protection] = method_protection(output)
    assert protection['status'] == 'INFERRED'
    derivation = protection['derivation']
    assert derivation['rule'] == METHOD_RULE
    assert derivation['premises'] == [f'HANDLED_BY : {ENDPOINT} -> {HANDLER}', f'AUTHORIZED_BY : {HANDLER} -> {ROLES}',
                                      f'ANNOTATED_WITH : {CONFIG} -> annotation:{ENABLE}']
    assert derivation['known_gaps'], 'les rôles des utilisateurs sont des données'
    lines = {(item['path'].rsplit('/', 1)[-1], item['line_start']) for item in protection['evidence']}
    assert lines == {('ItemController.java', 14), ('SecurityConfig.java', 13)}


def test_the_written_facts_are_observed_at_their_line():
    output = evaluate(shop())
    [guard] = found(output, 'AUTHORIZED_BY', HANDLER)
    assert (guard['status'], guard['object'], guard['qualifiers']) == ('OBSERVED', ROLES, {'annotation': 'PreAuthorize'})
    assert [item['line_start'] for item in guard['evidence']] == [14], 'la garde n’a que sa propre ligne pour preuve'
    [enabling] = found(output, 'ANNOTATED_WITH')
    assert (enabling['subject'], enabling['object']) == (CONFIG, f'annotation:{ENABLE}')
    assert enabling['evidence'][0]['line_start'] == 13
    [csrf] = found(output, 'CONFIGURES')
    assert (csrf['subject'], csrf['object'], csrf['status']) == (CHAIN, 'policy-rule:csrf.disable()', 'OBSERVED')
    assert csrf['evidence'][0]['line_start'] == 18


def test_method_security_protects_even_a_route_the_url_rules_permit():
    output = evaluate(shop(security(rule='permitAll()')))
    assert [fact['object'] for fact in found(output, 'PROTECTED_BY', ENDPOINT)] == [f'policy-rule:{ROLES}']


def test_without_enabling_the_guard_is_observed_but_protects_nothing():
    output = evaluate(shop(security(enabling='', annotation='')))
    assert found(output, 'AUTHORIZED_BY', HANDLER), 'l’annotation reste écrite'
    assert method_protection(output) == []
    assert any('activation non établie' in reason for reason in reasons(output, ENDPOINT))
    assert output.status == EvaluationStatus.PARTIAL


def test_global_method_security_enables_pre_authorize_only_when_written():
    imports = f'import {GLOBAL};'
    off = evaluate(shop(security(imports, '@EnableGlobalMethodSecurity(securedEnabled = true)')))
    assert method_protection(off) == [] and reasons(off, ENDPOINT)
    on = evaluate(shop(security(imports, '@EnableGlobalMethodSecurity(prePostEnabled = true)')))
    assert len(method_protection(on)) == 1
    [enabling] = found(on, 'ANNOTATED_WITH')
    assert enabling['qualifiers'] == {'prePostEnabled': 'true'}


def test_an_enabling_attribute_that_is_not_a_literal_is_declared_not_interpreted():
    output = evaluate(shop(security(annotation='@EnableMethodSecurity(prePostEnabled = Flags.ON)')))
    assert method_protection(output) == []
    assert any('prePostEnabled = Flags.ON' in reason for reason in reasons(output, CONFIG))


def test_an_expression_that_may_permit_everything_is_observed_never_concluded():
    output = evaluate(shop(web=controller('@PreAuthorize("@guard.check(authentication) or permitAll()")')))
    [guard] = found(output, 'AUTHORIZED_BY', HANDLER)
    assert guard['object'] == '@guard.check(authentication) or permitAll()'
    assert method_protection(output) == []
    assert any('expression non évaluée' in reason for reason in reasons(output, ENDPOINT))


def test_a_type_guard_applies_unless_the_method_has_its_own():
    typed = controller(guard='', type_guard='\n@PreAuthorize("hasRole(\'ADMIN\')")')
    output = evaluate(shop(web=typed))
    assert found(output, 'AUTHORIZED_BY', 'symbol:java:com.example.shop.web.ItemController'), 'le type porte la garde'
    assert [fact['object'] for fact in method_protection(output)] == ["policy-rule:hasRole('ADMIN')"]
    both = evaluate(shop(web=controller(type_guard='\n@PreAuthorize("hasRole(\'ADMIN\')")')))
    assert [fact['object'] for fact in method_protection(both)] == [f'policy-rule:{ROLES}'], 'la méthode l’emporte'


def test_a_homonym_of_pre_authorize_is_never_taken_for_spring():
    output = evaluate(shop(web=controller(imports='import com.example.shop.web.security.PreAuthorize;')))
    assert found(output, 'AUTHORIZED_BY', HANDLER) == [] and method_protection(output) == []
    assert any('non résolue vers Spring' in reason for reason in reasons(output, ENDPOINT))


def test_a_same_package_annotation_wins_over_a_wildcard_import_of_spring():
    local = 'package com.example.shop.web;\n\npublic @interface PreAuthorize {\n    String value();\n}\n'
    output = evaluate(shop(web=controller(imports='import org.springframework.security.access.prepost.*;'),
                           **{'src/main/java/com/example/shop/web/PreAuthorize.java': local}))
    assert found(output, 'AUTHORIZED_BY', HANDLER) == [] and method_protection(output) == []
    alone = evaluate(shop(web=controller(imports='import org.springframework.security.access.prepost.*;')))
    assert len(method_protection(alone)) == 1, 'sans homonyme, l’import du paquetage désigne Spring'


def test_other_method_security_annotations_stay_not_interpreted():
    guard = f'@PreAuthorize("{ROLES}")\n    @Secured("ROLE_ADMIN")'
    imports = f'import {PRE_AUTHORIZE};\nimport org.springframework.security.access.annotation.Secured;'
    output = evaluate(shop(web=controller(guard, imports)))
    assert len(method_protection(output)) == 1
    assert reasons(output, ENDPOINT) == ['sécurité de méthode non interprétée (@Secured)']


def test_an_enabling_type_the_application_does_not_load_protects_nothing():
    outside = security(package='com.other.config')
    output = evaluate(shop(security(enabling='', annotation=''),
                           **{'src/main/java/com/other/config/SecurityConfig.java': outside}))
    assert method_protection(output) == []
    assert any('activation par application:' in reason for reason in reasons(output, ENDPOINT))


def test_a_method_a_spring_proxy_cannot_intercept_is_never_protected():
    for modifier in ('final', 'static'):
        sealed = controller().replace('public List<String> items()', f'public {modifier} List<String> items()')
        output = evaluate(shop(web=sealed))
        assert found(output, 'AUTHORIZED_BY', HANDLER), 'l’annotation reste écrite'
        assert method_protection(output) == []
        assert any(f'méthode {modifier}' in reason for reason in reasons(output, ENDPOINT))


def test_without_a_spring_boot_application_the_enabling_is_never_assumed_to_apply():
    files = shop()
    del files['src/main/java/com/example/shop/ShopApplication.java']
    output = evaluate(files)
    assert found(output, 'ANNOTATED_WITH'), 'l’activation reste écrite'
    assert method_protection(output) == []
    assert any('aucune application Spring Boot lue' in reason for reason in reasons(output, ENDPOINT))


def test_csrf_is_read_only_when_it_is_disabled():
    configurer = 'import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;'
    for written, enabling in (('.csrf().disable().and()', ENABLING),
                              ('.csrf(AbstractHttpConfigurer::disable)', f'{ENABLING}\n{configurer}')):
        [csrf] = found(evaluate(shop(security(enabling, csrf=written))), 'CONFIGURES')
        assert csrf['object'] == 'policy-rule:csrf.disable()'
    other = evaluate(shop(security(csrf='.csrf(Customizer::disable)')))
    assert found(other, 'CONFIGURES') == [], 'une méthode disable d’un autre type peut ne rien désactiver'
    assert reasons(other, CHAIN) == ['configuration CSRF non interprétée (ligne 18)']
    customized = evaluate(shop(security(csrf='.csrf(csrf -> csrf.ignoringRequestMatchers("/hooks/**"))')))
    assert found(customized, 'CONFIGURES') == []
    assert reasons(customized, CHAIN) == ['configuration CSRF non interprétée (ligne 18)']
    assert found(evaluate(shop(security(csrf=''))), 'CONFIGURES') == [], 'CSRF par défaut : rien d’écrit'


def test_a_guard_through_a_meta_annotation_or_a_supertype_is_declared_not_read():
    meta = '''package com.example.shop.web;

import org.springframework.security.access.prepost.PreAuthorize;

@PreAuthorize("hasRole('ADMIN')")
public @interface IsAdmin {
}
'''
    output = evaluate(shop(web=controller('@IsAdmin', imports=''),
                           **{'src/main/java/com/example/shop/web/IsAdmin.java': meta}))
    assert method_protection(output) == []
    assert reasons(output, ENDPOINT) == ['sécurité de méthode non interprétée (méta-annotation @IsAdmin)']
    api = '''package com.example.shop.web;

import org.springframework.security.access.prepost.PreAuthorize;

public interface ItemApi {
    @PreAuthorize("hasRole('ADMIN')")
    java.util.List<String> items();
}
'''
    inherited = controller('', imports='').replace('public class ItemController {',
                                                   'public class ItemController implements ItemApi {')
    output = evaluate(shop(web=inherited, **{'src/main/java/com/example/shop/web/ItemApi.java': api}))
    assert method_protection(output) == []
    assert reasons(output, ENDPOINT) == ['sécurité de méthode non interprétée (héritée de ItemApi)']


def test_every_method_security_fact_satisfies_the_contract():
    execution = RunEvaluator()(SpringSecurityEvaluator(), snapshot(shop()))
    assert execution.status == EvaluationStatus.SUCCESS
    relations = {fact['relation'] for fact in execution.facts if fact['kind'] == 'ASSERTION'}
    assert {'ANNOTATED_WITH', 'AUTHORIZED_BY', 'CONFIGURES', 'PROTECTED_BY'} <= relations
