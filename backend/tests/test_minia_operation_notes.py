"""Les notes d'usage des opérations proposées à Minia (récit TAXO-MINIA-OPS-01).

Une note est du côté de Minia : `describe` et le protocole ne changent pas. Elle ne nomme que ce que Taxo publie déjà,
et leur somme reste bornée, parce que la liste des opérations repart à chaque tour du modèle.
"""
import re

from app.facts.domain.fact import RELATIONS
from app.minia.application import sources
from app.minia.domain import operation_notes
from app.minia.domain.operation_notes import MAX_NOTES_BYTES, NOTE, NOTES, noted
from app.protocol.application.exchange import OPERATIONS, _ARGUMENTS as DESCRIBED
from test_minia_explore import answer, statement
from test_minia_general import Scripted
from test_minia_source_reading import ask, sent

REFERENCE_TYPES = {kind for subjects, objects, _ in RELATIONS.values() for kind in (*subjects, *objects)}


def test_the_notes_stay_within_their_bound_so_a_long_guide_cannot_return_unnoticed():
    assert sum(len(note.encode('utf-8')) for note in NOTES.values()) <= MAX_NOTES_BYTES


def test_only_operations_of_the_protocol_carry_a_note():
    assert set(NOTES) <= set(OPERATIONS)


def test_a_note_names_only_relations_and_reference_types_that_taxo_publishes():
    for operation, note in NOTES.items():
        for relation in re.findall(r'\b[A-Z]{2,}(?:_[A-Z]+)+\b', note):
            assert relation in RELATIONS, f'{operation} : {relation}'
        for kind in ('endpoint', 'symbol'):
            if kind in note:
                assert kind in REFERENCE_TYPES


def test_a_noted_operation_keeps_what_describe_says_and_is_not_changed_in_place():
    item = {'kind': 'operation', 'operation': 'find_references', 'arguments': DESCRIBED['find_references']}
    seen = noted(item)
    assert seen == {**item, NOTE: NOTES['find_references']}
    assert NOTE not in item


def test_an_operation_without_a_known_note_is_left_as_described():
    item = {'kind': 'operation', 'operation': 'get_diff', 'arguments': DESCRIBED['get_diff']}
    assert noted(item) is item


def test_the_note_of_get_source_is_kept_as_it_was():
    item = sources.noted({'kind': 'operation', 'operation': 'get_source', 'arguments': DESCRIBED['get_source']})
    assert noted(item)[NOTE] == sources.NOTE


def test_minia_receives_each_operation_with_its_note_and_describe_is_unchanged(make_repo, tmp_path):
    model = Scripted(answer(statement('unknown', 'Rien à conclure.')))
    ask(make_repo, tmp_path, model)
    message = sent(model, 0)
    offered = {item['operation']: item for item in message['operations']}
    for operation in ('describe', 'find_references', 'get_neighborhood', 'find_facts', 'verify_claim'):
        assert offered[operation][NOTE] == operation_notes.NOTES[operation]
        assert offered[operation]['arguments'] == DESCRIBED[operation], 'les arguments restent ceux de describe'
    assert offered['get_source'][NOTE] == sources.NOTE
    assert 'ancre est le type de la référence' in offered['get_tile'][NOTE]
    described = message['trajectory'][0]['response']['items']
    assert all(NOTE not in item for item in described if item.get('kind') == 'operation'), \
        'la réponse de describe transmise reste celle de Taxo'
