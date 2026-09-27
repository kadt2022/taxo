"""TAXO-E1 tranche 2 (ADR 0012) : l'application qui sert chaque route, et les chaines de filtres qu'elle charge.

Une route n'est rattachee a une application, et a ses chaines, que par le classpath et le balayage etablis :
jamais par paquetage, proximite ou nom. Ce qui ne s'etablit pas reste NOT_INTERPRETED.
"""
from app.evaluations.application.run_evaluator import RunEvaluator
from app.evaluations.domain.status import EvaluationStatus
from app.evaluators.spring_boot.evaluator import SpringBootEvaluator
from app.evaluators.spring_security.evaluator import SpringSecurityEvaluator
from test_spring_api import snapshot

SHOP = 'shop-app/src/main/java/com/acme/shop/ShopApplication.java'
ADMIN_APP = 'admin-app/src/main/java/com/acme/adminapp/AdminApplication.java'
SHOP_REF = f'application:{SHOP}#ShopApplication'
ADMIN_REF = f'application:{ADMIN_APP}#AdminApplication'


def application(package, name, arguments='', annotations=''):
    return f'''package {package};

import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Import;

{annotations}@SpringBootApplication{arguments}
public class {name} {{
}}
'''


def controller(package, name, route, annotations=''):
    return f'''package {package};

import org.springframework.context.annotation.Profile;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

{annotations}@RestController
public class {name} {{
    @GetMapping("{route}")
    public String get() {{ return ""; }}
}}
'''


def security(package, name, rule, annotations='@Configuration\n', bean=''):
    return f'''package {package};

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;

{annotations}public class {name} {{
    @Bean
{bean}    SecurityFilterChain chain(HttpSecurity http) throws Exception {{
        return http.authorizeHttpRequests(auth -> auth
                .anyRequest().{rule})
            .build();
    }}
}}
'''


SETTINGS = 'include "shop-app", "admin-app", "web", "security", "admin"\n'


def repository(**changes):
    """Deux applications. La boutique balaie `com.acme` entier, mais le module `admin` n'est sur son classpath
    qu'en test : le piege de D1, un paquetage balaye qui ne dit rien du classpath."""
    files = {
        'settings.gradle': SETTINGS,
        'shop-app/build.gradle': 'dependencies {\n    implementation project(":web")\n'
                                 '    implementation project(":security")\n'
                                 '    testImplementation project(":admin")\n}\n',
        'admin-app/build.gradle': 'dependencies {\n    implementation project(":admin")\n}\n',
        'web/build.gradle': '', 'security/build.gradle': '', 'admin/build.gradle': '',
        SHOP: application('com.acme.shop', 'ShopApplication', '(scanBasePackages = "com.acme")'),
        ADMIN_APP: application('com.acme.adminapp', 'AdminApplication',
                               '(scanBasePackages = {"com.acme.admin", "com.acme.adminapp"})'),
        'web/src/main/java/com/acme/web/OrderController.java': controller('com.acme.web', 'OrderController', '/orders'),
        'admin/src/main/java/com/acme/admin/UserAdminController.java':
            controller('com.acme.admin', 'UserAdminController', '/admin/users'),
        'security/src/main/java/com/acme/security/ShopSecurity.java':
            security('com.acme.security', 'ShopSecurity', 'authenticated()'),
        'admin/src/main/java/com/acme/admin/AdminSecurity.java':
            security('com.acme.admin', 'AdminSecurity', 'hasRole("ADMIN")'),
    }
    files.update(changes)
    return {path: text for path, text in files.items() if text is not None}


def boot(files):
    return SpringBootEvaluator().evaluate(snapshot(files))


def secure(files):
    return SpringSecurityEvaluator().evaluate(snapshot(files))


def served(output):
    return {(fact['subject'], fact['object']) for fact in output.facts if fact['relation'] == 'SERVED_BY'}


def protected(output):
    return {fact['subject']: fact['object'] for fact in output.facts if fact['relation'] == 'PROTECTED_BY'}


def gaps(output):
    return {item['subject'] for item in output.coverage if item['coverage_type'] == 'NOT_INTERPRETED'}


def reasons(output, subject):
    return ' '.join(warning for warning in output.warnings if warning.startswith(subject))


def test_each_application_is_built_from_its_module_and_serves_only_what_its_classpath_and_scan_load():
    output = boot(repository())
    built = {(fact['subject'], fact['object']) for fact in output.facts if fact['relation'] == 'BUILT_FROM'}
    assert built == {(SHOP_REF, 'module:shop-app'), (ADMIN_REF, 'module:admin-app')}
    assert served(output) == {('endpoint:GET /orders', SHOP_REF), ('endpoint:GET /admin/users', ADMIN_REF)}, \
        'com.acme.admin est balaye par la boutique, mais son module n est sur son classpath qu en test'
    assert output.status == EvaluationStatus.SUCCESS
    fact = next(fact for fact in output.facts if fact['relation'] == 'SERVED_BY'
                and fact['subject'] == 'endpoint:GET /orders')
    assert fact['status'] == 'INFERRED'
    assert 'DEPENDS_ON : module:shop-app -> module:web (implementation)' in fact['derivation']['premises']
    assert {proof['path'] for proof in fact['evidence']} == {SHOP, 'web/src/main/java/com/acme/web/OrderController.java'}


def test_a_route_is_protected_only_by_the_chains_its_application_loads():
    output = secure(repository())
    assert protected(output) == {'endpoint:GET /orders': 'policy-rule:authenticated()',
                                 'endpoint:GET /admin/users': 'policy-rule:hasRole("ADMIN")'}
    admin = next(fact for fact in output.facts if fact['relation'] == 'MATCHED_BY'
                 and fact['subject'] == 'endpoint:GET /admin/users')
    assert admin['qualifiers']['filter_chain'] == 'symbol:java:com.acme.admin.AdminSecurity#chain(HttpSecurity)'
    assert f'SERVED_BY : endpoint:GET /admin/users -> {ADMIN_REF}' in admin['derivation']['premises']
    excluded = ' '.join(admin['derivation']['counter_examples_checked'])
    assert 'ShopSecurity' in excluded and 'hors du classpath' in excluded
    assert admin['derivation']['known_gaps'] == [], 'une chaine hors du classpath est ecartee sans reserve'


def test_a_conditional_controller_or_chain_is_never_attributed():
    profiled = controller('com.acme.web', 'OrderController', '/orders', '@Profile("dev")\n')
    output = boot(repository(**{'web/src/main/java/com/acme/web/OrderController.java': profiled}))
    assert ('endpoint:GET /orders', SHOP_REF) not in served(output)
    assert 'endpoint:GET /orders' in gaps(output)
    assert 'condition @Profile' in reasons(output, 'endpoint:GET /orders')
    chain = security('com.acme.security', 'ShopSecurity', 'authenticated()', bean='    @Profile("prod")\n')
    output = secure(repository(**{'security/src/main/java/com/acme/security/ShopSecurity.java': chain}))
    assert 'endpoint:GET /orders' not in protected(output)
    assert 'condition @Profile' in reasons(output, 'endpoint:GET /orders'), 'la condition du bean compte aussi'


def test_a_classpath_that_cannot_be_established_attributes_nothing():
    for build, cause in (('dependencies {\n    implementation project(":web")\n    shadow project(":security")\n}\n',
                          'shadow'),
                         ('dependencies {\n    implementation project(path)\n}\n', 'non lu')):
        output = boot(repository(**{'shop-app/build.gradle': build}))
        assert not {pair for pair in served(output) if pair[1] == SHOP_REF}, cause
        assert SHOP_REF in gaps(output), cause
    shared = 'subprojects {\n    dependencies {\n        implementation project(":security")\n    }\n}\n'
    output = boot(repository(**{'build.gradle': shared}))
    assert not served(output), 'des dependances communes a tous les modules ne sont pas lues module par module'
    assert {SHOP_REF, ADMIN_REF} <= gaps(output)


def test_an_application_outside_a_module_or_without_scan_is_declared():
    output = boot(repository(**{'settings.gradle': None, 'shop-app/build.gradle': None, 'admin-app/build.gradle': None,
                                'web/build.gradle': None, 'security/build.gradle': None, 'admin/build.gradle': None}))
    assert not served(output), 'sans descripteur de build, aucun classpath n est etabli'
    assert {SHOP_REF, ADMIN_REF} <= gaps(output)
    computed = application('com.acme.shop', 'ShopApplication', '(scanBasePackages = Packages.ROOT)')
    output = boot(repository(**{SHOP: computed}))
    assert SHOP_REF in gaps(output) and 'endpoint:GET /orders' in gaps(output)


def test_imports_extend_what_is_loaded_and_extra_scans_or_auto_configurations_stay_unknown():
    narrow = application('com.acme.shop', 'ShopApplication', '(scanBasePackages = "com.acme.shop")',
                         '@Import(com.acme.security.ShopSecurity.class)\n')
    output = secure(repository(**{SHOP: narrow}))
    assert 'endpoint:GET /orders' in gaps(output), 'le controleur hors du balayage n est pas servi'
    assert 'aucune application établie' in reasons(output, 'endpoint:GET /orders')
    loads = boot(repository(**{SHOP: narrow, 'web/src/main/java/com/acme/web/OrderController.java':
                               controller('com.acme.shop', 'OrderController', '/orders')}))
    assert ('endpoint:GET /orders', SHOP_REF) in served(loads)
    scanning = security('com.acme.security', 'ShopSecurity', 'authenticated()',
                        '@Configuration\n@ComponentScan("com.acme.web")\n')
    output = boot(repository(**{SHOP: narrow,
                                'security/src/main/java/com/acme/security/ShopSecurity.java': scanning}))
    assert 'endpoint:GET /orders' in gaps(output), 'un balayage supplementaire rend l absence inconnue'
    auto = {'security/src/main/resources/META-INF/spring/'
            'org.springframework.boot.autoconfigure.AutoConfiguration.imports': 'com.acme.security.ShopSecurity\n'}
    output = secure(repository(**auto))
    assert 'endpoint:GET /orders' not in protected(output)
    assert 'auto-configuration' in reasons(output, 'endpoint:GET /orders')


def test_a_route_served_by_two_applications_needs_the_same_chains():
    both = 'dependencies {\n    implementation project(":admin")\n    implementation project(":security")\n}\n'
    output = secure(repository(**{'admin-app/build.gradle': both,
                                  'shop-app/build.gradle': 'dependencies {\n    implementation project(":web")\n'
                                                           '    implementation project(":security")\n'
                                                           '    implementation project(":admin")\n}\n'}))
    assert 'endpoint:GET /admin/users' not in protected(output)
    assert 'chaînes différentes' in reasons(output, 'endpoint:GET /admin/users')
    same = 'dependencies {\n    implementation project(":web")\n    implementation project(":security")\n}\n'
    scan = application('com.acme.adminapp', 'AdminApplication', '(scanBasePackages = "com.acme")')
    shared = secure(repository(**{'admin-app/build.gradle': same, ADMIN_APP: scan}))
    orders = next(fact for fact in shared.facts if fact['relation'] == 'MATCHED_BY'
                  and fact['subject'] == 'endpoint:GET /orders')
    assert {f'SERVED_BY : endpoint:GET /orders -> {SHOP_REF}',
            f'SERVED_BY : endpoint:GET /orders -> {ADMIN_REF}'} <= set(orders['derivation']['premises']), \
        'deux applications qui chargent les memes chaines : la conclusion vaut pour les deux'


def test_every_fact_satisfies_the_contract():
    for evaluator in (SpringBootEvaluator(), SpringSecurityEvaluator()):
        execution = RunEvaluator()(evaluator, snapshot(repository()))
        assert execution.status == EvaluationStatus.SUCCESS
    execution = RunEvaluator()(SpringBootEvaluator(), snapshot(repository()))
    assert {fact['relation'] for fact in execution.facts} == {'BUILT_FROM', 'SERVED_BY'}
