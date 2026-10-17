"""Le chemin d'une route et ses tuiles de méthode (essai A/B validé par le Capitaine Pi, 2026-10-15).

A (`full`) : la carte et toutes les tuiles du chemin en une réponse. B (`map`) : la carte et la tuile d'entrée, puis les
tuiles demandées par numéro (`read_tiles`). Taxo fournit le graphe et le code, Minia orchestre, le modèle raisonne.
"""
import json

import pytest
from fastapi.testclient import TestClient

from app.bootstrap import settings
from app.bootstrap.database import Base
from app.main import create_app
from app.minia.application import paths
from app.protocol.domain.envelope import size
from app.minia.domain.exploration import Call
from test_minia_explore import answer, call, completed, statement
from test_minia_general import Scripted

ROOT = 'src/main/java/com/acme'
FILES = {
    'settings.gradle': "rootProject.name = 'shop'\n",
    'build.gradle': "plugins { id 'java' }\n",
    f'{ROOT}/web/ItemController.java': '''package com.acme.web;

import com.acme.model.Item;
import com.acme.service.ItemService;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/items")
public class ItemController {
    private final ItemService itemService;

    public ItemController(ItemService itemService) {
        this.itemService = itemService;
    }

    @PostMapping
    @PreAuthorize("hasRole('ADMIN')")
    public Item add(@RequestParam Long id) {
        return itemService.add(id);
    }
}
''',
    f'{ROOT}/service/ItemService.java': '''package com.acme.service;

import com.acme.model.Item;
import com.acme.repository.ItemRepository;
import org.springframework.stereotype.Service;

@Service
public class ItemService {
    private final ItemRepository itemRepository;

    public ItemService(ItemRepository itemRepository) {
        this.itemRepository = itemRepository;
    }

    public Item add(Long id) {
        return itemRepository.save(id);
    }
}
''',
    f'{ROOT}/repository/ItemRepository.java': '''package com.acme.repository;

import com.acme.model.Item;
import org.springframework.stereotype.Repository;

import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

@Repository
public class ItemRepository {
    private final Set<Item> items = ConcurrentHashMap.newKeySet();

    public Item save(Long id) {
        Item item = new Item(id);
        items.add(item);
        return item;
    }
}
''',
    f'{ROOT}/model/Item.java': 'package com.acme.model;\n\npublic record Item(Long id) {\n}\n',
}
ROUTE = 'endpoint:POST /api/items'
QUESTION = 'Que fait POST /api/items quand on ajoute deux fois le même article ?'


def run(make_repo, tmp_path, monkeypatch, model, mode, source=True):
    monkeypatch.setenv('MINIA_PATH_MODE', mode)
    root = make_repo(FILES)
    app = create_app(f'sqlite:///{tmp_path / "paths.db"}', [root], minia=model, source_reading='symbol')
    Base.metadata.create_all(app.state.engine)
    with TestClient(app) as client:
        project = client.post('/api/projects', json={'name': 'Boutique', 'path': str(root)}).json()
        client.post(f'/api/projects/{project["id"]}/scans')
        stream = client.post(f'/api/projects/{project["id"]}/ask/stream', json={'question': QUESTION, 'source': source})
        events = [(block.split('\n')[0][len('event: '):], json.loads(block.split('\n')[1][len('data: '):]))
                  for block in stream.text.strip().split('\n\n') if not block.startswith(':')]
    return completed(events)


def sent(model, turn):
    return json.loads(model.calls[turn][1])


def path_of(message):
    return next(item['response'] for item in message['trajectory'] if item['operation'] == paths.OPERATION)


CLAIM = statement('claim', 'POST /api/items est traité par ItemController.add.', ROUTE, 'HANDLED_BY',
                  'symbol:java:com.acme.web.ItemController#add(Long)')


# --- A : tout le chemin en une réponse, sans tour du modèle pour le trouver --------------------------------------

def test_a_the_route_of_the_question_brings_its_whole_path_before_the_first_turn(make_repo, tmp_path, monkeypatch):
    model = Scripted(answer(CLAIM))
    result = run(make_repo, tmp_path, monkeypatch, model, 'full')
    assert len(model.calls) == 1, 'le modèle n’a rien à chercher : il répond au premier tour'
    path = path_of(sent(model, 0))
    names = [entry['name'] for entry in path['map']]
    assert names == ['ItemController.add(Long)', 'ItemService.add(Long)', 'ItemRepository.save(Long)']
    assert [tile['number'] for tile in path['tiles']] == [1, 2, 3]
    assert path['to_read'] == []
    first, _, last = path['tiles']
    assert '@PreAuthorize("hasRole(\'ADMIN\')")' in first['code'], 'la méthode complète, avec ses annotations'
    assert '@RequestMapping("/api/items")' in first['class']['text'], 'les annotations de sa classe'
    assert last['fields'] == ['private final Set<Item> items = ConcurrentHashMap.newKeySet();'], 'les champs utilisés'
    assert 'Item item = new Item(id);' in last['code'], 'ses variables locales, dans son code'
    item = next(entry for tile in path['tiles'] for entry in tile.get('types', ())
                if entry['reference'] == 'symbol:java:com.acme.model.Item')
    assert item['text'].startswith('public record Item(Long id)')
    assert item['resolution'] == 'NAMED'
    assert result['statements'][0]['found'] is True, 'la vérification lit toujours Taxo'
    operation = next(step for step in result['trajectory'] if step['operation'] == paths.OPERATION)
    assert operation['outcome'] == 'OK'
    assert operation['bytes'] > 0, 'le chemin compte comme une opération'


def test_a_a_class_or_type_already_given_is_never_given_twice(make_repo, tmp_path, monkeypatch):
    model = Scripted(answer(CLAIM))
    run(make_repo, tmp_path, monkeypatch, model, 'full')
    path = path_of(sent(model, 0))
    given = [tile['class']['reference'] for tile in path['tiles'] if 'class' in tile]
    given += [entry['reference'] for tile in path['tiles'] for entry in tile.get('types', ())]
    assert len(given) == len(set(given))


# --- B : la carte, puis les tuiles demandées par numéro ----------------------------------------------------------

def test_b_the_map_comes_with_the_entry_tile_and_the_model_reads_the_others_by_number(make_repo, tmp_path, monkeypatch):
    model = Scripted(call(paths.READ, numbers=[2, 3, 9]), answer(CLAIM))
    result = run(make_repo, tmp_path, monkeypatch, model, 'map')
    path = path_of(sent(model, 0))
    assert len(path['map']) == 3
    assert [tile['number'] for tile in path['tiles']] == [1]
    read = sent(model, 1)['trajectory'][-1]['response']
    assert [tile['number'] for tile in read['tiles']] == [2, 3]
    assert read['not_sent'] == [{'what': 'tiles', 'numbers': [9], 'reason': 'UNKNOWN_NUMBER'}], \
        'un numéro inconnu est refusé et dit'
    assert 'items.add(item);' in read['tiles'][1]['code']
    assert [step['operation'] for step in result['trajectory']].count(paths.READ) == 1, 'un lot, une opération'


def test_b_read_tiles_without_a_map_is_refused():
    exchange = type('Exchange', (), {'snapshot': {'analysis': 'a', 'commit': None},
                                     'accounted': lambda self, serve, requested=None: serve(requested)})()
    response = paths.request(exchange, Call(paths.READ, {'numbers': [1]}), None, [], paths.MAP)
    assert response['outcome'] == 'ERROR'
    assert 'get_path' in response['error']['message']


# --- Consentement, références, budget, garde -------------------------------------------------------------------------

def test_without_consent_the_map_is_served_and_no_code_is_sent(make_repo, tmp_path, monkeypatch):
    model = Scripted(answer(CLAIM))
    run(make_repo, tmp_path, monkeypatch, model, 'full', source=False)
    path = path_of(sent(model, 0))
    assert path['tiles'] == []
    assert path['not_sent'] == [{'what': 'tiles', 'numbers': [1, 2, 3], 'reason': 'NO_CONSENT'}]
    assert 'items.add' not in model.calls[0][1], 'aucun code ne part sans accord'


def test_the_model_cannot_ask_the_path_of_a_reference_it_never_received(make_repo, tmp_path, monkeypatch):
    model = Scripted(call(paths.OPERATION, reference='endpoint:GET /api/inventee'), answer(CLAIM))
    result = run(make_repo, tmp_path, monkeypatch, model, 'map')
    refused = [step for step in result['trajectory'] if step['operation'] == paths.OPERATION][-1]
    assert refused['outcome'] == 'ERROR'


def test_what_does_not_fit_the_budget_is_said_never_dropped(make_repo, tmp_path, monkeypatch):
    monkeypatch.setattr(paths, 'MAX_PATH_BYTES', 2_500)
    model = Scripted(answer(CLAIM))
    run(make_repo, tmp_path, monkeypatch, model, 'full')
    path = path_of(sent(model, 0))
    sent_numbers = [tile['number'] for tile in path['tiles']]
    budget = [item for item in path['not_sent'] if item['reason'] == 'BUDGET']
    assert budget
    assert sorted(sent_numbers + budget[0]['numbers']) == [1, 2, 3]
    assert path['to_read'] == budget[0]['numbers'], 'le modèle sait quelles tuiles lire ensuite'


def test_the_conclusion_guard_counts_the_tiles_as_code_read(make_repo, tmp_path, monkeypatch):
    unknown = statement('unknown', 'Je ne sais pas si ItemRepository rejette un doublon.')
    model = Scripted(answer(CLAIM, unknown))
    result = run(make_repo, tmp_path, monkeypatch, model, 'full')
    assert len(model.calls) == 1
    assert 'returned' not in result, 'le code d’ItemRepository a été lu par sa tuile'


# --- Réglage et non-régression ---------------------------------------------------------------------------------------

def test_without_the_setting_nothing_changes(make_repo, tmp_path, monkeypatch):
    model = Scripted(answer(CLAIM))
    run(make_repo, tmp_path, monkeypatch, model, 'off')
    message = sent(model, 0)
    assert paths.OPERATION not in {item['operation'] for item in message['operations']}
    assert all(item['operation'] != paths.OPERATION for item in message['trajectory'])


def test_the_setting_accepts_only_off_full_or_map(monkeypatch):
    monkeypatch.delenv('MINIA_PATH_MODE', raising=False)
    assert settings.minia_path_mode() == 'off'
    assert settings.minia_path_mode('MAP') == 'map'
    with pytest.raises(ValueError, match='MINIA_PATH_MODE'):
        settings.minia_path_mode('tout')


# --- Corrections de la revue du Sage : conservation, budget, compaction -----------------------------------------------

def _sent_types(path):
    return [tile['class']['reference'] for tile in path['tiles'] if 'class' in tile] + \
        [entry['reference'] for tile in path['tiles'] for entry in tile.get('types', ())]


@pytest.mark.parametrize('budget', [1_800, 2_300, 2_800, 3_400, 4_200])
def test_a_dropped_tile_takes_nothing_with_it_and_the_whole_response_fits(make_repo, tmp_path, monkeypatch, budget):
    monkeypatch.setattr(paths, 'MAX_PATH_BYTES', budget)
    model = Scripted(answer(CLAIM))
    run(make_repo, tmp_path, monkeypatch, model, 'full')
    path = path_of(sent(model, 0))
    assert path['bytes'] <= budget
    assert size(path) <= budget, \
        'la réponse entière, carte et signalements compris, tient dans le budget'
    given = _sent_types(path)
    for tile in path['tiles']:
        owner = tile['reference'].split('#', 1)[0]
        assert owner in given, f'la classe de la tuile {tile["number"]} est donnée, même si une tuile a été retirée'
    if any('Item(' in tile['code'] or 'Item ' in tile['code'] for tile in path['tiles']):
        assert 'symbol:java:com.acme.model.Item' in given, 'le type Item part avec une tuile retenue'
    assert len(given) == len(set(given))


def test_an_incomplete_path_is_announced_with_its_missing_methods(make_repo, tmp_path, monkeypatch):
    monkeypatch.setattr(paths, 'MAX_PATH_BYTES', 2_500)
    model = Scripted(answer(CLAIM))
    run(make_repo, tmp_path, monkeypatch, model, 'full')
    path = path_of(sent(model, 0))
    assert path['all_tiles_sent'] is False
    assert path['to_read']
    assert all(f'#{number}' in path['incomplete'] for number in path['to_read'])


def test_a_path_with_all_its_tiles_says_so(make_repo, tmp_path, monkeypatch):
    model = Scripted(answer(CLAIM))
    run(make_repo, tmp_path, monkeypatch, model, 'full')
    path = path_of(sent(model, 0))
    assert path['all_tiles_sent'] is True
    assert 'incomplete' not in path
    assert 'limits' not in path, 'rien de tronqué, aucun en-tête manquant, aucun appel non suivi'


def test_an_unavailable_header_is_said_never_silent(make_repo, tmp_path, monkeypatch):
    header = paths._header
    monkeypatch.setattr(paths, '_header', lambda exchange, reference, headers: None
                        if reference.endswith('.Item') or reference.endswith('.ItemService') else
                        header(exchange, reference, headers))
    model = Scripted(answer(CLAIM))
    run(make_repo, tmp_path, monkeypatch, model, 'full')
    path = path_of(sent(model, 0))
    said = {(item['what'], item['reference']) for item in path['not_sent'] if item.get('reason') == 'NOT_AVAILABLE'}
    assert ('class_header', 'symbol:java:com.acme.service.ItemService') in said
    assert ('type_header', 'symbol:java:com.acme.model.Item') in said


def test_compaction_keeps_the_path_and_its_tiles_whole():
    from app.minia.application import ask
    tile = {'number': 1, 'reference': 'symbol:java:a.B#c()', 'code': 'void c() {}'}
    exchanged = [{'operation': name, 'arguments': {}, 'response': {'outcome': 'OK', 'tiles': [tile]}}
                 for name in (paths.OPERATION, paths.READ)]
    exchanged += [{'operation': 'find_references', 'arguments': {}, 'response': {'outcome': 'OK', 'items': []}}] * 3
    shown = ask._compacted(exchanged, keep=1)
    assert shown[0] is exchanged[0]
    assert shown[1] is exchanged[1], 'le code du chemin n’est jamais résumé'


def test_all_tiles_sent_does_not_hide_the_other_limits(make_repo, tmp_path, monkeypatch):
    header = paths._header
    monkeypatch.setattr(paths, '_header', lambda exchange, reference, headers: None
                        if reference.endswith('.Item') else header(exchange, reference, headers))
    model = Scripted(answer(CLAIM))
    run(make_repo, tmp_path, monkeypatch, model, 'full')
    path = path_of(sent(model, 0))
    assert path['all_tiles_sent'] is True
    assert path['limits'] == {'unavailable_headers': ['symbol:java:com.acme.model.Item']}


def test_b_the_tiles_left_to_read_are_announced_as_such(make_repo, tmp_path, monkeypatch):
    model = Scripted(answer(CLAIM))
    run(make_repo, tmp_path, monkeypatch, model, 'map')
    path = path_of(sent(model, 0))
    assert path['not_sent'] == []
    assert path['to_read'] == [2, 3]
    assert 'méthodes #2, #3 à lire avec read_tiles(numbers)' in path['incomplete']
    assert 'not_sent' not in path['incomplete'], 'aucune raison à chercher là où il n’y en a pas'


class _Facts:
    snapshot = {'analysis': 'a', 'commit': 'c1'}

    def __init__(self, chain, rules=()):
        self.chain, self.rules = chain, list(rules)

    def query(self, kind, subject=None, relation=None):
        if kind != 'ASSERTION':
            return []
        if subject == 'endpoint:GET /x' and relation == 'HANDLED_BY':
            return [{'object': 'symbol:java:a.B#c()'}]
        if subject == 'endpoint:GET /x' and relation == 'MATCHED_BY':
            return [self.chain]
        if subject == '/x' and relation is None:
            return self.rules
        return []


def _matched(**change):
    fact = {'relation': 'MATCHED_BY', 'object': '/x', 'status': 'INFERRED', 'validity': 'VALID',
            'qualifiers': {'filter_chain': 'symbol:java:a.Security#filterChain(HttpSecurity)'},
            'produced_by': {'producer_id': 'taxo.spring-security'}, 'snapshot': {'commit': 'c1'}}
    return {**fact, **change}


@pytest.mark.parametrize('fact', [
    _matched(produced_by={'producer_id': 'autre'}),
    _matched(snapshot={'commit': 'ancien'}),
    _matched(status='HYPOTHESIS'),
    _matched(qualifiers={'filter_chain': 'pas une méthode'}),
    _matched(qualifiers={'filter_chain': ['liste']}),
])
def test_a_filter_chain_opens_code_only_once_validated(fact):
    order, _, chains, rules, _ = paths.walk(_Facts(fact), 'endpoint:GET /x')
    assert chains == []
    assert order == ['symbol:java:a.B#c()']
    assert rules == [], 'un rattachement non validé ne porte aucune règle'


def test_a_validated_filter_chain_joins_the_path():
    order, _, chains, _, _ = paths.walk(_Facts(_matched()), 'endpoint:GET /x')
    assert chains == ['symbol:java:a.Security#filterChain(HttpSecurity)']
    assert order[-1] == chains[0]


def test_calls_left_never_exceeds_what_the_exchange_can_still_serve(make_repo, tmp_path, monkeypatch):
    from app.protocol.application import exchange
    monkeypatch.setattr(exchange, 'MAX_OPERATIONS', 4)
    model = Scripted(answer(CLAIM))
    run(make_repo, tmp_path, monkeypatch, model, 'full')
    message = sent(model, 0)
    assert message['calls_left'] <= 4 - len(message['trajectory'])


def _rule(relation, value='', **change):
    return _matched(relation=relation, object=value, status='OBSERVED', **change)


def test_the_rules_of_a_validated_chain_keep_public_access_and_roles():
    rules = [_rule('PERMITS_ALL'), _rule('AUTHORIZED_BY', 'role:ADMIN')]
    _, _, _, written, _ = paths.walk(_Facts(_matched(), rules), 'endpoint:GET /x')
    assert written == [{'pattern': '/x', 'filter_chain': 'symbol:java:a.Security#filterChain(HttpSecurity)',
                        'rules': ['PERMITS_ALL', 'AUTHORIZED_BY role:ADMIN']}], 'PERMITS_ALL valide n’est pas perdu'


def test_an_invalid_rule_never_matches_an_invalid_chain():
    rules = [_rule('AUTHORIZED_BY', 'role:ADMIN', produced_by={'producer_id': 'autre'})]
    _, _, _, written, _ = paths.walk(_Facts(_matched(produced_by={'producer_id': 'autre'}), rules), 'endpoint:GET /x')
    assert written == [], 'deux validations échouées ne font pas une correspondance'
    _, _, _, written, _ = paths.walk(_Facts(_matched(), rules), 'endpoint:GET /x')
    assert written[0]['rules'] == [], 'une règle d’un autre producteur ne part pas avec une chaîne validée'
