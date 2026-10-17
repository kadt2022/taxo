"""La cible B (MINIA_PATH_MODE=target) : le LLM désigne sa cible, Taxo calcule le parcours, Minia ne lui envoie que le
code (vision du Capitaine Pi, 2026-10-16). Aucun fait de Taxo ne part vers le LLM."""
import json

import pytest
from fastapi.testclient import TestClient

from app.bootstrap import settings
from app.bootstrap.database import Base
from app.main import create_app
from app.minia.application import paths
from test_minia_explore import answer, call, completed, statement
from test_minia_general import Scripted
from test_minia_paths import FILES, ROUTE

QUESTION = 'Que fait POST /api/items quand on ajoute deux fois le même article ?'
FACTS = ('HANDLED_BY', 'AUTHORIZED_BY', 'CALLS', 'MATCHED_BY', 'PERMITS_ALL')


def target(value):
    return json.dumps({'action': 'target', 'target': value})


def read(*numbers):
    return json.dumps({'action': 'read', 'numbers': list(numbers)})


def conclude(text='Le doublon est ajouté au Set ; Item est un record.'):
    return json.dumps({'action': 'answer', 'text': text})


NONE = json.dumps({'action': 'none'})


def run(make_repo, tmp_path, monkeypatch, model, source=True, question=QUESTION):
    monkeypatch.setenv('MINIA_PATH_MODE', 'target')
    root = make_repo(FILES)
    app = create_app(f'sqlite:///{tmp_path / "target.db"}', [root], minia=model, source_reading='symbol')
    Base.metadata.create_all(app.state.engine)
    with TestClient(app) as client:
        project = client.post('/api/projects', json={'name': 'Boutique', 'path': str(root)}).json()
        client.post(f'/api/projects/{project["id"]}/scans')
        stream = client.post(f'/api/projects/{project["id"]}/ask/stream', json={'question': question, 'source': source})
        events = [(block.split('\n')[0][len('event: '):], json.loads(block.split('\n')[1][len('data: '):]))
                  for block in stream.text.strip().split('\n\n') if not block.startswith(':')]
    return completed(events)


def sent(model, turn):
    """Le message d'un tour, en clair : la question, le menu et les réponses de Taxo (le JSON décodé)."""
    message = json.loads(model.calls[turn][1])
    return '\n'.join([message['question'], message['menu'], *(f"{t['asked']}\n{t['taxo']}" for t in message['turns'])])


# --- Le dialogue : cible, parcours, code ------------------------------------------------------------------------------

def test_the_llm_names_a_route_and_receives_only_the_code_of_its_path(make_repo, tmp_path, monkeypatch):
    model = Scripted(target(ROUTE), conclude())
    result = run(make_repo, tmp_path, monkeypatch, model)
    first, second = sent(model, 0), sent(model, 1)
    assert 'Points de départ connus de Taxo' in first and f'- {ROUTE}' in first and QUESTION in first
    assert set(json.loads(model.calls[0][1])) == {'question', 'menu', 'turns', 'calls_left'}, 'ni describe ni opérations'
    assert '@RequestMapping("/api/items")' in second, 'la classe et ses annotations'
    assert '@PreAuthorize("hasRole(\'ADMIN\')")' in second, 'la méthode complète, annotations comprises'
    assert 'private final Set<Item> items = ConcurrentHashMap.newKeySet();' in second, 'les champs utilisés'
    assert 'public record Item(Long id)' in second, 'les types nécessaires'
    assert not any(fact in sent(model, turn) for turn in range(len(model.calls)) for fact in FACTS), 'aucun fait de Taxo'
    assert result['path_mode'] == 'target' and result['mode'] == 'exploration'
    assert result['statements'] == [{'type': 'interpretation', 'text': 'Le doublon est ajouté au Set ; Item est un record.'}]
    assert [step['operation'] for step in result['trajectory']] == [paths.OPERATION]


def test_a_method_named_without_route_is_resolved_by_taxo(make_repo, tmp_path, monkeypatch):
    model = Scripted(target('ItemRepository.save'), conclude())
    result = run(make_repo, tmp_path, monkeypatch, model, question='Comment ItemRepository enregistre-t-il un article ?')
    assert 'Parcours depuis ItemRepository.save(Long)' in sent(model, 1) and 'items.add(item);' in sent(model, 1)
    assert [step['operation'] for step in result['trajectory']] == ['find_references', paths.OPERATION]


def test_an_ambiguous_name_brings_candidates_and_the_llm_can_read_several(make_repo, tmp_path, monkeypatch):
    model = Scripted(target('add'), target('C1, C2'), conclude())
    result = run(make_repo, tmp_path, monkeypatch, model)
    assert 'C1 ItemController.add(Long)' in sent(model, 1) and 'C2 ItemService.add(Long)' in sent(model, 1)
    assert sent(model, 2).count('Parcours depuis') == 2
    assert [step['operation'] for step in result['trajectory']].count(paths.OPERATION) == 2


def test_an_unknown_name_is_said(make_repo, tmp_path, monkeypatch):
    model = Scripted(target('Facture'), target(ROUTE), conclude())
    run(make_repo, tmp_path, monkeypatch, model)
    assert 'Aucune référence connue de Taxo pour « Facture »' in sent(model, 1)


def test_a_question_without_code_goes_back_to_the_classic_exploration(make_repo, tmp_path, monkeypatch):
    model = Scripted(NONE, answer(statement('unknown', 'L’historique ne dit pas qui.')))
    result = run(make_repo, tmp_path, monkeypatch, model, question='Quelles parties du projet Taxo n’a-t-il pas analysées ?')
    assert 'operations' in json.loads(model.calls[1][1]), 'l’exploration classique reprend, avec ses opérations'
    assert result['trajectory'][0]['operation'] == 'describe'


# --- Budget, lecture, garde, consentement ------------------------------------------------------------------------------

def test_what_does_not_fit_is_listed_and_read_by_number(make_repo, tmp_path, monkeypatch):
    monkeypatch.setattr(paths, 'MAX_PATH_BYTES', 2_500)
    model = Scripted(target(ROUTE), read(2, 3), conclude())
    result = run(make_repo, tmp_path, monkeypatch, model)
    assert 'Code du parcours non encore transmis' in sent(model, 1) and 'action "read"' in sent(model, 1)
    assert 'items.add(item);' in sent(model, 2)
    assert [step['operation'] for step in result['trajectory']] == [paths.OPERATION, paths.READ]


def test_reading_before_any_map_is_refused(make_repo, tmp_path, monkeypatch):
    model = Scripted(read(1), target(ROUTE), conclude())
    run(make_repo, tmp_path, monkeypatch, model)
    assert 'Aucune carte reçue' in sent(model, 1)


def test_a_conclusion_without_the_direct_calls_is_returned_once(make_repo, tmp_path, monkeypatch):
    monkeypatch.setattr(paths, 'MAX_PATH_BYTES', 2_500)
    model = Scripted(target(ROUTE), conclude('Trop tôt.'), conclude('Je maintiens.'))
    result = run(make_repo, tmp_path, monkeypatch, model)
    assert 'Non lus : #2' in sent(model, 2), 'la méthode appelée par l’entrée n’a pas été lue'
    assert result['returned'] == ['#2']
    assert result['statements'][-1]['type'] == 'unknown' and '#2' in result['statements'][-1]['text']


def test_without_consent_the_map_goes_alone(make_repo, tmp_path, monkeypatch):
    model = Scripted(target(ROUTE), conclude('Sans code.'))
    result = run(make_repo, tmp_path, monkeypatch, model, source=False)
    assert 'Code non autorisé' in sent(model, 1) and 'items.add' not in sent(model, 1)
    assert 'returned' not in result, 'sans code lu, rien à rappeler'


def test_an_invalid_turn_falls_back_to_the_packet_mode(make_repo, tmp_path, monkeypatch):
    model = Scripted('pas du json', json.dumps({'cited': [], 'answer': 'Repli.', 'unknown': ''}))
    result = run(make_repo, tmp_path, monkeypatch, model)
    assert result['mode'] == 'paquet'


def test_the_setting_accepts_target(monkeypatch):
    assert settings.minia_path_mode('target') == 'target'
    with pytest.raises(ValueError, match='target'):
        settings.minia_path_mode('cible')


def test_the_guard_never_recalls_a_tile_without_readable_code():
    from app.minia.application import targeting
    path = {'outcome': 'OK', 'reference': 'endpoint:POST /api/courses', 'tiles': [{'number': 1}, {'number': 4}],
            'map': [{'number': 1, 'calls': [2, 3, 4]}, {'number': 2}, {'number': 3}, {'number': 4}],
            'not_sent': [{'what': 'tiles', 'numbers': [2], 'reason': 'NOT_AVAILABLE'},
                         {'what': 'tiles', 'numbers': [3], 'reason': 'BUDGET'}]}
    exchanged = [{'operation': paths.OPERATION, 'arguments': {}, 'response': path}]
    assert targeting.unread(exchanged) == [3], 'un accesseur implicite de record n’a pas de code ; le budget, si'


# --- La bascule vers l'exploration classique : continuité et traçabilité (autorisé par le Capitaine, 2026-10-16) ---

UNKNOWN_REPOSITORY = answer(statement('unknown', 'Je ne sais pas si ItemRepository rejette un doublon.'))


def test_the_switch_keeps_every_operation_in_its_real_order(make_repo, tmp_path, monkeypatch):
    model = Scripted(target('ItemRepository.save'), NONE, answer(statement('interpretation', 'Rien à lire de plus.')))
    result = run(make_repo, tmp_path, monkeypatch, model, question='Quelles parties du projet Taxo n’a-t-il pas analysées ?')
    operations = [step['operation'] for step in result['trajectory']]
    assert operations[:3] == ['find_references', paths.OPERATION, 'describe'], 'la phase cible B, puis l’exploration'


def test_what_the_llm_already_received_is_not_sent_again(make_repo, tmp_path, monkeypatch):
    model = Scripted(target(ROUTE), NONE, answer(statement('interpretation', 'Rien de plus.')))
    run(make_repo, tmp_path, monkeypatch, model, question='Quelles parties du projet Taxo n’a-t-il pas analysées ?')
    classic = json.loads(model.calls[2][1])
    assert [item['operation'] for item in classic['trajectory']] == ['describe'], 'le chemin n’est pas renvoyé'


def _find_repository(message):
    """L'exploration classique retrouve ItemRepository : la garde le connaît, lu ou non."""
    analysis = message['trajectory'][0]['response']['snapshot']['analysis']
    return call('find_references', analysis=analysis, prefix='ItemRepository', match='NAME')


def test_code_read_before_the_switch_counts_as_read_for_the_guard(make_repo, tmp_path, monkeypatch):
    model = Scripted(target(ROUTE), NONE, _find_repository, UNKNOWN_REPOSITORY)
    result = run(make_repo, tmp_path, monkeypatch, model)
    assert len(model.calls) == 4 and 'returned' not in result, 'la tuile d’ItemRepository a été lue avant la bascule'


def test_without_the_target_phase_the_same_conclusion_is_returned(make_repo, tmp_path, monkeypatch):
    model = Scripted(NONE, _find_repository, UNKNOWN_REPOSITORY, answer(statement('interpretation', 'Je maintiens.')))
    result = run(make_repo, tmp_path, monkeypatch, model)
    assert result['returned'], 'témoin : sans lecture préalable, la garde rappelle ItemRepository'


def test_a_tile_only_listed_on_the_map_is_not_counted_as_read(make_repo, tmp_path, monkeypatch):
    monkeypatch.setattr(paths, 'MAX_PATH_BYTES', 2_500)
    model = Scripted(target(ROUTE), NONE, UNKNOWN_REPOSITORY, answer(statement('interpretation', 'Je maintiens.')))
    result = run(make_repo, tmp_path, monkeypatch, model)
    sent_tiles = next(step for step in result['trajectory'] if step['operation'] == paths.OPERATION)
    assert any(item.get('reason') == 'BUDGET' for item in sent_tiles['not_sent']), 'ItemRepository n’est pas parti'
    assert result['returned'] == ['symbol:java:com.acme.repository.ItemRepository#save(Long)'], \
        'une méthode seulement proposée sur la carte n’est pas du code lu : la garde la rappelle'


def test_the_usage_counts_every_model_call_once(make_repo, tmp_path, monkeypatch):
    model = Scripted(target(ROUTE), NONE, answer(statement('interpretation', 'Rien de plus.')))
    result = run(make_repo, tmp_path, monkeypatch, model, question='Quelles parties du projet Taxo n’a-t-il pas analysées ?')
    assert result['usage']['calls'] == len(model.calls) == 3
    assert {step['operation'] for step in result['trajectory']} >= {paths.OPERATION, 'describe'}
    assert result['usage']['taxo_bytes'] == {'exploration': sum(step['bytes'] for step in result['trajectory']),
                                             'verification': 0}, 'les octets de Taxo des deux phases, une fois chacun'
