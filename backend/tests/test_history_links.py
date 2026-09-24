"""TAXO-HIST-03 : relier une ligne modifiee du diff aux faits Taxo que le commit a changes."""
import json
import re

import pytest

from app.evaluations.application.run_evaluator import RunEvaluator
from app.evaluations.domain.evaluator import EvaluationOutput, EvaluatorCatalog
from app.evaluations.domain.status import EvaluationStatus
from app.evaluators.inventory.evaluator import InventoryEvaluator
from app.facts import content_hash
from app.history.application.queries import ProjectHistory
from app.history.domain.links import FILE, LINE, link
from app.history.infrastructure.git_history import GitHistoryReader
from app.projects.domain.project import Project
from app.snapshots.infrastructure.git.reader import GitSnapshotReader

RULE = re.compile(r'requestMatchers\("([^"]+)"\)\.(\w+)\(')


class RouteRules:
    """Evaluateur de test : un fait par regle de route, avec sa ligne comme preuve."""

    evaluator_id = 'test.routes'
    producer_version = '0.0.1'
    catalog = EvaluatorCatalog(catalog_id='routes', catalog_version='1', relations=('AUTHORIZED_BY',),
                               coverage_types=('ANALYSED',))

    def evaluate(self, snapshot):
        repository = f'repository:{snapshot.repository}'
        facts = []
        java = [file.path for file in snapshot.iter_files() if file.path.endswith('.java')]
        for path, data in snapshot.read_many(java):
            for number, text in enumerate(data.decode().splitlines(), 1):
                for pattern, rule in RULE.findall(text):
                    facts.append({
                        'contract_version': 1, 'kind': 'ASSERTION', 'status': 'OBSERVED', 'validity': 'VALID',
                        'subject': f'route-pattern:{pattern}', 'relation': 'AUTHORIZED_BY',
                        'object': f'symbol:{rule}', 'qualifiers': {},
                        'evidence': [{'repository': snapshot.repository, 'commit': snapshot.commit, 'path': path,
                                      'line_start': number, 'line_end': number, 'method': 'test.routes',
                                      'content_hash': content_hash(data)}]})
        coverage = ({'contract_version': 1, 'kind': 'COVERAGE', 'status': 'OBSERVED', 'validity': 'VALID',
                     'subject': repository, 'coverage_type': 'ANALYSED', 'scope': {'include': [repository]}},)
        return EvaluationOutput(tuple(facts), coverage, EvaluationStatus.SUCCESS, (), {})


def config(rule):
    return ('class SecurityConfig {\n'
            '  void chain(Http http) {\n'
            '    http.authorizeHttpRequests(auth -> auth\n'
            '      .requestMatchers("/api/health").permitAll()\n'
            f'      .requestMatchers("/api/v1/workspaces/**").{rule}\n'
            '      .anyRequest().authenticated());\n'
            '  }\n'
            '}\n')


def commit_all(git, repo, message):
    git(repo, 'add', '-A')
    git(repo, 'commit', '-qm', message)
    return git(repo, 'rev-parse', 'HEAD')


@pytest.fixture(name='secured')
def secured_fixture(make_repo, git):
    repo = make_repo({'SecurityConfig.java': config('permitAll()'), 'README.md': 'Taxo\n'}, 'secured')
    (repo / 'SecurityConfig.java').write_text(config('hasRole("WORKSPACE_READER")'))
    (repo / 'README.md').write_text('Taxo, source de verite\n')
    (repo / 'package.json').write_text(json.dumps({'dependencies': {'react': '19'}}))
    sha = commit_all(git, repo, 'protege les workspaces')

    class Projects:
        def get(self, project_id):
            return Project(project_id, 'demo', str(repo))

    class Paths:
        def resolve(self, value):
            return value

    history = ProjectHistory(Projects(), Paths(), GitHistoryReader(), GitSnapshotReader(),
                             [InventoryEvaluator(), RouteRules()], RunEvaluator())
    return history, sha


def test_a_modified_line_leads_to_the_fact_it_changed(secured):
    history, sha = secured
    result = history.diff_facts('demo', sha, 'SecurityConfig.java')
    assert result['not_comparable'] == []
    [fact] = [fact for fact in result['facts'] if fact['precision'] == LINE]
    assert (fact['change'], fact['subject'], fact['relation']) == ('MODIFIED', 'route-pattern:/api/v1/workspaces/**',
                                                                   'AUTHORIZED_BY')
    assert (fact['before'], fact['after']) == ('symbol:permitAll', 'symbol:hasRole')
    assert fact['lines'] == {'before': [5], 'after': [5]}
    assert fact['evaluator_id'] == 'test.routes'
    assert not any('/api/health' in item['subject'] for item in result['facts']), 'une regle inchangee n\'est pas liee'


def test_facts_proven_elsewhere_are_not_linked(secured):
    history, sha = secured
    readme = history.diff_facts('demo', sha, 'README.md')
    assert readme['facts'] == [], 'le README ne prouve aucun fait change'
    manifest = history.diff_facts('demo', sha, 'package.json')
    technologies = {fact['after'] for fact in manifest['facts']}
    assert 'technology:React' in technologies
    assert {fact['precision'] for fact in manifest['facts']} == {FILE}, 'preuve sans lignes : lien au fichier'
    assert all(fact['lines'] == {'before': [], 'after': []} for fact in manifest['facts'])


def test_the_api_serves_the_links(secured, make_repo, git, tmp_path):
    from fastapi.testclient import TestClient

    from app.bootstrap.database import Base
    from app.main import create_app

    history, sha = secured
    repo = history.projects.get('demo').path
    app = create_app(f'sqlite:///{tmp_path / "links.db"}', [repo])
    Base.metadata.create_all(app.state.engine)
    with TestClient(app) as client:
        project = client.post('/api/projects', json={'name': 'Liens', 'path': repo}).json()
        base = f'/api/projects/{project["id"]}/history/commits/{sha}/diff/facts'
        result = client.get(base, params={'path': 'package.json'}).json()
        assert result['commit'] == sha and result['facts']
        assert client.get(base, params={'path': 'absent.txt'}).status_code == 404


def change(evidence_before=(), evidence_after=(), name='x'):
    return {'change': 'MODIFIED', 'subject': f'endpoint:{name}', 'relation': 'R', 'kind': 'ASSERTION',
            'evidence_before': list(evidence_before), 'evidence_after': list(evidence_after)}


def hunk(*rows):
    return [{'before_start': 1, 'after_start': 1, 'rows': [
        {'kind': kind, 'before': {'number': before} if before else None, 'after': {'number': after} if after else None}
        for kind, before, after in rows]}]


def test_a_renamed_file_is_linked_through_its_old_path_on_the_left():
    moved = change([{'path': 'old/A.java', 'line_start': 2, 'line_end': 3}], [{'path': 'new/A.java'}])
    [linked] = link([moved], 'old/A.java', 'new/A.java', hunk(('changed', 3, 3), ('equal', 4, 4)))
    assert (linked['precision'], linked['lines']) == (LINE, {'before': [3], 'after': []})


def test_evidence_on_unchanged_lines_is_only_a_file_link():
    untouched = change(evidence_after=[{'path': 'A.java', 'line_start': 10, 'line_end': 12}])
    [linked] = link([untouched], 'A.java', 'A.java', hunk(('equal', 10, 10), ('added', None, 20)))
    assert (linked['precision'], linked['lines']) == (FILE, {'before': [], 'after': []})


def test_line_links_come_first_and_sides_are_never_mixed():
    left_only = change(evidence_before=[{'path': 'A.java', 'line_start': 1, 'line_end': 1}], name='left')
    right_only = change(evidence_after=[{'path': 'A.java'}], name='right')
    wrong_side = change(evidence_before=[{'path': 'B.java', 'line_start': 1, 'line_end': 1}], name='other')
    linked = link([right_only, left_only, wrong_side], 'A.java', 'A.java', hunk(('removed', 1, None)))
    assert [item['subject'] for item in linked] == ['endpoint:left', 'endpoint:right']
    assert link([left_only], None, 'A.java', hunk(('added', None, 1))) == [], 'un ajout n\'a pas de cote gauche'
