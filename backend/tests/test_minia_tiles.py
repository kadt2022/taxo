"""Minia demande des Tuiles adaptatives en exploration, sans jamais recevoir de code (TAXO-MIP-ADT-01, PR C).

La vérité est celle du dépôt scénarisé des appels Java (`test_java_calls.fixture_files`) :
`CourseController#register(String)` appelle `CourseService#register(String)`.
"""
import json

from fastapi.testclient import TestClient

from app.bootstrap.database import Base
from app.main import create_app
from test_java_calls import fixture_files
from test_minia_explore import answer, call, completed, statement
from test_minia_general import REGISTER, SERVICE, Scripted, analysis_of

QUESTION = 'Que fait CourseController.register ?'


def ask(make_repo, tmp_path, model, source_reading=None):
    root = make_repo(fixture_files())
    app = create_app(f'sqlite:///{tmp_path / "tiles.db"}', [root], minia=model, source_reading=source_reading)
    Base.metadata.create_all(app.state.engine)
    with TestClient(app) as client:
        project = client.post('/api/projects', json={'name': 'Cours', 'path': str(root)}).json()
        client.post(f'/api/projects/{project["id"]}/scans')
        stream = client.post(f'/api/projects/{project["id"]}/ask/stream', json={'question': QUESTION})
        events = [(block.split('\n')[0][len('event: '):], json.loads(block.split('\n')[1][len('data: '):]))
                  for block in stream.text.strip().split('\n\n') if not block.startswith(':')]
    return completed(events)


def sent(model, turn):
    return json.loads(model.calls[turn][1])


def test_minia_reads_a_method_through_its_declared_profile_on_the_same_analysis(make_repo, tmp_path):
    """D1, D2, D4 : une référence reçue, puis sa Tuile `method-context/1` ; la Tuile garde sa provenance et sa
    classification, et l'affirmation de Minia est vérifiée par Taxo."""
    model = Scripted(
        lambda message: call('find_references', analysis=analysis_of(message), prefix='CourseController.register',
                             match='NAME'),
        call('get_tile', reference=REGISTER, profile='method-context/1'),
        answer(statement('claim', 'CourseController#register appelle CourseService#register.', REGISTER, 'CALLS',
                         SERVICE)))
    result = ask(make_repo, tmp_path, model)
    assert [step['operation'] for step in result['trajectory']] == [
        'describe', 'find_references', 'get_tile', 'verify_claim']
    tile = sent(model, 2)['trajectory'][2]['response']
    assert tile['outcome'] == 'OK' and tile['profile']['id'] == 'method-context/1'
    assert tile['snapshot']['analysis'] == analysis_of(sent(model, 0)), 'la même analyse que l’échange'
    assert (REGISTER, 'CALLS', SERVICE, 'callees') in [
        (item['fact']['subject'], item['fact']['relation'], item['fact']['object'], item['selection']['rule'])
        for item in tile['facts']]
    assert tile['classification']['profile'] == 'method-context/1'
    assert 'CODE_SOURCE' not in tile['classification']['content']
    assert result['trajectory'][2]['items'] == len(tile['facts']) and result['trajectory'][2]['bytes'] > 0
    assert result['statements'][0]['verdict'] == 'CONFIRMED'


def test_the_tile_is_offered_and_the_source_never_is_even_when_the_server_allows_it(make_repo, tmp_path):
    """Seules les capacités activées pour cet échange sont proposées : Minia n'ouvre jamais un échange qui autorise
    le code, et une demande de `get_source` est refusée sans rien lire."""
    model = Scripted(call('get_source', reference=REGISTER),
                     answer(statement('unknown', 'Le code n’est pas disponible.')))
    result = ask(make_repo, tmp_path, model, source_reading='symbol')
    offered = [item['operation'] for item in sent(model, 0)['operations']]
    assert 'get_tile' in offered and 'get_source' not in offered
    refused = result['trajectory'][1]
    assert (refused['operation'], refused['error']['code']) == ('get_source', 'NO_CONSENT')
    assert 'this.courseService.register(name)' not in json.dumps(model.calls), 'aucune ligne du code transmise'


def test_a_refused_tile_is_said_and_the_exploration_goes_on(make_repo, tmp_path):
    """D5 : un profil dont l'ancre n'a pas le type de la référence, ou un argument inconnu, est refusé tel quel."""
    model = Scripted(
        call('get_tile', reference=REGISTER, profile='security/1'),
        call('get_tile', reference=REGISTER, profile='method-context/1', depth=3),
        answer(statement('unknown', 'Aucune Tuile servie.')))
    result = ask(make_repo, tmp_path, model)
    wrong_anchor, unknown_argument = result['trajectory'][1:3]
    assert wrong_anchor['error']['code'] == 'INVALID_ARGUMENT' and 'endpoint' in wrong_anchor['error']['message']
    assert unknown_argument['error'] == {'code': 'INVALID_ARGUMENT', 'message': 'Argument inconnu : depth.'}
    assert result['mode'] == 'exploration' and result['statements'][0]['type'] == 'unknown'
