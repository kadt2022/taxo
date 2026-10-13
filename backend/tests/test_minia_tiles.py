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
        'describe', 'find_references', 'get_tile', 'find_claim']
    tile = sent(model, 2)['trajectory'][2]['response']
    assert tile['bytes'] == len(json.dumps(tile, ensure_ascii=False, separators=(',', ':')).encode('utf-8'))
    assert result['budget']['used'] == sum(step['bytes'] for step in result['trajectory']), \
        'la Tuile est comptée dans le budget de l’échange'

    assert tile['outcome'] == 'OK' and tile['profile']['id'] == 'method-context/1'
    assert tile['snapshot']['analysis'] == analysis_of(sent(model, 0)), 'la même analyse que l’échange'
    assert (REGISTER, 'CALLS', SERVICE, 'callees') in [
        (item['fact']['subject'], item['fact']['relation'], item['fact']['object'], item['selection']['rule'])
        for item in tile['facts']]
    assert tile['classification']['profile'] == 'method-context/1'
    assert 'CODE_SOURCE' not in tile['classification']['content']
    assert result['trajectory'][2]['items'] == len(tile['facts']) and result['trajectory'][2]['bytes'] > 0
    assert result['statements'][0]['found'] is True


def test_a_fact_handle_of_the_tile_is_one_of_the_exchange(make_repo, tmp_path):
    """Les références courtes (`F…`) d'une Tuile sont celles de l'échange de Minia : `get_evidence` sur l'une d'elles
    rend la preuve de ce fait-là, jamais celle d'un autre."""
    def evidence_of_the_call(message):
        tile = message['trajectory'][2]['response']
        handle = next(item['ref'] for item in tile['facts'] if item['fact']['relation'] == 'CALLS')
        return call('get_evidence', fact=handle)

    model = Scripted(
        lambda message: call('find_references', analysis=analysis_of(message), prefix='CourseController.register',
                             match='NAME'),
        call('get_tile', reference=REGISTER, profile='method-context/1'),
        evidence_of_the_call,
        answer(statement('unknown', 'Preuve lue.')))
    result = ask(make_repo, tmp_path, model)
    evidence = sent(model, 3)['trajectory'][3]['response']
    assert evidence['outcome'] == 'OK', evidence
    assert result['trajectory'][3]['operation'] == 'get_evidence'
    tile = sent(model, 2)['trajectory'][2]['response']
    called = next(item for item in tile['facts'] if item['fact']['relation'] == 'CALLS')
    assert evidence['fact'] == called['ref'] and evidence['evidence']
    assert {proof['location']['symbol'] for proof in evidence['evidence']} == {REGISTER}


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
    """D5 : une référence jamais reçue de Taxo, un profil dont l'ancre n'a pas le type de la référence, ou un argument
    inconnu, sont refusés tels quels ; l'exploration continue."""
    model = Scripted(
        call('get_tile', reference=REGISTER, profile='method-context/1'),
        lambda message: call('find_references', analysis=analysis_of(message), prefix='CourseController.register',
                             match='NAME'),
        call('get_tile', reference=REGISTER, profile='security/1'),
        call('get_tile', reference=REGISTER, profile='method-context/1', depth=3),
        answer(statement('unknown', 'Aucune Tuile servie.')))
    result = ask(make_repo, tmp_path, model)
    guessed, _, wrong_anchor, unknown_argument = result['trajectory'][1:5]
    assert guessed['error']['code'] == 'INVALID_ARGUMENT' and 'reçue de Taxo' in guessed['error']['message']
    assert wrong_anchor['error']['code'] == 'INVALID_ARGUMENT' and 'endpoint' in wrong_anchor['error']['message']
    assert unknown_argument['error'] == {'code': 'INVALID_ARGUMENT', 'message': 'Argument inconnu : depth.'}
    assert result['mode'] == 'exploration' and result['statements'][0]['type'] == 'unknown'


def test_a_tile_question_naming_an_author_sends_no_identity_and_the_trajectory_keeps_no_secret(
        make_repo, git, tmp_path):
    """TAXO-MINIA-SEC-01 (E3, E4) : sur le chemin des Tuiles aussi, chaque charge reellement envoyee au fournisseur
    est protegee (auteur nomme dans la question, co-auteur, secret du depot) ; la trajectoire rendue au portail ne
    porte que les operations, leurs arguments et leurs issues, jamais le contenu des reponses."""
    name, email, secret = 'Ada Lovelace', 'ada@example.org', 'admin123'
    root = make_repo({**fixture_files(),
                      'src/main/resources/application.yml': f'spring:\n  datasource:\n    password: {secret}\n'})
    git(root, '-c', f'user.name={name}', '-c', f'user.email={email}', 'commit', '-q', '--allow-empty', '-m',
        'feat: inscription\n\nCo-authored-by: Bob Martin <bob@example.org>')
    model = Scripted(
        lambda message: call('find_references', analysis=analysis_of(message), prefix='CourseController.register',
                             match='NAME'),
        call('get_tile', reference=REGISTER, profile='method-context/1'),
        answer(statement('interpretation', 'personne-1 a écrit une méthode qui délègue au service.')))
    app = create_app(f'sqlite:///{tmp_path / "tiles.db"}', [root], minia=model)
    Base.metadata.create_all(app.state.engine)
    with TestClient(app) as client:
        project = client.post('/api/projects', json={'name': 'Cours', 'path': str(root)}).json()
        client.post(f'/api/projects/{project["id"]}/scans')
        stream = client.post(f'/api/projects/{project["id"]}/ask/stream',
                             json={'question': f'Que fait CourseController.register, écrit par {name} ?'})
    events = [(block.split('\n')[0][len('event: '):], json.loads(block.split('\n')[1][len('data: '):]))
              for block in stream.text.strip().split('\n\n') if not block.startswith(':')]
    result = completed(events)
    assert [step['operation'] for step in result['trajectory']] == ['describe', 'find_references', 'get_tile']
    assert result['trajectory'][2]['outcome'] == 'OK'
    for _, user, _ in model.calls:
        for forbidden in (name, 'Lovelace', email, 'bob@example.org', 'Bob Martin', secret):
            assert forbidden not in user, forbidden
    assert result['statements'][0]['text'] == f'{name} a écrit une méthode qui délègue au service.'
    assert result['withheld']['identities'] >= 1
    assert secret not in json.dumps(result['trajectory']) and 'response' not in json.dumps(result['trajectory'])
