"""TAXO-QUERY-01 : la requete selectionne parmi les faits Git conserves ; Minia n'explique que la selection."""
import json

import pytest
from fastapi.testclient import TestClient

from app.bootstrap.database import Base
from app.main import create_app
from app.projection.domain.errors import QueryError
from app.projection.domain.projection import log_order
from app.projection.domain.request import COMMIT, GLOBAL, LATEST, PERIOD, parse


@pytest.mark.parametrize('text, count', [
    ('Montre les 10 derniers commits', 10), ('3 derniers', 3), ('les trois dernières modifications', 3),
    ('Quel est le dernier commit ?', 1), ('les derniers 5 commits', 5), ('last 2 commits', 2)])
def test_an_explicit_number_selects_that_many_commits(text, count):
    request = parse(text)
    assert (request.kind, request.count) == (LATEST, count)


@pytest.mark.parametrize('text', ['Analyse le projet', 'Lance l’analyse globale', 'les derniers commits',
                                  'Que fait ce projet ?', 'commit 12'])
def test_no_number_is_ever_assumed(text):
    request = parse(text)
    assert request.kind == GLOBAL and request.count is None, 'aucune fenetre par defaut'


def test_a_commit_is_selected_by_its_identifier():
    assert parse('Que change le commit 5b9022b ?').commit == '5b9022b'
    assert parse('explique ABCDEF1234').commit == 'abcdef1234'
    assert parse('commit 1234567').kind == COMMIT
    assert parse('1234567 derniers commits').kind == LATEST, 'un nombre seul n est pas un identifiant'


@pytest.mark.parametrize('text, since, until', [
    ('depuis 2026-09-01', '2026-09-01', None),
    ('jusqu’au 2026-09-10', None, '2026-09-10'),
    ('avant 2026-09-10', None, '2026-09-09'),
    ('entre 2026-09-01 et 2026-09-10', '2026-09-01', '2026-09-10'),
    ('du 2026-09-01 au 2026-09-10', '2026-09-01', '2026-09-10'),
    ('commits de 2026-02', '2026-02-01', '2026-02-28'),
    ('le 2026-12-31', '2026-12-31', '2026-12-31'),
    ('2026-09-01 2026-09-03', '2026-09-01', '2026-09-03')])
def test_a_period_is_read_from_iso_dates(text, since, until):
    request = parse(text)
    assert (request.kind, request.since, request.until) == (PERIOD, since, until)


def test_a_number_and_a_period_combine():
    request = parse('les 3 derniers commits depuis 2026-09-01')
    assert (request.kind, request.count, request.since) == (LATEST, 3, '2026-09-01')


@pytest.mark.parametrize('text', ['0 derniers commits', 'depuis 2026-02-30', 'entre 2026-09-10 et 2026-09-01'])
def test_an_impossible_request_is_refused(text):
    with pytest.raises(QueryError):
        parse(text)


def test_children_always_come_before_their_parents_then_newest_first():
    commits = {'root': {'authored_at': '2026-09-30T00:00:00+00:00'},
               'a': {'authored_at': '2026-09-02T00:00:00+00:00'},
               'b': {'authored_at': '2026-09-03T00:00:00+02:00'},
               'merge': {'authored_at': '2026-09-01T00:00:00+00:00'}}
    parents = {'root': [], 'a': ['root'], 'b': ['root'], 'merge': ['a', 'b', 'outside']}
    assert log_order(commits, parents) == ['merge', 'b', 'a', 'root']


def test_like_git_the_most_recently_committed_tip_comes_first():
    commits = {'rebased': {'authored_at': '2026-01-01T00:00:00+00:00', 'committed_at': '2026-09-20T00:00:00+00:00'},
               'fresh': {'authored_at': '2026-09-10T00:00:00+00:00', 'committed_at': '2026-09-10T00:00:00+00:00'}}
    assert log_order(commits, {'rebased': [], 'fresh': []}) == ['rebased', 'fresh']


def commit_on(git, repo, name, day):
    (repo / f'{name}.txt').write_text(f'{name}\n')
    git(repo, 'add', '-A')
    git(repo, 'commit', '-qm', f'ajoute {name}', f'--date=2026-09-{day:02d}T12:00:00+00:00')
    return git(repo, 'rev-parse', 'HEAD')


@pytest.fixture(name='history')
def history_fixture(make_repo, git):
    repo = make_repo({'README.md': 'Taxo\n'}, 'query')
    git(repo, 'commit', '-q', '--amend', '--no-edit', '--date=2026-08-31T12:00:00+00:00')
    shas = [git(repo, 'rev-parse', 'HEAD')] + [commit_on(git, repo, f'f{day}', day) for day in range(1, 6)]
    return repo, shas  # du plus ancien (31 aout) au plus recent (5 septembre)


class FakeModel:
    provider, model_name = 'fake', 'fake-1'

    def __init__(self, reply):
        self.reply, self.calls = reply, []

    def complete(self, system, user):
        self.calls.append((system, user))
        return json.dumps(self.reply)


@pytest.fixture(name='api')
def api_fixture(history, tmp_path):
    repo, shas = history
    model = FakeModel({'cited': ['F1', 'F2'], 'answer': 'Deux fichiers auraient été ajoutés.', 'unknown': ''})
    app = create_app(f'sqlite:///{tmp_path / "query.db"}', [repo], minia=model)
    Base.metadata.create_all(app.state.engine)
    with TestClient(app) as client:
        project = client.post('/api/projects', json={'name': 'Requetes', 'path': str(repo)}).json()
        base = f'/api/projects/{project["id"]}'
        yield client, base, shas, model


def query(client, base, text):
    return client.get(f'{base}/query', params={'q': text})


def test_nothing_is_selected_before_the_global_analysis(api):
    client, base, _, _ = api
    response = query(client, base, '3 derniers commits')
    assert response.status_code == 409 and 'NO_ANALYSIS' in response.json()['detail']


def test_the_request_selects_after_the_analysis(api):
    client, base, shas, _ = api
    client.post(f'{base}/scans')
    ten = query(client, base, '10 derniers commits').json()
    assert [commit['sha'] for commit in ten['commits']] == shas[::-1], 'moins de 10 commits : tous, du plus recent'
    three = query(client, base, '3 derniers commits').json()
    assert [commit['sha'] for commit in three['commits']] == shas[:-4:-1]
    assert (three['status'], three['total_commits']) == ('SELECTED', 6)
    subjects = {fact['subject'] for fact in three['facts'] if fact['relation'] != 'HAS_COMMIT'}
    assert subjects == {f'commit:{sha}' for sha in shas[-3:]}, 'seuls les faits des commits vises'
    assert all(fact['produced_by']['producer_id'] == 'taxo.git' for fact in three['facts']), 'provenance conservee'
    assert all(fact['evidence'][0]['object'].startswith('commit:') for fact in three['facts'])


def test_a_commit_and_a_period_are_selected_from_the_same_facts(api):
    client, base, shas, _ = api
    client.post(f'{base}/scans')
    one = query(client, base, f'Que change le commit {shas[2][:9]} ?').json()
    assert [commit['sha'] for commit in one['commits']] == [shas[2]]
    assert {fact['object'] for fact in one['facts'] if fact['relation'] == 'CHANGES'} == {'file:f2.txt'}
    assert query(client, base, 'commit abcdef1').json()['status'] == 'NOT_FOUND'
    period = query(client, base, 'entre 2026-09-02 et 2026-09-04').json()
    assert [commit['sha'] for commit in period['commits']] == [shas[4], shas[3], shas[2]]
    both = query(client, base, '2 derniers commits avant 2026-09-04').json()
    assert [commit['sha'] for commit in both['commits']] == [shas[3], shas[2]]


def test_analysing_the_project_never_becomes_the_latest_commits(api):
    client, base, _, _ = api
    client.post(f'{base}/scans')
    result = query(client, base, 'Analyse le projet').json()
    assert (result['status'], result['commits'], result['facts']) == ('GLOBAL', [], [])
    assert {item['evaluator_id'] for item in result['evaluations']} == {'taxo.inventory', 'taxo.git', 'taxo.spring-api'}
    assert query(client, base, '0 derniers commits').status_code == 422


def test_minia_receives_only_the_targeted_facts(api):
    client, base, shas, model = api
    client.post(f'{base}/scans')
    answer = client.post(f'{base}/ask', json={'question': 'Résume les 2 derniers commits'}).json()
    assert answer['status'] == 'ANSWERED' and answer['answer'] == 'Deux fichiers auraient été ajoutés.'
    sent = model.calls[0][1]
    commits = {fact['object'] for fact in json.loads(sent)['facts'] if fact['relation'] == 'HAS_COMMIT'}
    assert commits == {f'commit:{sha}' for sha in shas[-2:]}, 'seuls les commits vises sont transmis'
    assert {fact['subject'] for fact in json.loads(sent)['facts'] if fact['relation'] != 'HAS_COMMIT'} \
        == commits, 'aucun fait d un autre commit'
    assert 'file:f3.txt' not in sent and 'README' not in sent
    assert json.loads(sent)['request']['count'] == 2
    assert [fact['ref'] for fact in answer['facts']] == ['F1', 'F2']
    assert answer['facts'][0]['produced_by']['producer_id'] == 'taxo.git', 'les faits cites sont ceux de Taxo'
    assert [commit['sha'] for commit in answer['commits']] == shas[:-3:-1]


def test_minia_asks_for_a_selection_instead_of_guessing_one(api):
    client, base, _, model = api
    client.post(f'{base}/scans')
    vague = client.post(f'{base}/ask', json={'question': 'Analyse le projet'}).json()
    assert vague['status'] == 'NEEDS_SELECTION' and vague['commits'] == []
    missing = client.post(f'{base}/ask', json={'question': 'Que fait le commit abcdef1 ?'}).json()
    assert missing['status'] == 'TAXO_KNOWS_NOTHING' and 'identifiant' in missing['unknown']
    assert model.calls == [], 'le modele n est pas appele sans faits a expliquer'


def test_a_failed_git_evaluator_is_said_not_hidden(api, monkeypatch):
    from app.evaluators.git.evaluator import GitEvaluator

    def broken(self, snapshot):
        raise ValueError('historique illisible')

    client, base, _, model = api
    monkeypatch.setattr(GitEvaluator, 'evaluate', broken)
    client.post(f'{base}/scans')
    assert query(client, base, '3 derniers commits').json()['status'] == 'NO_GIT_FACTS'
    answer = client.post(f'{base}/ask', json={'question': '3 derniers commits'}).json()
    assert answer['status'] == 'TAXO_KNOWS_NOTHING' and 'relancez' in answer['unknown']
    assert model.calls == []


def test_the_projection_selects_nothing_for_a_global_request_and_tolerates_unknown_dates():
    from app.projection.domain.projection import select
    fact = {'kind': 'ASSERTION', 'relation': 'HAS_COMMIT', 'subject': 'repository:r', 'object': 'commit:' + 'a' * 40,
            'qualifiers': {'authored_at': 'inconnue', 'subject': 's'}}
    assert select([fact], parse('Analyse le projet'))['commits'] == []
    assert [item['sha'] for item in select([fact], parse('1 dernier commit'))['commits']] == ['a' * 40]
