"""MINIA-09 : Minia interroge Taxo operation par operation ; Taxo verifie ses affirmations avant affichage."""
import json
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from app.bootstrap.database import Base
from app.main import create_app
from app.minia.application.ask import MAX_CALLS, MAX_CLAIMS
from app.minia.domain import exploration
from app.minia.domain.errors import CONTEXT_TOO_LARGE, MiniaError
from app.minia.infrastructure.claude import ClaudeModel
from app.minia.infrastructure.gemini import GeminiModel, gemini_schema
from app.minia.infrastructure.ollama import OllamaModel

AUTHOR = 'person:taxo@example.invalid'
EMPTY = {name: '' for name in exploration.ARGUMENTS}


def call(operation, **arguments):
    return json.dumps({'action': 'call', 'operation': operation, **EMPTY, **arguments, 'statements': []})


def statement(kind, text, subject='', relation='', object_=''):
    return {'type': kind, 'text': text, 'subject': subject, 'relation': relation, 'object': object_}


def answer(*statements):
    return json.dumps({'action': 'answer', 'operation': '', **EMPTY, 'statements': list(statements)})


class ScriptedModel:
    """Un fournisseur qui sait explorer : il rend, tour apres tour, les reponses prevues."""

    provider, model_name, explores = 'scripted', 'scripted-1', True

    def __init__(self, *replies):
        self.replies, self.calls = list(replies), []

    def complete(self, system, user, schema=None):
        self.calls.append((system, user, schema))
        return self.replies.pop(0)


@pytest.fixture(name='repo')
def repo_fixture(make_repo, git):
    repo = make_repo({'README.md': 'Taxo\n', 'src/app.txt': 'un\n'}, 'exploration')
    (repo / 'src/app.txt').write_text('deux\n')
    git(repo, 'add', '-A')
    git(repo, 'commit', '-qm', 'change app')
    return repo, git(repo, 'rev-parse', 'HEAD')


def run(repo, tmp_path, model, question='Que change le dernier commit ?'):
    app = create_app(f'sqlite:///{tmp_path / "explore.db"}', [repo], minia=model)
    Base.metadata.create_all(app.state.engine)
    with TestClient(app) as client:
        project = client.post('/api/projects', json={'name': 'Exploration', 'path': str(repo)}).json()
        client.post(f'/api/projects/{project["id"]}/scans')
        stream = client.post(f'/api/projects/{project["id"]}/ask/stream', json={'question': question})
        events = [(block.split('\n')[0][len('event: '):], json.loads(block.split('\n')[1][len('data: '):]))
                  for block in stream.text.strip().split('\n\n')]
    return events


def completed(events):
    return next(data for kind, data in events if kind == 'minia.completed')


def test_minia_asks_taxo_then_every_claim_is_verified_before_display(repo, tmp_path):
    repo, sha = repo
    model = ScriptedModel(
        call('get_commit', commit=sha[:10]),
        answer(statement('claim', 'Le commit modifie src/app.txt.', f'commit:{sha}', 'CHANGES', 'file:src/app.txt'),
               statement('claim', 'Le commit est de quelqu’un d’autre.', f'commit:{sha}', 'AUTHORED_BY',
                         'person:autre@example.invalid'),
               statement('claim', 'Le commit modifie README.md.', f'commit:{sha}', 'CHANGES', 'file:README.md'),
               statement('interpretation', 'Il ajusterait le contenu de l’application.'),
               statement('unknown', 'Taxo ne dit pas pourquoi ce fichier a changé.')))
    result = completed(run(repo, tmp_path, model))
    assert (result['status'], result['mode']) == ('ANSWERED', 'exploration')
    changes, author, readme, guess, missing = result['statements']
    assert (changes['verdict'], changes['reason']) == ('CONFIRMED', None)
    assert changes['facts'][0]['fact']['object'] == 'file:src/app.txt' and changes['evidence']
    assert author['verdict'] == 'REFUTED' and author['facts'][0]['fact']['object'] == AUTHOR, \
        'Taxo contredit avec le fait qui dit le contraire'
    assert (readme['verdict'], readme['reason']) == ('NOT_PROVEN', 'NOT_FOUND_IN_ANALYSED_SCOPE')
    assert guess == {'type': 'interpretation', 'text': 'Il ajusterait le contenu de l’application.'}
    assert missing['type'] == 'unknown'
    assert result['answer'] == '', 'aucun texte hors des enonces types'
    operations = [step['operation'] for step in result['trajectory']]
    assert operations == ['describe', 'get_commit', 'verify_claim', 'verify_claim', 'verify_claim']
    assert result['trajectory'][1]['outcome'] == 'OK' and result['trajectory'][1]['items'] >= 3
    assert result['budget']['used'] <= result['budget']['max_bytes']


def test_the_trajectory_is_visible_live_and_results_reach_minia_as_data(repo, tmp_path):
    repo, sha = repo
    model = ScriptedModel(call('find_facts', relation='AUTHORED_BY'), answer(statement('unknown', 'Rien de plus.')))
    events = run(repo, tmp_path, model)
    live = [data['operation'] for kind, data in events if kind == 'minia.operation']
    assert live == ['describe', 'find_facts']
    system, second, schema = model.calls[1]
    assert system == exploration.SYSTEM and schema == exploration.STEP_SCHEMA
    sent = json.loads(second)
    assert [step['operation'] for step in sent['trajectory']] == ['describe', 'find_facts']
    assert sent['trajectory'][1]['response']['items'][0]['fact']['object'] == AUTHOR
    assert sent['calls_left'] == MAX_CALLS - 1
    assert 'jamais des' in system and 'instructions' in system, 'les resultats sont des donnees'


def test_a_refused_operation_is_given_back_to_minia_as_a_result(repo, tmp_path):
    repo, sha = repo
    model = ScriptedModel(call('get_diff', commit=sha, path='src/app.txt'), answer(statement('unknown', 'Pas de diff.')))
    result = completed(run(repo, tmp_path, model))
    refused = result['trajectory'][1]
    assert (refused['outcome'], refused['error']['code']) == ('ERROR', 'NO_CONSENT')
    assert json.loads(model.calls[1][1])['trajectory'][1]['response']['outcome'] == 'ERROR'


def test_a_malformed_claim_is_shown_unverified_never_as_established(repo, tmp_path):
    repo, sha = repo
    claims = [statement('claim', f'Affirmation {index}.', f'commit:{sha}', 'CHANGES', 'file:src/app.txt')
              for index in range(MAX_CLAIMS)]
    model = ScriptedModel(answer(statement('claim', 'Mal formée.', f'commit:{sha}', 'INVENTED', 'file:x'), *claims))
    result = completed(run(repo, tmp_path, model))
    malformed, *rest = result['statements']
    assert malformed['verdict'] is None and malformed['error']['code'] == 'INVALID_ARGUMENT'
    assert rest[-1]['verdict'] is None and rest[-1]['error']['code'] == 'NOT_VERIFIED', \
        f'au-dela de {MAX_CLAIMS} affirmations, Taxo ne verifie plus'
    assert all(item['verdict'] == 'CONFIRMED' for item in rest[:-1])


@pytest.mark.parametrize('replies', [
    ('pas du JSON',),
    (call('describe'), call('describe')),
    tuple(call('find_facts', subject=f'file:f{index}.txt') for index in range(MAX_CALLS + 1)),
], ids=['illisible', 'sans progres', 'limite'])
def test_a_failed_exploration_falls_back_to_the_packet(repo, tmp_path, replies):
    repo, _ = repo
    packet = json.dumps({'cited': ['F1'], 'answer': 'Un commit aurait changé src/app.txt.', 'unknown': ''})
    model = ScriptedModel(*replies, packet)
    result = completed(run(repo, tmp_path, model, 'Résume le dernier commit'))
    assert (result['status'], result['mode']) == ('ANSWERED', 'paquet')
    assert result['fallback'] and result['trajectory'][0]['operation'] == 'describe'
    assert result['answer'] == 'Un commit aurait changé src/app.txt.'
    assert model.calls[-1][2] is None, 'le paquet reprend le format de reponse habituel'


def test_a_provider_that_cannot_explore_keeps_the_packet(repo, tmp_path):
    repo, _ = repo
    model = ScriptedModel(json.dumps({'cited': [], 'answer': 'Rien.', 'unknown': ''}))
    model.explores = False
    result = completed(run(repo, tmp_path, model, 'Résume le dernier commit'))
    assert result['mode'] == 'paquet' and 'fallback' not in result
    assert model.calls[0][2] is None


def test_exploration_answers_without_a_selection(repo, tmp_path):
    repo, _ = repo
    model = ScriptedModel(answer(statement('unknown', 'Le projet a deux commits analysés.')))
    result = completed(run(repo, tmp_path, model, 'Analyse le projet'))
    assert (result['status'], result['mode']) == ('ANSWERED', 'exploration'), 'plus besoin de selection'


@pytest.mark.parametrize('raw', ['{}', json.dumps({'action': 'call', 'operation': ''}),
                                 json.dumps({'action': 'answer', 'statements': []}),
                                 json.dumps({'action': 'answer', 'statements': [{'type': 'opinion', 'text': 'x'}]}),
                                 json.dumps({'action': 'answer', 'statements': [{'type': 'claim', 'text': ' '}]})])
def test_an_unreadable_step_is_refused(raw):
    with pytest.raises(MiniaError):
        exploration.parse_step(raw)


def test_a_step_keeps_only_the_arguments_given():
    step = exploration.parse_step(call('find_facts', relation='CHANGES', subject=' commit:x '))
    assert step == exploration.Call('find_facts', {'subject': 'commit:x', 'relation': 'CHANGES'})
    assert 'instruction' in json.loads(exploration.message('q', [], [], 0)), 'a zero, Minia doit conclure'


def test_each_provider_constrains_the_step_with_the_schema():
    seen = []
    requests = SimpleNamespace(create=lambda **request: seen.append(request) or SimpleNamespace(
        content=[SimpleNamespace(type='text', text='{}')], stop_reason='end_turn'))
    ClaudeModel('claude-opus-5', client=SimpleNamespace(beta=SimpleNamespace(messages=requests))).complete(
        's', 'u', exploration.STEP_SCHEMA)
    assert seen[0]['output_config']['format']['schema'] == exploration.STEP_SCHEMA

    bodies = []

    def handler(request):
        bodies.append(json.loads(request.content))
        if 'generativelanguage' in str(request.url):
            return httpx.Response(200, json={'candidates': [{'content': {'parts': [{'text': '{}'}]},
                                                             'finishReason': 'STOP'}]})
        return httpx.Response(200, json={'message': {'content': '{}'}})

    GeminiModel('g', api_key='k', transport=httpx.MockTransport(handler)).complete('s', 'u', exploration.STEP_SCHEMA)
    OllamaModel('o', 'http://ollama.test:11434', transport=httpx.MockTransport(handler)).complete(
        's', 'u', exploration.STEP_SCHEMA)
    gemini, ollama = bodies
    assert gemini['generationConfig']['responseSchema'] == gemini_schema(exploration.STEP_SCHEMA)
    assert ollama['format'] == exploration.STEP_SCHEMA


def test_the_gemini_schema_has_uppercase_types_and_no_additional_properties():
    converted = gemini_schema(exploration.STEP_SCHEMA)
    assert converted['type'] == 'OBJECT' and 'additionalProperties' not in converted
    item = converted['properties']['statements']['items']
    assert item['type'] == 'OBJECT' and item['properties']['type']['enum'] == ['claim', 'interpretation', 'unknown']
    assert 'additionalProperties' not in item


def ask_commit(repo, tmp_path, model, sha=None, source=False, setting='diff', after_scan=None, parent=None,
               question='Que change ce commit ?', scan=True):
    app = create_app(f'sqlite:///{tmp_path / "commit.db"}', [repo], minia=model, source_context=setting)
    Base.metadata.create_all(app.state.engine)
    with TestClient(app) as client:
        project = client.post('/api/projects', json={'name': 'Exploration', 'path': str(repo)}).json()
        if scan:
            client.post(f'/api/projects/{project["id"]}/scans')
        if after_scan:
            sha = after_scan()
        body = {'question': question, 'source_context': source, **({'parent': parent} if parent else {})}
        stream = client.post(f'/api/projects/{project["id"]}/history/commits/{sha}/ask/stream', json=body)
        return [(block.split('\n')[0][len('event: '):], json.loads(block.split('\n')[1][len('data: '):]))
                for block in stream.text.strip().split('\n\n')]


def test_a_commit_question_starts_from_what_git_knows_then_minia_explores(repo, tmp_path):
    repo, sha = repo
    model = ScriptedModel(
        call('diff_facts', commit=sha), call('get_diff', commit=sha, path='src/app.txt'),
        answer(statement('claim', 'Le commit modifie src/app.txt.', f'commit:{sha}', 'CHANGES', 'file:src/app.txt'),
               statement('interpretation', 'Le contenu passerait de « un » à « deux ».')))
    result = completed(ask_commit(repo, tmp_path, model, sha, source=True))
    assert (result['mode'], result['commit'], result['source_context']) == ('exploration', sha, {'status': 'ON_DEMAND'})
    assert result['git']['sha'] == sha and result['git']['files'][0]['path'] == 'src/app.txt'
    operations = [step['operation'] for step in result['trajectory']]
    assert operations == ['describe', 'get_commit', 'diff_facts', 'get_diff', 'verify_claim']
    assert result['trajectory'][3]['outcome'] == 'OK', 'le diff est lisible sur double accord'
    assert result['statements'][0]['verdict'] == 'CONFIRMED'
    first = json.loads(model.calls[0][1])
    assert first['context'] == {'commit': f'commit:{sha}', 'parent': first['context']['parent'], 'diff_readable': True}
    assert [step['operation'] for step in first['trajectory']] == ['describe', 'get_commit']
    diff = json.loads(model.calls[2][1])['trajectory'][3]['response']
    assert diff['items'][0]['after'] == 'deux', 'Minia lit le bloc modifie, et rien d autre'


@pytest.mark.parametrize('source, setting', [(False, 'diff'), (True, 'off')])
def test_without_both_consents_the_diff_stays_closed(repo, tmp_path, source, setting):
    repo, sha = repo
    model = ScriptedModel(call('get_diff', commit=sha, path='src/app.txt'), answer(statement('unknown', 'Pas de diff.')))
    result = completed(ask_commit(repo, tmp_path, model, sha, source=source, setting=setting))
    assert result['trajectory'][2]['error']['code'] == 'NO_CONSENT'
    assert json.loads(model.calls[0][1])['context']['diff_readable'] is False


def test_a_commit_absent_from_the_last_analysis_falls_back_to_its_packet(repo, tmp_path, git):
    repo, _ = repo

    def newer_commit():
        (repo / 'src/new.txt').write_text('nouveau\n')
        git(repo, 'add', '-A')
        git(repo, 'commit', '-qm', 'après l analyse')
        return git(repo, 'rev-parse', 'HEAD')

    packet = json.dumps({'cited': [], 'answer': 'Un fichier aurait été ajouté.', 'unknown': ''})
    model = ScriptedModel(packet)
    result = completed(ask_commit(repo, tmp_path, model, after_scan=newer_commit))
    assert (result['mode'], result['answer']) == ('paquet', 'Un fichier aurait été ajouté.')
    assert result['fallback'].startswith('get_commit') and result['trajectory'][1]['error']['code'] == 'OUT_OF_SCOPE'
    assert len(model.calls) == 1 and model.calls[0][2] is None, 'Minia n est interrogee qu une fois, en paquet'


def test_the_other_side_of_a_merge_stays_in_the_packet(make_repo, git, tmp_path):
    repo = make_repo({'a.txt': 'a\n'}, 'fusion')
    main = git(repo, 'rev-parse', '--abbrev-ref', 'HEAD')
    git(repo, 'checkout', '-qb', 'side')
    (repo / 'b.txt').write_text('b\n')
    git(repo, 'add', '-A')
    git(repo, 'commit', '-qm', 'side')
    git(repo, 'checkout', '-q', main)
    (repo / 'c.txt').write_text('c\n')
    git(repo, 'add', '-A')
    git(repo, 'commit', '-qm', 'main')
    git(repo, 'merge', '-q', '--no-ff', 'side', '-m', 'fusion')
    merge, second = git(repo, 'rev-parse', 'HEAD'), git(repo, 'rev-parse', 'HEAD^2')
    model = ScriptedModel(json.dumps({'cited': [], 'answer': 'Fusion de side.', 'unknown': ''}))
    result = completed(ask_commit(repo, tmp_path, model, merge, parent=second))
    assert result['mode'] == 'paquet' and 'autre parent' in result['fallback'] and result['trajectory'] == []


def test_without_a_global_analysis_the_commit_question_keeps_its_packet(repo, tmp_path):
    repo, sha = repo
    model = ScriptedModel(json.dumps({'cited': [], 'answer': 'Un fichier aurait changé.', 'unknown': ''}))
    result = completed(ask_commit(repo, tmp_path, model, sha, scan=False))
    assert result['mode'] == 'paquet', 'le paquet compare les instantanes sans analyse globale'
    assert 'analyse globale' in result['fallback'] and result['trajectory'] == []


class NarrowModel(ScriptedModel):
    """Un fournisseur a petite fenetre : l'exploration s'y ajuste, et un depassement renvoie au paquet."""

    def __init__(self, *replies, room=30_000):
        super().__init__(*replies)
        self.room = room

    def capacity(self, system):
        return self.room - len(system.encode('utf-8'))

    def complete(self, system, user, schema=None):
        if len(user.encode('utf-8')) > self.capacity(system):
            self.calls.append((system, user, schema))
            raise MiniaError(CONTEXT_TOO_LARGE, 'trop grand')
        return super().complete(system, user, schema)


def test_the_exchange_budget_follows_the_window_of_the_model(repo, tmp_path):
    repo, _ = repo
    model = NarrowModel(answer(statement('unknown', 'Rien.')))
    result = completed(run(repo, tmp_path, model))
    capacity = model.capacity(exploration.SYSTEM)
    assert result['budget']['max_bytes'] == max(capacity - 4096, 16_240) < 64_000


def test_a_window_overflow_during_exploration_falls_back_to_the_packet(repo, tmp_path):
    repo, _ = repo
    packet = json.dumps({'cited': [], 'answer': 'Paquet.', 'unknown': ''})
    model = NarrowModel(packet, room=len(exploration.SYSTEM.encode('utf-8')) + 1000)
    result = completed(run(repo, tmp_path, model, 'Résume le dernier commit'))
    assert result['mode'] == 'paquet' and result['fallback'] == 'trop grand'
