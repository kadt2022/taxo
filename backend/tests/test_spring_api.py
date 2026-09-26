"""TAXO-04 : les endpoints Spring MVC en faits, avec leurs preuves ; ce qui n'est pas resolu est declare."""
import pytest
from fastapi.testclient import TestClient

from app.bootstrap.database import Base
from app.evaluations.application.run_evaluator import RunEvaluator
from app.evaluations.domain.status import EvaluationStatus
from app.evaluators.java import syntax
from app.evaluators.spring_api.evaluator import SpringApiEvaluator
from app.facts import content_hash
from app.main import create_app
from app.snapshots.domain.mode import COMMIT
from app.snapshots.domain.snapshot import Snapshot, SnapshotFile

ROOT = 'service/src/main/java/com/example'

PATHS = f'''package com.example.api;

public final class ApiPaths {{
    public static final String BASE = "/api/v1";
    public static final String ORGS = BASE + "/orgs/{{orgCode}}";
    private ApiPaths() {{}}
}}
'''

CONTROLLER = f'''package com.example.api.users;

import com.example.api.ApiPaths;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping(ApiPaths.ORGS + "/users")
public class UserController {{

    private static final String ONE = "/{{userId}}";

    @GetMapping
    public Page list() {{ return null; }}

    @GetMapping(ONE)
    public User get() {{ return null; }}

    @PostMapping(value = {{"", "/import"}})
    public User create() {{ return null; }}

    @RequestMapping(path = ONE, method = {{RequestMethod.PUT, RequestMethod.PATCH}})
    public User update() {{ return null; }}

    @RequestMapping("/ping")
    public String ping() {{ return "ok"; }}

    @DeleteMapping(Unknown.PATH)
    public void remove() {{}}

    @GetMapping("${{users.export}}")
    public void export() {{}}
}}
'''


class Content:
    def __init__(self, files):
        self.files = files

    def read_many(self, paths):
        for path in paths:
            yield path, self.files[path]


def snapshot(files):
    encoded = {path: text.encode('utf-8') if isinstance(text, str) else text for path, text in files.items()}
    return Snapshot('depot', 'a' * 40, COMMIT, tuple(SnapshotFile(path, len(data)) for path, data in encoded.items()),
                    content=Content(encoded))


def evaluate(files):
    return SpringApiEvaluator().evaluate(snapshot(files))


def handlers(output):
    return {(fact['subject'], fact['object']) for fact in output.facts}


def gaps(output):
    return {fact['subject'] for fact in output.coverage if fact['coverage_type'] == 'NOT_INTERPRETED'}


USERS = 'symbol:java:com.example.api.users.UserController'


def test_each_mapping_becomes_an_endpoint_handled_by_its_method():
    output = evaluate({f'{ROOT}/api/ApiPaths.java': PATHS, f'{ROOT}/api/users/UserController.java': CONTROLLER})
    base = '/api/v1/orgs/{orgCode}/users'
    assert handlers(output) == {
        (f'endpoint:GET {base}', f'{USERS}#list'),
        (f'endpoint:GET {base}/{{userId}}', f'{USERS}#get'),
        (f'endpoint:POST {base}', f'{USERS}#create'),
        (f'endpoint:POST {base}/import', f'{USERS}#create'),
        (f'endpoint:PUT {base}/{{userId}}', f'{USERS}#update'),
        (f'endpoint:PATCH {base}/{{userId}}', f'{USERS}#update'),
        (f'endpoint:ANY {base}/ping', f'{USERS}#ping'),
    }, 'constante d un autre fichier, constante du type, concatenation, tableau, verbes, mapping sans chemin'
    assert gaps(output) == {f'{USERS}#remove', f'{USERS}#export'}, 'jamais deviner : constante inconnue, propriete'
    assert output.status is EvaluationStatus.PARTIAL
    assert any('Unknown.PATH' in warning for warning in output.warnings)
    assert any('${users.export}' in warning for warning in output.warnings)


def test_the_evidence_points_at_both_mappings_to_the_line():
    source = CONTROLLER.encode('utf-8')
    output = evaluate({f'{ROOT}/api/ApiPaths.java': PATHS, f'{ROOT}/api/users/UserController.java': source})
    fact = next(item for item in output.facts if item['object'] == f'{USERS}#get')
    lines = CONTROLLER.split('\n')
    assert [item['line_start'] for item in fact['evidence']] == [
        lines.index('@RequestMapping(ApiPaths.ORGS + "/users")') + 1, lines.index('    @GetMapping(ONE)') + 1]
    for item in fact['evidence']:
        assert item['path'] == f'{ROOT}/api/users/UserController.java' and item['symbol'] == f'{USERS}#get'
        assert item['method'] == 'java.spring.request-mapping'
        assert item['content_hash'] == content_hash(source, item['line_start'], item['line_end'])


def test_the_facts_satisfy_the_contract():
    evaluator = SpringApiEvaluator()
    execution = RunEvaluator()(evaluator, snapshot({f'{ROOT}/api/ApiPaths.java': PATHS,
                                                    f'{ROOT}/api/users/UserController.java': CONTROLLER}))
    assert execution.status is EvaluationStatus.PARTIAL and len(execution.facts) == 7


def test_static_imports_class_level_verbs_and_nested_controllers():
    source = '''package com.example.web;
import org.springframework.web.bind.annotation.*;

import static com.example.web.Routes.HEALTH;
import static org.springframework.web.bind.annotation.RequestMethod.GET;
import org.springframework.stereotype.Controller;

@Controller
@RequestMapping(value = "/ops/", method = RequestMethod.GET)
class OpsController {
    @RequestMapping(HEALTH) String health() { return ""; }
    @RequestMapping(value = "/stop", method = GET) String stop() { return ""; }

    @RestController
    static class Inner {
        @DeleteMapping("cache/") void flush() {}
    }
}
'''
    routes = 'package com.example.web;\ninterface Routes { String HEALTH = "/health"; }\n'
    output = evaluate({'src/main/java/Ops.java': source, 'src/main/java/Routes.java': routes})
    assert handlers(output) == {
        ('endpoint:GET /ops/health', 'symbol:java:com.example.web.OpsController#health'),
        ('endpoint:GET /ops/stop', 'symbol:java:com.example.web.OpsController#stop'),
        ('endpoint:DELETE /cache/', 'symbol:java:com.example.web.OpsController.Inner#flush'),
    }, 'constante d interface, verbe du type, import statique, type imbrique, / final garde'
    assert output.status is EvaluationStatus.SUCCESS and gaps(output) == set()


def test_mappings_outside_a_controller_are_declared_not_guessed():
    api = '''package com.example;
import org.springframework.web.bind.annotation.*;
public interface UsersApi {
    @GetMapping("/users") List<User> list();
}
'''
    base = '''package com.example;
import org.springframework.web.bind.annotation.*;
@RequestMapping("/base")
public abstract class BaseController {
    @GetMapping("/info") public String info() { return ""; }
}
'''
    plain = 'package com.example;\npublic class Helper { public void mapping() {} }\n'
    output = evaluate({'src/main/java/UsersApi.java': api, 'src/main/java/BaseController.java': base,
                       'src/main/java/Helper.java': plain})
    assert output.facts == ()
    assert gaps(output) == {'symbol:java:com.example.UsersApi', 'symbol:java:com.example.BaseController'}


def test_routes_inherited_from_a_generated_or_mapped_type_are_declared():
    generated = '''package com.example.web;
import org.springframework.web.bind.annotation.*;
import com.example.generated.PetsApi;
@RestController
@RequestMapping("api")
class PetController implements PetsApi {
    @Override public Pet getPet(Integer id) { return null; }
    @GetMapping("/pets/count") public int count() { return 0; }
}
'''
    api = 'package com.example.web;\nimport org.springframework.web.bind.annotation.*;\npublic interface OwnersApi { @GetMapping("/owners") List<Owner> list(); }\n'
    owner = '''package com.example.web;
import org.springframework.web.bind.annotation.*;
@RestController
class OwnerController implements OwnersApi, Serializable {
    public List<Owner> list() { return null; }
}
'''
    output = evaluate({'src/main/java/PetController.java': generated, 'src/main/java/OwnersApi.java': api,
                       'src/main/java/OwnerController.java': owner})
    assert handlers(output) == {('endpoint:GET /api/pets/count', 'symbol:java:com.example.web.PetController#count')}, \
        'ses propres mappings restent des faits'
    assert gaps(output) == {'symbol:java:com.example.web.PetController', 'symbol:java:com.example.web.OwnersApi',
                            'symbol:java:com.example.web.OwnerController'}
    assert any('absent des sources : PetsApi' in warning for warning in output.warnings)
    assert any('absent des sources : Serializable ; porteur de mappings : OwnersApi' in warning
               for warning in output.warnings)


def test_an_unresolved_controller_mapping_declares_the_whole_controller():
    source = '''package com.example;
import org.springframework.web.bind.annotation.*;
@RestController
@RequestMapping(Somewhere.ROOT)
class Orders { @GetMapping("/orders") void list() {} }
'''
    output = evaluate({'src/main/java/Orders.java': source})
    assert output.facts == () and gaps(output) == {'symbol:java:com.example.Orders'}


def test_test_sources_and_build_outputs_are_outside_the_scope():
    controller = 'package t;\nimport org.springframework.web.bind.annotation.*;\n@RestController\nclass T { @GetMapping("/t") void t() {} }\n'
    output = evaluate({'app/src/test/java/T.java': controller, 'app/build/generated/T.java': controller})
    assert output.facts == ()
    analysed = next(item for item in output.coverage if item['coverage_type'] == 'ANALYSED')
    assert analysed['scope'] == {'include': ['repository:depot'],
                                 'exclude': ['directory:app/build', 'directory:app/src/test']}


def test_a_broken_or_unreadable_file_is_declared():
    broken = 'package b;\nimport org.springframework.web.bind.annotation.*;\n@RestController\nclass B { @GetMapping("/b") void b() {} void oops( }\n'
    output = evaluate({'src/main/java/B.java': broken, 'src/main/java/Latin.java': b'\xe9\xe9 class L {}'})
    assert 'file:src/main/java/B.java' in gaps(output)
    unreadable = {item['subject'] for item in output.coverage if item['coverage_type'] == 'READ_ERROR'}
    assert unreadable == {'file:src/main/java/Latin.java'}
    assert output.status is EvaluationStatus.PARTIAL


def test_a_repository_without_java_is_analysed_and_has_no_endpoint():
    output = evaluate({'main.py': 'print(1)\n'})
    assert output.facts == () and output.status is EvaluationStatus.SUCCESS
    assert [item['coverage_type'] for item in output.coverage] == ['ANALYSED']


@pytest.mark.parametrize('written, expected', [
    ('"/a" + "/b"', '/a/b'), ('("/a")', '/a'), ('"\\"q\\""', '"q"'), ('"\\u0041"', None), ('prefix()', None),
    ('Other.X', None), ('LOCAL', '/local'),
])
def test_the_java_analyzer_resolves_only_what_is_written(written, expected):
    source = f'class C {{ static final String LOCAL = "/local"; @M({written}) void m() {{}} }}'.encode('utf-8')
    value = syntax.parse('C.java', source).types[0].methods[0].annotations[0].arguments['value'][0]
    assert value.text == expected and value.written == written


def test_the_impact_of_a_commit_names_the_endpoints_it_introduces_moves_and_removes(make_repo, git, tmp_path):
    first = 'package p;\nimport org.springframework.web.bind.annotation.*;\n@RestController\nclass A {\n    @GetMapping("/a") void a() {}\n    @GetMapping("/gone") void g() {}\n}\n'
    repo = make_repo({'src/main/java/A.java': first}, 'endpoints')
    second = 'package p;\nimport org.springframework.web.bind.annotation.*;\n@RestController\nclass A {\n    @GetMapping("/a") void renamed() {}\n    @PostMapping("/new") void n() {}\n}\n'
    (repo / 'src/main/java/A.java').write_text(second)
    git(repo, 'add', '-A')
    git(repo, 'commit', '-qm', 'endpoints')
    sha = git(repo, 'rev-parse', 'HEAD')
    app = create_app(f'sqlite:///{tmp_path / "endpoints.db"}', [repo])
    Base.metadata.create_all(app.state.engine)
    with TestClient(app) as client:
        project = client.post('/api/projects', json={'name': 'Endpoints', 'path': str(repo)}).json()
        impact = client.get(f'/api/projects/{project["id"]}/history/commits/{sha}/impact').json()
    spring = next(item for item in impact['evaluations'] if item['evaluator_id'] == 'taxo.spring-api')
    changes = {(item['change'], item['subject'], item['before'], item['after']) for item in spring['changes']}
    assert changes == {
        ('MODIFIED', 'endpoint:GET /a', 'symbol:java:p.A#a', 'symbol:java:p.A#renamed'),
        ('REMOVED', 'endpoint:GET /gone', 'symbol:java:p.A#g', None),
        ('INTRODUCED', 'endpoint:POST /new', None, 'symbol:java:p.A#n'),
    }


def test_a_prefix_inherited_from_a_base_type_is_never_dropped():
    base = '''package com.example;
import org.springframework.web.bind.annotation.*;
@RequestMapping("/api")
abstract class Base {}
'''
    child = '''package com.example;
import org.springframework.web.bind.annotation.*;
@RestController
class Child extends Base { @GetMapping("/x") String x() { return ""; } }
'''
    own = '''package com.example;
import org.springframework.web.bind.annotation.*;
@RestController
@RequestMapping("/own")
class Own extends Base { @GetMapping("/y") String y() { return ""; } }
'''
    output = evaluate({'src/main/java/Base.java': base, 'src/main/java/Child.java': child,
                       'src/main/java/Own.java': own})
    assert handlers(output) == {('endpoint:GET /own/y', 'symbol:java:com.example.Own#y')}, \
        'sans mapping propre, le prefixe herite est inconnu : pas de /x ; un mapping propre prime sur l heritage'
    assert {'symbol:java:com.example.Child', 'symbol:java:com.example.Own', 'symbol:java:com.example.Base'} == gaps(output)


def test_only_spring_annotations_count():
    other = '''package com.acme;
import com.acme.web.GetMapping;
import com.acme.web.RestController;
@RestController
class NotSpring { @GetMapping("/no") void no() {} }
'''
    local = '''package com.acme.web;
import org.springframework.web.bind.annotation.*;
@RestController
class Shadowed { @GetMapping("/shadow") void no() {} }
'''
    homemade = 'package com.acme.web;\npublic @interface GetMapping { String value(); }\n'
    qualified = '''package com.acme.api;
@org.springframework.web.bind.annotation.RestController
class Qualified { @org.springframework.web.bind.annotation.GetMapping("/yes") void yes() {} }
'''
    output = evaluate({'src/main/java/NotSpring.java': other, 'src/main/java/Shadowed.java': local,
                       'src/main/java/GetMapping.java': homemade, 'src/main/java/Qualified.java': qualified})
    assert handlers(output) == {('endpoint:GET /yes', 'symbol:java:com.acme.api.Qualified#yes')}, \
        'un import explicite ou un type du meme paquetage masque Spring ; un nom qualifie de Spring compte'
    assert gaps(output) == set() and output.status is EvaluationStatus.SUCCESS


def test_constants_citing_constants_of_other_files_are_resolved():
    routes = 'package com.example.api;\npublic final class Routes { public static final String USERS = Api.ROOT + "/users"; }\n'
    api = 'package com.example.api;\npublic final class Api { public static final String ROOT = Base.PREFIX + "/v1"; }\n'
    prefix = 'package com.example.api;\ninterface Base { String PREFIX = "/api"; }\n'
    controller = '''package com.example.api;
import org.springframework.web.bind.annotation.*;
@RestController
@RequestMapping(Routes.USERS)
class Users { @GetMapping void list() {} }
'''
    output = evaluate({'src/main/java/Users.java': controller, 'src/main/java/Routes.java': routes,
                       'src/main/java/Api.java': api, 'src/main/java/Base.java': prefix})
    assert handlers(output) == {('endpoint:GET /api/v1/users', 'symbol:java:com.example.api.Users#list')}
    assert output.status is EvaluationStatus.SUCCESS
