"""TAXO-E1 (ARCHITECTURE § 7.5) : modules, dependances entre modules et unites deployables, lus sans rien executer."""
from fastapi.testclient import TestClient

from app.bootstrap.database import Base
from app.evaluations.application.run_evaluator import RunEvaluator
from app.evaluations.domain.status import EvaluationStatus
from app.evaluators.structure.evaluator import StructureEvaluator
from app.main import create_app
from test_spring_api import snapshot


def evaluate(files):
    return StructureEvaluator().evaluate(snapshot(files))


def modules(output):
    return {fact['object'].removeprefix('module:'): fact['qualifiers']['build_systems']
            for fact in output.facts if fact['relation'] == 'CONTAINS'}


def dependencies(output):
    return {(fact['subject'].removeprefix('module:'), fact['object'].removeprefix('module:'),
             fact['qualifiers']['configuration']) for fact in output.facts if fact['relation'] == 'DEPENDS_ON'}


def applications(output):
    return {fact['subject']: fact['object'] for fact in output.facts if fact['relation'] == 'BUILT_FROM'}


def gaps(output):
    return {item['subject'] for item in output.coverage if item['coverage_type'] == 'NOT_INTERPRETED'}


SETTINGS = '''rootProject.name = 'demo'
include(
        "core",
        "web"   // commentaire
)
include ':tools:cli'
// include 'commented'
'''
WEB = '''plugins { id 'java' }
dependencies {
    implementation project(':core')
    testImplementation(project(path: ':tools:cli'))
}
'''


def test_gradle_modules_and_project_dependencies_with_their_configuration():
    output = evaluate({'settings.gradle': SETTINGS, 'build.gradle': 'allprojects {}\n',
                       'web/build.gradle': WEB, 'core/build.gradle': '', 'tools/cli/build.gradle': ''})
    assert modules(output) == {'core': ['gradle'], 'web': ['gradle'], 'tools/cli': ['gradle']}
    assert dependencies(output) == {('web', 'core', 'implementation'), ('web', 'tools/cli', 'testImplementation')}
    assert output.status == EvaluationStatus.SUCCESS
    evidence = next(fact for fact in output.facts if fact['relation'] == 'DEPENDS_ON'
                    and fact['object'] == 'module:core')['evidence'][0]
    assert (evidence['path'], evidence['line_start']) == ('web/build.gradle', 3)


def test_kotlin_dsl_is_read_the_same_way():
    output = evaluate({'settings.gradle.kts': 'include(":a", ":b")\n',
                       'b/build.gradle.kts': 'dependencies { api(project(":a")) }\n'})
    assert modules(output) == {'a': ['gradle'], 'b': ['gradle']}
    assert dependencies(output) == {('b', 'a', 'api')}


def test_a_single_gradle_project_is_a_module_at_the_root():
    output = evaluate({'build.gradle': 'plugins { id "java" }\n'})
    assert modules(output) == {'.': ['gradle']}


def test_a_single_gradle_project_with_settings_is_still_the_root_module():
    output = evaluate({'settings.gradle': "rootProject.name = 'demo'\n",
                       'build.gradle': 'plugins { id "java" }\n'})
    assert modules(output) == {'.': ['gradle']}


def test_a_root_build_whose_settings_may_declare_projects_is_never_guessed_as_a_module():
    build = {'build.gradle': 'plugins { id "java" }\n'}
    computed = evaluate({'settings.gradle': 'def names = ["a"]\ninclude names\n', **build})
    assert modules(computed) == {}, 'une inclusion calculee ne fait pas de la racine un projet seul'
    moved = evaluate({'settings.gradle': 'project(":a").projectDir = file("elsewhere")\n', **build})
    assert modules(moved) == {}, 'un dossier redefini ne fait pas de la racine un projet seul'
    flat = evaluate({'settings.gradle': "includeFlat 'sibling'\n", **build})
    assert modules(flat) == {}, 'un projet frere declare ne fait pas de la racine un projet seul'
    composite = evaluate({'settings.gradle': 'includeBuild "../tools"\n', **build})
    assert modules(composite) == {'.': ['gradle']}, 'un build inclus est un autre build, pas un projet'
    commented = evaluate({'settings.gradle': '// include "a"\nrootProject.name = "demo"\n', **build})
    assert modules(commented) == {'.': ['gradle']}


def test_what_gradle_reading_cannot_establish_is_declared_never_guessed():
    computed = evaluate({'settings.gradle': 'def names = ["a"]\ninclude names\ninclude "b"\n'})
    assert modules(computed) == {'b': ['gradle']}
    assert 'file:settings.gradle' in gaps(computed)
    moved = evaluate({'settings.gradle': 'include "a"\nproject(":a").projectDir = file("elsewhere")\n'})
    assert modules(moved) == {}, 'un dossier redefini ne se devine pas'
    assert 'file:settings.gradle' in gaps(moved)
    dynamic = evaluate({'settings.gradle': 'include "a", "b"\n',
                        'b/build.gradle': 'dependencies { implementation project(":${name}") }\n'
                                          'dependencies { implementation project(":ghost") }\n'})
    assert dependencies(dynamic) == set()
    assert 'file:b/build.gradle' in gaps(dynamic)
    assert dynamic.status == EvaluationStatus.PARTIAL


POM = '''<project xmlns="http://maven.apache.org/POM/4.0.0">
  <groupId>com.acme</groupId>
  <artifactId>parent</artifactId>
  <packaging>pom</packaging>
  <modules>
    <module>api</module>
    <module>app</module>
  </modules>
</project>
'''
APP_POM = '''<project xmlns="http://maven.apache.org/POM/4.0.0">
  <parent><groupId>com.acme</groupId><artifactId>parent</artifactId></parent>
  <artifactId>app</artifactId>
  <dependencies>
    <dependency>
      <groupId>com.acme</groupId>
      <artifactId>api</artifactId>
    </dependency>
    <dependency>
      <groupId>org.junit</groupId>
      <artifactId>junit</artifactId>
      <scope>test</scope>
    </dependency>
  </dependencies>
</project>
'''
API_POM = '''<project><parent><groupId>com.acme</groupId><artifactId>parent</artifactId></parent>
  <artifactId>api</artifactId></project>
'''


def test_maven_modules_and_dependencies_between_them():
    output = evaluate({'pom.xml': POM, 'app/pom.xml': APP_POM, 'api/pom.xml': API_POM})
    assert modules(output) == {'api': ['maven'], 'app': ['maven']}
    assert dependencies(output) == {('app', 'api', 'compile')}, 'une dependance externe n est pas un module'


def test_npm_packages_workspaces_and_local_dependencies():
    root = '{"name": "mono", "private": true, "workspaces": ["packages/*"]}'
    ui = '{"name": "@acme/ui", "dependencies": {"react": "^19", "@acme/core": "workspace:*"}}'
    core = '{"name": "@acme/core"}'
    tool = '{"name": "tool", "devDependencies": {"helper": "file:../helper"}}'
    output = evaluate({'package.json': root, 'packages/ui/package.json': ui, 'packages/core/package.json': core,
                       'tool/package.json': tool, 'helper/package.json': '{"name": "helper"}',
                       'node_modules/x/package.json': '{"name": "x"}'})
    assert set(modules(output)) == {'.', 'packages/ui', 'packages/core', 'tool', 'helper'}
    assert dependencies(output) == {('packages/ui', 'packages/core', 'dependencies'),
                                    ('tool', 'helper', 'devDependencies')}


def test_python_modules_and_path_dependencies_declared():
    output = evaluate({'backend/requirements.txt': 'fastapi\n', 'lib/pyproject.toml': '[project]\nname = "lib"\n',
                       'app/requirements.txt': '-e ../lib\n'})
    assert modules(output) == {'backend': ['python'], 'lib': ['python'], 'app': ['python']}
    assert 'file:app/requirements.txt' in gaps(output)


COMPOSE = '''services:
  db:
    image: postgres:17
  api:
    build: ./backend
  portal:
    build:
      context: frontend
      dockerfile: Dockerfile
  worker:
    build: ${WORKER_CONTEXT}
  docs:
    build: ./docs
'''


def test_compose_services_built_from_a_module_are_deployable_units():
    output = evaluate({'compose.yaml': COMPOSE, 'backend/requirements.txt': 'fastapi\n',
                       'frontend/package.json': '{"name": "portal"}'})
    assert applications(output) == {'application:compose.yaml#api': 'module:backend',
                                    'application:compose.yaml#portal': 'module:frontend'}
    assert 'file:compose.yaml' in gaps(output), 'contexte calcule, et contexte sans module reconnu'
    reasons = ' '.join(output.warnings)
    assert 'worker' in reasons
    assert 'docs' in reasons
    assert 'db' not in reasons, 'une image externe n est ni un fait ni une lacune'


def test_every_fact_satisfies_the_contract():
    files = {'settings.gradle': SETTINGS, 'web/build.gradle': WEB, 'core/build.gradle': '',
             'tools/cli/build.gradle': '', 'compose.yaml': 'services:\n  web:\n    build: web\n'}
    execution = RunEvaluator()(StructureEvaluator(), snapshot(files))
    assert execution.status == EvaluationStatus.SUCCESS
    assert {fact['relation'] for fact in execution.facts} == {'CONTAINS', 'DEPENDS_ON', 'BUILT_FROM'}


def test_the_impact_of_a_commit_shows_a_new_module_and_a_new_dependency(make_repo, git, tmp_path):
    repo = make_repo({'settings.gradle': 'include "core"\n', 'core/build.gradle': ''}, 'first')
    (repo / 'settings.gradle').write_text('include "core", "web"\n')
    (repo / 'web').mkdir()
    (repo / 'web' / 'build.gradle').write_text('dependencies { implementation project(":core") }\n')
    git(repo, 'add', '-A')
    git(repo, 'commit', '-qm', 'web')
    sha = git(repo, 'rev-parse', 'HEAD')
    app = create_app(f'sqlite:///{tmp_path / "structure.db"}', [repo])
    Base.metadata.create_all(app.state.engine)
    with TestClient(app) as client:
        project = client.post('/api/projects', json={'name': 'Structure', 'path': str(repo)}).json()
        impact = client.get(f'/api/projects/{project["id"]}/history/commits/{sha}/impact').json()
    structure = next(item for item in impact['evaluations'] if item['evaluator_id'] == 'taxo.structure')
    changes = {(item['change'], item['relation'], item['after']) for item in structure['changes']}
    assert changes == {('INTRODUCED', 'CONTAINS', 'module:web'), ('INTRODUCED', 'DEPENDS_ON', 'module:core')}


def test_empty_descriptors_are_modules_with_whole_file_evidence():
    execution = RunEvaluator()(StructureEvaluator(), snapshot({'lib/requirements.txt': '', 'build.gradle': ''}))
    assert execution.status == EvaluationStatus.SUCCESS
    evidence = [proof for fact in execution.facts for proof in fact['evidence']]
    assert evidence
    assert all('line_start' not in proof for proof in evidence)


def test_wrapped_project_dependencies_keep_their_outer_configuration():
    build = ('dependencies {\n    implementation(platform(project(":bom")))\n'
             '    testImplementation(testFixtures(project(":core")))\n}\n')
    output = evaluate({'settings.gradle': 'include "bom", "core", "app"\n', 'app/build.gradle': build})
    assert dependencies(output) == {('app', 'bom', 'implementation'), ('app', 'core', 'testImplementation')}


def test_a_maven_dependency_with_a_computed_group_is_never_attached():
    app = APP_POM.replace('<groupId>com.acme</groupId>\n      <artifactId>api</artifactId>',
                          '<groupId>${vendor.group}</groupId>\n      <artifactId>api</artifactId>')
    output = evaluate({'pom.xml': POM, 'app/pom.xml': app, 'api/pom.xml': API_POM})
    assert dependencies(output) == set()
    assert 'file:app/pom.xml' in gaps(output)
