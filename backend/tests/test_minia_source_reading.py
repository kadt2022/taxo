"""Minia lit le code d'une méthode, sous le double consentement de `get_source` (TAXO-MIP-ADT-01, PR C2).

La vérité est écrite à la main dans les sources ci-dessous, sur le modèle de `student-course-demo` :
`StudentService#findStudents()` rend `studentRepository.findAll()`, et `StudentRepository#findAll()` est déclarée
dans les sources. Le modèle est scénarisé : ce qu'il reçoit est ce que Taxo sert réellement, jamais un extrait préparé.
"""
import json

from fastapi.testclient import TestClient

from app.bootstrap.database import Base
from app.main import create_app
from test_minia_explore import answer, call, completed, statement
from test_minia_general import Scripted, analysis_of

ROOT = 'src/main/java/com/example/demo/'
SERVICE = 'symbol:java:com.example.demo.service.StudentService'
FIND = f'{SERVICE}#findStudents()'
FIND_ALL = 'symbol:java:com.example.demo.repository.StudentRepository#findAll()'
BODY = '    public List<Student> findStudents() {\n        return studentRepository.findAll();\n    }'
QUESTION = 'Que fait StudentService.findStudents() ?'
FILES = {
    f'{ROOT}model/Student.java': 'package com.example.demo.model;\n\npublic class Student {\n}\n',
    f'{ROOT}repository/StudentRepository.java': '\n'.join([
        'package com.example.demo.repository;',
        '',
        'import com.example.demo.model.Student;',
        'import java.util.List;',
        '',
        'public class StudentRepository {',
        '    public List<Student> findAll() {',
        '        return List.of();',
        '    }',
        '}',
        '']),
    f'{ROOT}service/StudentService.java': '\n'.join([
        'package com.example.demo.service;',
        '',
        'import com.example.demo.model.Student;',
        'import com.example.demo.repository.StudentRepository;',
        'import java.util.List;',
        'import org.springframework.stereotype.Service;',
        '',
        '@Service',
        'public class StudentService {',
        '    private final StudentRepository studentRepository;',
        '',
        '    public StudentService(StudentRepository studentRepository) {',
        '        this.studentRepository = studentRepository;',
        '    }',
        '',
        BODY,
        '',
        '    public String connect() {',
        '        String password = "hunter2-in-code";',
        '        return password;',
        '    }',
        '}',
        '']),
}


def ask(make_repo, tmp_path, model, source=True, reading='symbol', mode='commit', question=QUESTION):
    root = make_repo(FILES)
    app = create_app(f'sqlite:///{tmp_path / "source.db"}', [root], minia=model, source_reading=reading)
    Base.metadata.create_all(app.state.engine)
    with TestClient(app) as client:
        project = client.post('/api/projects', json={'name': 'Cours', 'path': str(root)}).json()
        client.post(f'/api/projects/{project["id"]}/scans', params={'mode': mode})
        assert client.get('/api/minia/status').json()['source_reading'] == reading, 'la case suit le réglage'
        stream = client.post(f'/api/projects/{project["id"]}/ask/stream',
                             json={'question': question, 'source': source})
        events = [(block.split('\n')[0][len('event: '):], json.loads(block.split('\n')[1][len('data: '):]))
                  for block in stream.text.strip().split('\n\n') if not block.startswith(':')]
    return completed(events)


def sent(model, turn):
    return json.loads(model.calls[turn][1])


def found(message):
    return call('find_references', analysis=analysis_of(message), prefix='StudentService.findStudents', match='NAME')


def callee(message):
    """La méthode appelée, prise dans la Tuile reçue : jamais devinée par le scénario."""
    tile = message['trajectory'][2]['response']
    called = next(item['fact']['object'] for item in tile['facts'] if item['fact']['relation'] == 'CALLS')
    return call('get_source', reference=called)


def test_minia_reads_the_tile_then_the_code_then_the_code_of_the_called_method(make_repo, tmp_path):
    """La démonstration du récit : la Tuile de la méthode, son code exact, puis le code de la méthode qu'elle
    appelle, trouvée dans la Tuile. Chaque pièce garde sa propre classification ; la Tuile n'annonce pas de code."""
    model = Scripted(
        found,
        call('get_tile', reference=FIND, profile='method-context/1'),
        call('get_source', reference=FIND),
        callee,
        answer(statement('claim', 'findStudents appelle StudentRepository.findAll.', FIND, 'CALLS', FIND_ALL),
               statement('interpretation', 'findStudents rendrait la liste de tous les étudiants.')))
    result = ask(make_repo, tmp_path, model)
    assert [step['operation'] for step in result['trajectory']] == [
        'describe', 'find_references', 'get_tile', 'get_source', 'get_source', 'verify_claim']
    assert result['source_reading'] == {'status': 'ON_DEMAND'}
    offered = {item['operation']: item for item in sent(model, 0)['operations']}
    assert 'get_tile' in offered and 'commit de l’analyse' in offered['get_source']['note']
    tile = sent(model, 2)['trajectory'][2]['response']
    assert 'CODE_SOURCE' not in tile['classification']['content']
    piece = sent(model, 3)['trajectory'][3]['response']
    assert piece['outcome'] == 'OK' and piece['items'][0]['text'] == BODY
    assert 'CODE_SOURCE' in piece['classification']['content'] and piece['reference'] == FIND
    assert piece['commit'] == tile['snapshot']['commit'], 'le commit de l’analyse, pour la Tuile et la pièce'
    following = sent(model, 4)['trajectory'][4]['response']
    assert following['reference'] == FIND_ALL and 'return List.of();' in following['items'][0]['text']
    assert result['statements'][0]['verdict'] == 'CONFIRMED'
    assert result['statements'][1]['type'] == 'interpretation'


def test_a_secret_written_in_the_code_is_masked_before_the_model(make_repo, tmp_path):
    """Le code passe par la protection de la demande : la valeur d'un mot de passe écrit en dur ne sort pas."""
    model = Scripted(
        lambda message: call('find_references', analysis=analysis_of(message), prefix='StudentService.connect',
                             match='NAME'),
        call('get_source', reference=f'{SERVICE}#connect()'),
        answer(statement('unknown', 'Rien à conclure.')))
    ask(make_repo, tmp_path, model)
    message = model.calls[2][1]
    assert 'String password = \\"******\\"' in message or 'password = "******"' in message
    assert 'hunter2-in-code' not in json.dumps(model.calls)


def test_a_symbol_never_received_from_taxo_is_not_read(make_repo, tmp_path):
    """Une référence devinée est refusée sans lecture ; reçue ensuite par une recherche, elle est lue."""
    model = Scripted(
        call('get_source', reference=FIND),
        found,
        call('get_source', reference=FIND),
        answer(statement('unknown', 'Lu après la recherche.')))
    result = ask(make_repo, tmp_path, model)
    guessed, _, read = result['trajectory'][1:4]
    assert guessed['error']['code'] == 'INVALID_ARGUMENT' and 'reçu de Taxo' in guessed['error']['message']
    assert read['outcome'] == 'OK' and read['items'] == 1
    assert 'findAll' not in json.dumps(sent(model, 1)['trajectory'][1]), 'rien n’a été lu pour le refus'


def test_without_both_consents_the_code_is_never_offered_nor_read(make_repo, tmp_path):
    """Sans l'accord de la demande, ou avec l'accord mais sans le réglage du serveur, `get_source` n'est pas
    proposée et sa demande est refusée sans rien lire ; la réponse dit pourquoi."""
    for source, reading, status in ((False, 'symbol', 'NOT_REQUESTED'), (True, 'off', 'DISABLED')):
        model = Scripted(found, call('get_source', reference=FIND), answer(statement('unknown', 'Pas de code.')))
        (tmp_path / status).mkdir()
        result = ask(make_repo, tmp_path / status, model, source=source, reading=reading)
        assert result['source_reading'] == {'status': status}
        assert 'get_source' not in [item['operation'] for item in sent(model, 0)['operations']]
        assert result['trajectory'][2]['error']['code'] == 'NO_CONSENT'
        assert 'studentRepository.findAll()' not in json.dumps(model.calls)


def test_the_same_reading_twice_in_the_same_state_is_a_repetition(make_repo, tmp_path):
    """Seule une référence devenue reçue peut être redemandée : relire le même code n'apporte rien, l'exploration
    s'arrête comme pour toute opération répétée."""
    model = Scripted(found, call('get_source', reference=FIND), call('get_source', reference=FIND),
                     json.dumps({'cited': [], 'answer': '', 'unknown': 'Repli sur le paquet.'}))
    result = ask(make_repo, tmp_path, model)
    assert result['mode'] == 'paquet' and 'répétée' in result['fallback']
    assert result['source_reading'] == {'status': 'ON_DEMAND'}, 'le repli garde ce que la demande permettait'
    operations = [step['operation'] for step in result['trajectory']]
    assert operations[:3] == ['describe', 'find_references', 'get_source'] and operations.count('get_source') == 1


def test_a_working_tree_analysis_says_the_code_is_unavailable_and_never_offers_it(make_repo, tmp_path):
    """Les deux accords donnés, mais l'analyse est celle du dossier de travail : aucun commit à lire. La réponse ne
    prétend pas que Minia pouvait lire le code."""
    model = Scripted(found, call('get_source', reference=FIND), answer(statement('unknown', 'Pas de code.')))
    result = ask(make_repo, tmp_path, model, mode='working-tree')
    assert result['source_reading'] == {'status': 'UNAVAILABLE'}
    assert 'get_source' not in [item['operation'] for item in sent(model, 0)['operations']]
    assert result['trajectory'][2]['outcome'] == 'ERROR'
    assert 'studentRepository.findAll()' not in json.dumps(model.calls)


def test_a_symbol_written_in_the_code_read_is_not_a_received_reference():
    """Un symbole écrit dans le code d'une pièce (ou dans tout texte) n'ouvre pas sa lecture : seule une valeur rendue
    par Taxo comme référence compte, à l'identique."""
    from app.minia.application import sources
    hidden = f'{SERVICE}#secret()'
    piece = {'operation': 'get_source', 'arguments': {'reference': 'symbol:java:Ailleurs'}, 'response': {'reference': FIND, 'items': [
        {'reference': FIND, 'text': f'String next = "{hidden}";'}], 'message': hidden}}
    tile = {'operation': 'get_tile', 'response': {'facts': [{'fact': {'subject': FIND, 'object': FIND_ALL,
                                                                       'derivation': {'premises': [FIND_ALL]}}}]}}
    assert not sources.received(hidden, [piece, tile])
    assert sources.received(FIND, [piece]) and sources.received(FIND_ALL, [tile])
    assert not sources.received(FIND[:-2], [piece]), 'jamais un fragment de référence'
    echoed = {'operation': 'verify_claim', 'arguments': {'subject': hidden, 'relation': 'CALLS', 'object': FIND},
              'response': {
        'claim': {'subject': hidden, 'relation': 'CALLS', 'object': FIND}, 'verdict': 'NOT_PROVEN',
        'coverage': {'subject': hidden}, 'items': []}}
    assert not sources.received(hidden, [echoed]), 'une affirmation répétée par Taxo n’est pas une découverte'
    unknown = {'operation': 'get_neighborhood', 'arguments': {'root': hidden},
               'response': {'anchor': {'reference': hidden, 'known': False},
                            'boundaries': [{'nature': 'SELECTION', 'node': hidden}], 'items': []}}
    assert not sources.received(hidden, [unknown]), 'l’ancre d’un voisinage, même inconnue, est la demande répétée'
    known = {'operation': 'get_neighborhood', 'arguments': {'root': FIND},
             'response': {'anchor': {'reference': FIND, 'known': True}, 'items': []}}
    assert sources.received(FIND, [known]), 'une ancre demandée que Taxo reconnaît est reçue'
    searched = {'operation': 'find_references', 'arguments': {'prefix': FIND},
                'response': {'prefix': FIND, 'items': [{'reference': FIND, 'type': 'method'}]}}
    assert sources.received(FIND, [searched]), 'un résultat de recherche égal au préfixe demandé est reçu'
    fact = {'operation': 'find_facts', 'arguments': {'subject': FIND},
            'response': {'items': [{'ref': 'F1', 'fact': {'subject': FIND, 'relation': 'CALLS', 'object': FIND_ALL}}],
                         'evidence': [{'ref': 'P1', 'fact': 'F1'}]}}
    assert sources.received(FIND, [fact]), 'le sujet demandé d’un fait rendu par Taxo est reçu'


def test_a_model_that_does_not_explore_says_the_code_was_not_read(make_repo, tmp_path):
    """L'accord donné à un modèle en mode paquet seul : aucun code n'est lu, et la réponse le dit."""
    model = Scripted(json.dumps({'cited': [], 'answer': 'Rien.', 'unknown': ''}), explores=False)
    result = ask(make_repo, tmp_path, model)
    assert result['source_reading'] == {'status': 'UNAVAILABLE'}
    assert 'studentRepository.findAll()' not in json.dumps(model.calls)


def test_a_direct_answer_on_authors_says_the_code_was_not_read(make_repo, tmp_path):
    """Les auteurs d'une sélection de commits sont dits par Taxo sans modèle : l'accord donné n'y lit aucun code."""
    model = Scripted(json.dumps({'cited': [], 'answer': 'Rien.', 'unknown': ''}))
    result = ask(make_repo, tmp_path, model, question='Qui a écrit les 2 derniers commits ?')
    assert result['mode'] == 'taxo' and result['source_reading'] == {'status': 'UNAVAILABLE'}
    assert model.calls == []
