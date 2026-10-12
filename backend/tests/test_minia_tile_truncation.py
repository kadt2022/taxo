"""Repli paquet : une Tuile coupée par un budget, ou non servie, n'est jamais prise pour une absence de faits.

Seule une Tuile lue en entier et vide dit « Taxo ne connaît aucun fait ». Une Tuile coupée avant le moindre fait, ou
refusée faute de place, rend `NOT_CONCLUDED`, sans appeler le modèle. Le budget d'une Tuile est ce qui reste, moins ce
qu'il faut aux suivantes, sans jamais dépasser le plafond du paquet.
"""
import json

import pytest
from fastapi.testclient import TestClient

from app.bootstrap.database import Base
from app.main import create_app
from app.minia.application import anchoring
from app.minia.domain import briefing
from app.protocol.domain.envelope import size
from test_java_calls import fixture_files
from test_minia_explore import completed
from test_minia_general import REGISTER, SERVICE, WHO_CALLS, Scripted

NO_FACT_FOUND = 'ne connaît aucun fait'
SECRET = 'hunter2-tile-secret'


@pytest.fixture(name='courses')
def courses_fixture(make_repo):
    return make_repo(fixture_files())


def fact(subject, relation, object_):
    return {'fact': {'subject': subject, 'relation': relation, 'object': object_, 'status': 'OBSERVED',
                     'validity': 'VALID'}, 'evidence': []}


def tile(facts=(), truncated=False, stop='ADJACENCY_COMPLETE', pad=0):
    """Une Tuile MIP à la forme que lisent le repli et le briefing ; `pad` en fixe la taille sérialisée."""
    rendered = {'outcome': 'OK', 'facts': list(facts), 'frontier': [], 'truncated': truncated, 'stop_reason': stop,
                'not_sent': [], 'snapshot': {'analysis': 'a1', 'commit': 'c1'}}
    if pad:
        rendered['pad'] = ''
        rendered['pad'] = 'x' * max(pad - size(rendered), 0)
    return rendered


def refusal(message='La Tuile MIP dépasse le budget d’octets : augmenter max_bytes.'):
    return {'outcome': 'ERROR', 'error': {'code': 'BUDGET_EXHAUSTED', 'message': message}}


class FakeMip:
    """Un service MIP scénarisé : une réponse par requête, la dernière répétée ; il garde ce qui lui est demandé."""

    def __init__(self, *tiles):
        self.tiles, self.queries = list(tiles), []

    def query(self, project_id, payload, exchange=None):
        self.queries.append(payload)
        return self.tiles.pop(0) if len(self.tiles) > 1 else self.tiles[0]


def run(courses, tmp_path, model, mip, question=WHO_CALLS):
    app = create_app(f'sqlite:///{tmp_path / "truncation.db"}', [courses], minia=model)
    Base.metadata.create_all(app.state.engine)
    with TestClient(app) as client:
        project = client.post('/api/projects', json={'name': 'Cours', 'path': str(courses)}).json()
        client.post(f'/api/projects/{project["id"]}/scans')
        app.state.minia.mip = mip
        stream = client.post(f'/api/projects/{project["id"]}/ask/stream', json={'question': question})
        events = [(block.split('\n')[0][len('event: '):], json.loads(block.split('\n')[1][len('data: '):]))
                  for block in stream.text.strip().split('\n\n') if not block.startswith(':')]
    return completed(events)


# --- Tuile vide réelle, Tuile tronquée -----------------------------------------------------------------------------

def test_a_really_empty_tile_read_in_full_says_taxo_knows_nothing(courses, tmp_path):
    model = Scripted(explores=False)
    result = run(courses, tmp_path, model, FakeMip(tile()))
    assert result['status'] == 'TAXO_KNOWS_NOTHING'
    assert NO_FACT_FOUND in result['unknown']
    assert model.calls == [], 'une Tuile vide n’a rien à faire interpréter'


def test_a_truncated_tile_without_a_fact_is_never_an_absence_of_facts(courses, tmp_path):
    model = Scripted(explores=False)
    result = run(courses, tmp_path, model, FakeMip(tile(truncated=True, stop='BYTES')))
    assert result['status'] == 'NOT_CONCLUDED'
    assert NO_FACT_FOUND not in result['unknown']
    assert 'coupée par un budget' in result['unknown']
    assert 'Ce n\'est pas une absence de faits' in result['unknown']
    assert model.calls == [], 'rien n’a été lu : aucun appel, donc rien d’envoyé'


def test_a_tile_whose_envelope_fills_the_whole_budget_is_not_an_absence(courses, tmp_path):
    """L'enveloppe (couverture, frontière) tient, mais plus un seul fait : la Tuile n'est pas vide, elle est coupée."""
    model = Scripted(explores=False)
    result = run(courses, tmp_path, model, FakeMip(tile(truncated=True, stop='BYTES', pad=9000)))
    assert result['status'] == 'NOT_CONCLUDED'
    assert NO_FACT_FOUND not in result['unknown']


def test_a_tile_refused_for_lack_of_room_is_not_an_absence_either(courses, tmp_path):
    model = Scripted(explores=False)
    result = run(courses, tmp_path, model, FakeMip(refusal()))
    assert result['status'] == 'NOT_CONCLUDED'
    assert 'n\'a pas pu être servie' in result['unknown']
    assert NO_FACT_FOUND not in result['unknown']
    assert model.calls == []


@pytest.mark.parametrize('capacity', [300, 800, 1500, 2500, 4000, 6000, 9000, 14000])
def test_with_the_real_engine_no_budget_ever_turns_existing_facts_into_an_absence(courses, tmp_path, capacity):
    """Sur le dépôt réel, la Tuile de `CourseService.register` a des faits : aucun budget, si petit soit-il, ne doit
    conclure « aucun fait ». Elle répond, ou dit qu'elle n'a pas pu conclure sans appeler le modèle."""
    from test_minia_general import ask
    model = Scripted(json.dumps({'cited': [], 'answer': 'Réponse.', 'unknown': ''}), explores=False,
                     capacity=capacity)
    result, _, _ = ask(courses, tmp_path, model, WHO_CALLS)
    assert result['status'] != 'TAXO_KNOWS_NOTHING', f'capacité {capacity} : des faits existent'
    if result['status'] == 'NOT_CONCLUDED':
        assert model.calls == []
    else:
        assert result['status'] == 'ANSWERED'


# --- Un fait servi par une Tuile survit au refus d'une autre ------------------------------------------------------

def test_a_tile_refused_after_another_keeps_the_facts_and_says_the_limit(courses, tmp_path, monkeypatch):
    monkeypatch.setattr(anchoring, 'MAX_RELATIONS', 2)
    served = tile([fact(REGISTER, 'CALLS', SERVICE)])
    model = Scripted(json.dumps({'cited': ['F1'], 'answer': 'Un appel.', 'unknown': ''}), explores=False)
    result = run(courses, tmp_path, model, FakeMip(served, refusal('plus de place')))
    assert result['status'] == 'ANSWERED', 'les faits de la première Tuile suffisent à répondre'
    sent = json.loads(model.calls[0][1])
    assert [(item['subject'], item['relation']) for item in sent['facts']] == [(REGISTER, 'CALLS')]
    assert any('n’a pas pu être servie : plus de place' in limit for limit in sent['not_interpreted'])


def test_no_secret_in_a_served_tile_reaches_the_model_when_the_next_tile_is_refused(courses, tmp_path, monkeypatch):
    monkeypatch.setattr(anchoring, 'MAX_RELATIONS', 2)
    served = tile([fact(REGISTER, 'CALLS', SERVICE), fact(SERVICE, 'CONFIGURED_BY', f'password={SECRET}')])
    model = Scripted(json.dumps({'cited': [], 'answer': 'Rien.', 'unknown': ''}), explores=False)
    result = run(courses, tmp_path, model, FakeMip(served, refusal()))
    assert result['status'] == 'ANSWERED'
    assert model.calls
    assert SECRET not in json.dumps(model.calls), 'le secret n’est pas transmis, même avec une Tuile refusée'


def test_a_not_concluded_answer_carries_no_value_from_the_tile(courses, tmp_path):
    cut = tile([fact(SERVICE, 'CONFIGURED_BY', f'password={SECRET}')], truncated=True, stop='BYTES')
    model = Scripted(explores=False, capacity=1)  # rien ne tient : aucun fait n'est transmis
    result = run(courses, tmp_path, model, FakeMip(cut))
    assert result['status'] == 'NOT_CONCLUDED'
    assert model.calls == []
    assert SECRET not in json.dumps(result)


# --- Le budget d'une Tuile : ce qui reste, moins ce qu'il faut aux suivantes --------------------------------------

class Described:
    """Un échange où `find_references` rend l'ancre et `describe` annonce `count` relations présentes."""

    def __init__(self, count):
        self.snapshot, self.count = {'analysis': 'a1'}, count

    def call(self, request):
        if request['operation'] == 'describe':
            return {'outcome': 'OK', 'items': [{'kind': 'relation', 'relation': f'R{index:02d}', 'count': 1}
                                               for index in range(self.count)]}
        return {'outcome': 'OK', 'items': [{'reference': 'symbol:java:a.Items#list()'}], 'next': None,
                'not_sent': []}


def anchored(count, mip, max_bytes=None):
    return anchoring.drained(anchoring.anchor(Described(count), mip, 'p', 'Que fait Items.list ?', [], max_bytes))


def test_the_first_tile_gets_what_remains_minus_what_the_next_one_needs():
    mip = FakeMip(tile(pad=9000), tile(pad=3000))
    found = anchored(20, mip)
    budgets = [query['bounds']['max_bytes'] for query in mip.queries]
    assert [len(query['relations']) for query in mip.queries] == [16, 4]
    assert budgets[0] == anchoring.MAX_TILE_BYTES - anchoring.MIN_TILE_BYTES, 'plus la moitié du plafond'
    assert budgets[1] == anchoring.MAX_TILE_BYTES - size(found.tiles[0]), 'ce que la première n’a pas dépensé'
    assert sum(size(item) for item in found.tiles) <= anchoring.MAX_TILE_BYTES


def test_the_budgets_never_exceed_the_ceiling_of_the_packet():
    mip = FakeMip(tile(pad=12000), tile(pad=3500))
    anchored(20, mip)
    spent = 0
    for query, answered in zip(mip.queries, (12000, 3500)):
        assert spent + query['bounds']['max_bytes'] <= anchoring.MAX_TILE_BYTES
        spent += answered


def test_a_small_window_shrinks_the_budgets_and_keeps_one_byte_at_least():
    mip = FakeMip(refusal())
    found = anchored(20, mip, max_bytes=1000)
    assert [query['bounds']['max_bytes'] for query in mip.queries] == [1], 'une seule Tuile demandée : refusée'
    assert found.refused
    assert not found.tiles
    assert not found.truncated


def test_a_served_tile_cut_by_a_budget_is_reported_as_truncated():
    mip = FakeMip(tile([fact(REGISTER, 'CALLS', SERVICE)], truncated=True, stop='BYTES'))
    found = anchored(3, mip)
    assert found.truncated
    assert found.refused is None
    brief = briefing.tile('Que fait Items.list ?', 'symbol:java:a.Items#list()', found.tiles)
    assert any('coupée par un budget (BYTES)' in limit for limit in brief.not_interpreted), 'dit au modèle'
