"""TAXO-EVAL-02 : Git devient un evaluateur ; ses faits sont conserves et interrogeables apres l'analyse."""
import inspect

import pytest
from fastapi.testclient import TestClient

from app.bootstrap.database import Base
from app.evaluations.application.run_evaluator import RunEvaluator
from app.evaluations.domain.evaluator import EvaluationOutput, EvaluatorCatalog
from app.evaluations.domain.status import EvaluationStatus
from app.evaluators.git.evaluator import GitEvaluator
from app.main import create_app
from app.snapshots.domain.mode import WORKING_TREE
from app.snapshots.infrastructure.git.reader import GitSnapshotReader

READER = GitSnapshotReader()


def commit_all(git, repo, message):
    git(repo, 'add', '-A')
    git(repo, 'commit', '-qm', message)
    return git(repo, 'rev-parse', 'HEAD')


@pytest.fixture(name='story')
def story_fixture(make_repo, git):
    repo = make_repo({'README.md': 'Taxo\n', 'docs/backlog/R1.md': 'recit\n', 'old.txt': 'adieu\n'}, 'story')
    root = git(repo, 'rev-parse', 'HEAD')
    (repo / 'docs' / 'done').mkdir()
    git(repo, 'mv', 'docs/backlog/R1.md', 'docs/done/R1.md')
    (repo / 'README.md').write_text('Taxo, source de verite\n')
    (repo / 'old.txt').unlink()
    moved = commit_all(git, repo, 'R1 termine')
    git(repo, 'checkout', '-qb', 'side')
    (repo / 'side.py').write_text('x = 1\n')
    side = commit_all(git, repo, 'side')
    git(repo, 'checkout', '-q', '-')
    (repo / 'App.java').write_text('class App {}\n')
    main = commit_all(git, repo, 'main')
    git(repo, 'merge', '-q', '--no-edit', 'side')
    merge = git(repo, 'rev-parse', 'HEAD')
    return repo, {'root': root, 'moved': moved, 'side': side, 'main': main, 'merge': merge}


def execute(repo, evaluator=None):
    return RunEvaluator()(evaluator or GitEvaluator(), READER.open(repo, 'depot'))


def facts_of(execution, relation, subject=None):
    return [fact for fact in execution.facts
            if fact['relation'] == relation and (subject is None or fact['subject'] == subject)]


def test_git_history_becomes_valid_taxo_facts(story):
    repo, sha = story
    execution = execute(repo)
    assert execution.status is EvaluationStatus.SUCCESS, execution.warnings
    assert {fact['object'] for fact in facts_of(execution, 'HAS_COMMIT')} == {f'commit:{value}' for value in sha.values()}
    moved = f'commit:{sha["moved"]}'
    [authored] = facts_of(execution, 'AUTHORED_BY', moved)
    assert (authored['object'], authored['qualifiers']) == ('person:taxo@example.invalid', {'name': 'Taxo'})
    changes = {fact['object']: fact['qualifiers'] for fact in facts_of(execution, 'CHANGES', moved)}
    assert changes == {'file:README.md': {'change': 'MODIFIED'}, 'file:old.txt': {'change': 'DELETED'},
                       'file:docs/done/R1.md': {'change': 'RENAMED', 'old_path': 'docs/backlog/R1.md'}}
    evidence = authored['evidence'][0]
    assert (evidence['object'], evidence['method']) == (moved, 'git.log') and 'path' not in evidence


def test_a_merge_keeps_both_parents_and_its_changes_against_the_first(story):
    repo, sha = story
    execution = execute(repo)
    merge = f'commit:{sha["merge"]}'
    parents = {fact['object']: fact['qualifiers']['position'] for fact in facts_of(execution, 'CHILD_OF', merge)}
    assert parents == {f'commit:{sha["main"]}': 1, f'commit:{sha["side"]}': 2}
    assert [fact['object'] for fact in facts_of(execution, 'CHANGES', merge)] == ['file:side.py']
    root = f'commit:{sha["root"]}'
    assert facts_of(execution, 'CHILD_OF', root) == [], 'un commit racine n a pas de parent'
    assert {fact['qualifiers']['change'] for fact in facts_of(execution, 'CHANGES', root)} == {'ADDED'}


def test_the_evaluator_has_no_presentation_window():
    assert list(inspect.signature(GitEvaluator.evaluate).parameters) == ['self', 'snapshot']
    assert 'limit' not in inspect.signature(GitEvaluator).parameters


def test_history_beyond_the_budget_is_declared_not_interpreted(story):
    repo, sha = story
    execution = execute(repo, GitEvaluator(max_commits=2))
    assert execution.status is EvaluationStatus.PARTIAL
    assert len(facts_of(execution, 'HAS_COMMIT')) == 2
    uncovered = [fact for fact in execution.coverage if fact['coverage_type'] == 'NOT_INTERPRETED']
    assert [fact['subject'] for fact in uncovered] in ([f'commit:{sha["main"]}'], [f'commit:{sha["side"]}'])
    assert execution.legacy == {'commits_count': 2, 'history_complete': False}


def test_an_unrepresentable_path_is_declared_not_silently_dropped(make_repo, git):
    repo = make_repo({'a.txt': 'a\n'}, 'odd')
    (repo / 'deux:points.txt').write_text('b\n')
    sha = commit_all(git, repo, 'chemin avec deux points')
    execution = execute(repo)
    assert execution.status is EvaluationStatus.PARTIAL
    assert not facts_of(execution, 'CHANGES', f'commit:{sha}')
    assert f'commit:{sha}' in {fact['subject'] for fact in execution.coverage if fact['coverage_type'] == 'NOT_INTERPRETED'}


def test_a_working_tree_snapshot_reads_the_history_of_head(story):
    repo, sha = story
    (repo / 'README.md').write_text('modifie sans commit\n')
    snapshot = READER.open(repo, 'depot', WORKING_TREE)
    execution = RunEvaluator()(GitEvaluator(), snapshot)
    assert f'commit:{sha["merge"]}' in {fact['object'] for fact in facts_of(execution, 'HAS_COMMIT')}


@pytest.fixture(name='api')
def api_fixture(story, tmp_path):
    repo, sha = story
    app = create_app(f'sqlite:///{tmp_path / "git.db"}', [repo])
    Base.metadata.create_all(app.state.engine)
    with TestClient(app) as client:
        project = client.post('/api/projects', json={'name': 'Git', 'path': str(repo)}).json()
        yield client, f'/api/projects/{project["id"]}', sha


def test_the_global_analysis_runs_every_evaluator_and_keeps_their_facts(api):
    client, base, sha = api
    analysis = client.post(f'{base}/scans').json()
    assert {item['evaluator_id'] for item in analysis['evaluations']} == {'taxo.git', 'taxo.inventory'}
    assert analysis['evaluation_summary']['evaluator_id'] == 'taxo.inventory', 'le resume principal reste le code'
    facts = f'{base}/scans/{analysis["id"]}/facts'
    commits = client.get(facts, params={'evaluator': 'taxo.git', 'relation': 'HAS_COMMIT'}).json()
    assert len(commits) == 5, "tout l'historique atteignable, sans fenetre"
    one = client.get(facts, params={'subject': f'commit:{sha["moved"]}', 'relation': 'CHANGES'}).json()
    assert {fact['object'] for fact in one} == {'file:README.md', 'file:old.txt', 'file:docs/done/R1.md'}
    assert all(fact['produced_by']['producer_id'] == 'taxo.git' for fact in one), 'la provenance est conservee'
    listed = client.get(f'{base}/scans').json()[0]
    assert 'produced_by' not in str(listed), 'la liste des analyses ne transporte pas les faits'
    assert client.get(f'{base}/scans/inconnue/facts').status_code == 404


def test_git_facts_meet_code_facts_through_the_same_file_reference(api):
    client, base, _ = api
    analysis = client.post(f'{base}/scans').json()
    facts = f'{base}/scans/{analysis["id"]}/facts'
    readme = client.get(facts, params={'object': 'file:README.md'}).json()
    relations = {(fact['produced_by']['producer_id'], fact['relation']) for fact in readme}
    assert {('taxo.inventory', 'CONTAINS'), ('taxo.git', 'CHANGES')} <= relations


def test_the_code_analysis_survives_a_failing_git_evaluator(api, monkeypatch):
    client, base, _ = api

    def broken(self, snapshot):
        raise ValueError('historique illisible')

    monkeypatch.setattr(GitEvaluator, 'evaluate', broken)
    analysis = client.post(f'{base}/scans')
    assert analysis.status_code == 201
    statuses = {item['evaluator_id']: item['status'] for item in analysis.json()['evaluations']}
    assert statuses == {'taxo.git': 'FAILED', 'taxo.inventory': 'SUCCESS'}
    assert analysis.json()['evaluation_summary']['fact_count'] > 0


def test_the_impact_of_a_commit_compares_content_only(api):
    client, base, sha = api
    impact = client.get(f'{base}/history/commits/{sha["moved"]}/impact').json()
    assert [item['evaluator_id'] for item in impact['evaluations']] == ['taxo.inventory']


def test_a_third_evaluator_joins_without_touching_the_first_two(story, tmp_path):
    from app.scans.application.run_scan import RunScan
    from app.evaluators.inventory.evaluator import InventoryEvaluator
    from app.projects.domain.project import Project

    repo, _ = story

    class Third:
        evaluator_id, producer_version = 'test.third', '0.0.1'
        catalog = EvaluatorCatalog(catalog_id='third', catalog_version='1', coverage_types=('ANALYSED',))

        def evaluate(self, snapshot):
            repository = f'repository:{snapshot.repository}'
            coverage = ({'contract_version': 1, 'kind': 'COVERAGE', 'status': 'OBSERVED', 'validity': 'VALID',
                         'subject': repository, 'coverage_type': 'ANALYSED', 'scope': {'include': [repository]}},)
            return EvaluationOutput((), coverage)

    class Projects:
        def get(self, project_id):
            return Project(project_id, 'demo', str(repo))

    class Paths:
        def resolve(self, value):
            return value

    class Scans:
        def add(self, scan):
            return scan

    class Store:
        def __init__(self):
            self.by_evaluator = {}

        def add(self, scan_id, evaluator_id, facts):
            self.by_evaluator[evaluator_id] = facts

    store = Store()
    run = RunScan(Projects(), Scans(), Paths(), READER, InventoryEvaluator(), RunEvaluator(),
                  others=(GitEvaluator(), Third()), facts=store)
    result = run('demo').result
    assert [item['evaluator_id'] for item in result['evaluations']] == ['taxo.inventory', 'taxo.git', 'test.third']
    assert set(store.by_evaluator) == {'taxo.inventory', 'taxo.git', 'test.third'}


def test_history_paths_are_nfc_like_the_snapshot(make_repo, git):
    repo = make_repo({'a.txt': 'a\n'}, 'nfc')
    (repo / 'café.py').write_text('x = 1\n')
    sha = commit_all(git, repo, 'chemin decompose')
    execution = execute(repo)
    assert [fact['object'] for fact in facts_of(execution, 'CHANGES', f'commit:{sha}')] == ['file:café.py']


def test_a_non_utf8_path_is_declared_not_interpreted_not_failed(make_repo, git):
    import os
    repo = make_repo({'a.txt': 'a\n'}, 'latin')
    with open(os.path.join(os.fsencode(repo), b'caf\xe9.txt'), 'wb') as handle:
        handle.write(b'b\n')
    sha = commit_all(git, repo, 'chemin latin-1')
    os.remove(os.path.join(os.fsencode(repo), b'caf\xe9.txt'))
    commit_all(git, repo, "absent de l'instantane, present dans l'historique")
    execution = execute(repo)
    assert execution.status is EvaluationStatus.PARTIAL, execution.warnings
    assert not facts_of(execution, 'CHANGES', f'commit:{sha}')
    assert f'commit:{sha}' in {fact['subject'] for fact in execution.coverage if fact['coverage_type'] == 'NOT_INTERPRETED'}


def test_a_leading_newline_stays_part_of_the_path(make_repo, git):
    repo = make_repo({'secret.txt': 's\n'}, 'newline')
    (repo / '\nsecret.txt').write_text('autre\n')
    sha = commit_all(git, repo, 'nom avec saut de ligne')
    execution = execute(repo)
    assert 'file:secret.txt' not in {fact['object'] for fact in facts_of(execution, 'CHANGES', f'commit:{sha}')}


def test_a_non_utf8_commit_message_does_not_fail_the_history(make_repo, git):
    repo = make_repo({'a.txt': 'a\n'}, 'message')
    (repo / 'b.txt').write_text('b\n')
    git(repo, 'add', '-A')
    git(repo, 'commit', '-qm', 'résumé'.encode('latin-1').decode('utf-8', 'surrogateescape'))
    execution = execute(repo)
    assert execution.status is EvaluationStatus.SUCCESS, execution.warnings
