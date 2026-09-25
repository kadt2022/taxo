"""TAXO-UX-02 : une analyse annonce ses vraies etapes pendant qu'elle travaille."""
import json

import pytest
from fastapi.testclient import TestClient

from app.bootstrap.database import Base
from app.evaluations.application.run_evaluator import RunEvaluator
from app.evaluators.git.evaluator import GitEvaluator
from app.main import create_app
from app.scans.application.analysis_jobs import AnalysisJob
from app.scans.api.router import sse
from app.snapshots.infrastructure.git.reader import GitSnapshotReader


def events_of(response):
    """Evenements SSE d'une reponse : (type, donnees), commentaires ignores."""
    parsed, current = [], {}
    for line in response.iter_lines():
        if not line:
            if current:
                parsed.append((current['event'], json.loads(current['data'])))
            current = {}
        elif not line.startswith(':'):
            key, _, value = line.partition(': ')
            current[key] = value
    return parsed


@pytest.fixture(name='api')
def api_fixture(make_repo, tmp_path):
    repo = make_repo({'README.md': 'Taxo\n', 'package.json': '{"dependencies":{"react":"19"}}'}, 'progres')
    app = create_app(f'sqlite:///{tmp_path / "progress.db"}', [repo])
    Base.metadata.create_all(app.state.engine)
    with TestClient(app) as client:
        project = client.post('/api/projects', json={'name': 'Progres', 'path': str(repo)}).json()
        yield client, f'/api/projects/{project["id"]}'


def run_analysis(client, base, **params):
    started = client.post(f'{base}/analyses', params=params)
    assert started.status_code == 202, started.text
    with client.stream('GET', started.json()['events']) as response:
        assert response.headers['content-type'].startswith('text/event-stream')
        return started.json()['id'], events_of(response)


def test_the_analysis_announces_its_real_steps_in_order(api):
    client, base = api
    job_id, events = run_analysis(client, base)
    types = [event_type for event_type, _ in events]
    assert types[0] == 'analysis.started' and types[-1] == 'analysis.completed'
    assert events[0][1]['evaluators'] == ['taxo.inventory', 'taxo.git']
    assert types.index('snapshot.ready') < types.index('evaluator.started')
    started = [data['evaluator'] for event_type, data in events if event_type == 'evaluator.started']
    completed = [data['evaluator'] for event_type, data in events if event_type == 'evaluator.completed']
    assert started == completed == ['taxo.inventory', 'taxo.git'], 'chaque evaluateur termine avant le suivant'
    assert types.index('analysis.consolidating') > types.index('evaluator.completed')


def test_each_evaluator_publishes_its_results_as_soon_as_it_finishes(api):
    client, base = api
    job_id, events = run_analysis(client, base)
    inventory = next(data for event_type, data in events
                     if event_type == 'evaluator.completed' and data['evaluator'] == 'taxo.inventory')
    assert inventory['result']['files_count'] == 2
    assert {fact['technology'] for fact in inventory['result']['facts']} >= {'React'}
    assert inventory['summary']['fact_count'] > 0
    git = next(data for event_type, data in events
               if event_type == 'evaluator.completed' and data['evaluator'] == 'taxo.git')
    assert git['result'] is None and git['summary']['relations']['HAS_COMMIT'] == 1
    final = events[-1][1]['scan']
    assert final['id'] == job_id, "l'analyse conservee porte l'identifiant annonce au lancement"
    assert client.get(f'{base}/scans').json()[0]['id'] == job_id


def test_progress_is_real_never_an_estimated_percentage(api):
    client, base = api
    _, events = run_analysis(client, base)
    progress = [data for event_type, data in events if event_type == 'evaluator.progress']
    files = next(data for data in progress if data['stage'] == 'files')
    assert (files['evaluator'], files['completed'], files['total']) == ('taxo.inventory', 2, 2)
    history = [data for data in progress if data['stage'] == 'history']
    assert history[-1] == {'evaluator': 'taxo.git', 'stage': 'history', 'message': 'Commits lus',
                           'completed': 1, 'total': 1}
    assert all('percent' not in data for data in progress)


def test_a_failing_evaluator_is_reported_without_stopping_the_analysis(api, monkeypatch):
    client, base = api

    def broken(self, snapshot, progress=None):
        raise ValueError('historique illisible')

    monkeypatch.setattr(GitEvaluator, 'evaluate', broken)
    _, events = run_analysis(client, base)
    failed = next(data for event_type, data in events if event_type == 'evaluator.failed')
    assert failed['evaluator'] == 'taxo.git' and 'historique illisible' in failed['message']
    assert events[-1][0] == 'analysis.completed'


def test_a_failed_analysis_ends_the_stream_with_its_reason(make_repo, tmp_path):
    repo = make_repo({'a.txt': 'a\n'}, 'racine')
    (repo / 'sous-dossier').mkdir()
    app = create_app(f'sqlite:///{tmp_path / "failed.db"}', [repo])
    Base.metadata.create_all(app.state.engine)
    with TestClient(app) as client:
        project = client.post('/api/projects', json={'name': 'Pas Git', 'path': str(repo / 'sous-dossier')}).json()
        _, events = run_analysis(client, f'/api/projects/{project["id"]}')
    assert events[-1][0] == 'analysis.failed' and 'NOT_A_GIT_REPOSITORY' in events[-1][1]['message']


def test_a_reconnecting_browser_resumes_after_the_last_event(api):
    client, base = api
    job_id, events = run_analysis(client, base)
    with client.stream('GET', f'{base}/analyses/{job_id}/events', headers={'Last-Event-ID': '3'}) as response:
        replay = events_of(response)
    assert replay == events[3:]


def test_bad_requests_are_refused_before_anything_starts(api):
    client, base = api
    assert client.post('/api/projects/inconnu/analyses').status_code == 404
    assert client.post(f'{base}/analyses', params={'mode': 'nimporte'}).status_code == 422
    assert client.get(f'{base}/analyses/inconnue/events').status_code == 404


def test_a_job_journal_follows_live_and_keeps_the_connection_alive():
    job = AnalysisJob('j', 'p')
    follower = job.follow(heartbeat=0.01)
    assert next(follower) is None, 'rien de neuf : un battement garde la connexion'
    job.emit('analysis.started', {})
    assert next(follower)['type'] == 'analysis.started'
    job.emit('analysis.completed', {})
    job.emit('evaluator.started', {})
    assert [event['type'] for event in follower] == ['analysis.completed'], 'rien apres la fin'
    assert sse(None) == ': en cours\n\n'
    assert sse({'id': 1, 'type': 't', 'data': {'a': 'é'}}) == 'id: 1\nevent: t\ndata: {"a": "é"}\n\n'


def test_an_evaluator_without_progress_support_runs_as_before(make_repo):
    class Plain(GitEvaluator):
        def evaluate(self, snapshot):
            return super().evaluate(snapshot)

    repo = make_repo({'a.txt': 'a\n'}, 'plain')
    calls = []
    execution = RunEvaluator()(Plain(), GitSnapshotReader().open(repo, 'r'), lambda *args, **kw: calls.append(args))
    assert execution.status.value == 'SUCCESS' and calls == []


def test_an_unexpected_crash_still_ends_the_stream_and_old_journals_are_released(monkeypatch):
    from app.projects.domain.project import Project, ProjectError
    from app.scans.application import analysis_jobs

    class Projects:
        def get(self, project_id):
            return Project(project_id, 'demo', 'x')

    def crash(*args, **kwargs):
        raise RuntimeError('panne')

    jobs = analysis_jobs.AnalysisJobs(crash, Projects(), workers=1)
    job = jobs.start('p')
    assert [event['type'] for event in job.follow()][-1] == 'analysis.failed'
    assert 'RuntimeError' in job.events[-1]['data']['message']
    monkeypatch.setattr(analysis_jobs, 'KEPT', 1)
    newer = jobs.start('p')
    list(newer.follow())
    with pytest.raises(ProjectError):
        jobs.get('p', job.id)
    with pytest.raises(ProjectError):
        jobs.get('autre', newer.id)
