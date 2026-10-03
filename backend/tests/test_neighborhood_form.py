"""TAXO-01J, tranche F : la forme compacte est la même réponse, écrite autrement.

`expand` est l'inverse, écrit ici à partir du contrat, sans une ligne du module de forme : la forme complète
doit en sortir à l'identique, pour toute Tuile (coupures, reprises, sens combiné, éventail, preuves résumées,
plusieurs producteurs). Le gain est mesuré, pas promis.
"""
import copy

import pytest

from app.facts.domain.provenance import ProducerExecution
from app.protocol.domain.envelope import size
from test_neighborhood_conformance import STORAGES, Twin, edge

A, B, C, D = (f'module:{name}' for name in 'abcd')
V2 = {'engine': 'neighborhood/2'}
OTHER = ProducerExecution('EVALUATOR', 'other', '2.0.0', 'run-2', 'other-rules', '1')


def expand(envelope):
    """La forme complète d'une Tuile compacte, d'après le contrat seul."""
    full = copy.deepcopy(envelope)
    shared = full.pop('shared')
    nodes, steps = full['nodes'], full['parameters']['steps']
    full['node_details'] = [{'reference': reference, **node} for reference, node in zip(nodes, full['node_details'])]
    for item in full['items']:
        item['fact'] = {**item['fact'], **shared['common'][item.pop('common')]}
        step = steps[item['via']['step']]
        item['via'] = {'from': nodes[item['via']['from']], **step}
    return full


def comparable(envelope):
    """Ce qui doit être égal : tout, sauf la forme demandée et la taille, qui en dépend."""
    kept = copy.deepcopy(envelope)
    kept['parameters'].pop('form')
    kept.pop('bytes')
    for item in kept['items']:
        item['fact'] = dict(sorted(item['fact'].items()))
    return kept


@pytest.fixture
def twin(tmp_path):
    found = Twin(tmp_path)
    found.add([edge(B, subject=A), edge(C, subject=A), edge(D, subject=B), edge(D, subject=C), edge(A, subject=D),
               edge(A, subject=A)])
    store = found.stores['fact_memory']
    store.record_execution('analysis-1', OTHER)
    for name in STORAGES:
        found.stores[name].add('analysis-1', 'other', [edge(B, subject=A, line=9, produced_by=OTHER.produced_by()),
                                                       edge(C, subject=D, line=4, produced_by=OTHER.produced_by())])
    return found


def ask(twin, name, form, max_bytes=20_000, **arguments):
    shortcut = {} if 'steps' in arguments else {'follow': ['DEPENDS_ON'], 'direction': 'OUTGOING'}
    result = twin.exchange(name).call({'operation': 'get_neighborhood', 'max_bytes': max_bytes, 'arguments': {
        'analysis': 'analysis-1', 'root': A, **shortcut, **V2, 'form': form, **arguments}})
    assert result['outcome'] == 'OK', result
    assert result['bytes'] == size(result)
    return result


TILES = [
    {'depth': 1},
    {'depth': 3},
    {'depth': 4, 'follow': ['DEPENDS_ON'], 'direction': 'BOTH'},
    {'depth': 2, 'max_fanout': 1},
    {'depth': 3, 'max_edges': 3},
    {'depth': 3, 'evidence': 'SUMMARY'},
    {'depth': 2, 'steps': [{'relation': 'DEPENDS_ON', 'direction': 'INCOMING'},
                           {'relation': 'DEPENDS_ON', 'direction': 'OUTGOING'}]},
    {'root': 'module:absent', 'depth': 2},
]


@pytest.mark.parametrize('name', STORAGES)
@pytest.mark.parametrize('arguments', TILES)
def test_the_compact_form_expands_to_the_full_form_exactly(twin, name, arguments):
    full = ask(twin, name, 'FULL', **arguments)
    compact = ask(twin, name, 'COMPACT', **arguments)
    assert comparable(expand(compact)) == comparable(full)
    assert compact['parameters']['form'] == 'COMPACT'
    if full['items']:
        assert compact['bytes'] < full['bytes']


def test_the_compact_form_is_written_by_hand(twin):
    compact = ask(twin, 'fact_memory', 'COMPACT', depth=1)
    assert [node.get('reference') for node in compact['node_details']] == [None, None, None]
    assert compact['nodes'] == [A, B, C]
    common = compact['shared']['common']
    assert [entry['produced_by']['producer_id'] for entry in common] == ['fixture', 'other'], \
        'une entrée par combinaison commune, dans l’ordre de première apparition'
    assert all(entry['snapshot'] == common[0]['snapshot'] and entry['status'] == 'OBSERVED' for entry in common)
    assert [(item['fact'], item['common'], item['via']) for item in compact['items']] == [
        ({'subject': A, 'relation': 'DEPENDS_ON', 'object': A, 'qualifiers': {}}, 0, {'from': 0, 'step': 0}),
        ({'subject': A, 'relation': 'DEPENDS_ON', 'object': B, 'qualifiers': {}}, 1, {'from': 0, 'step': 0}),
        ({'subject': A, 'relation': 'DEPENDS_ON', 'object': B, 'qualifiers': {}}, 0, {'from': 0, 'step': 0}),
        ({'subject': A, 'relation': 'DEPENDS_ON', 'object': C, 'qualifiers': {}}, 0, {'from': 0, 'step': 0})]


@pytest.mark.parametrize('name', STORAGES)
def test_a_continuation_does_not_depend_on_the_form(twin, name):
    """La forme ne change pas la séquence : une reprise émise par une forme sert l'autre."""
    full = ask(twin, name, 'FULL', depth=3, max_edges=2)
    compact = ask(twin, name, 'COMPACT', depth=3, max_edges=2)
    assert full['continuation'] == compact['continuation']
    node = next(entry['node'] for entry in full['frontier'] if entry.get('continuation') == full['continuation'])
    resumed = ask(twin, name, 'COMPACT', root=node, depth=3, continuation=full['continuation'])
    assert comparable(expand(resumed)) == comparable(ask(twin, name, 'FULL', root=node, depth=3,
                                                         continuation=full['continuation']))


def test_a_budget_in_bytes_holds_more_of_the_same_sequence(tmp_path):
    """La mesure de la tranche F : un nœud de 300 voisins, une opération de 32 000 octets. La forme compacte
    rend un préfixe plus long de la même séquence."""
    twin = Twin(tmp_path)
    twin.add([edge(f'module:service-{index:03d}', subject=A) for index in range(300)])
    counts = {}
    for form in ('FULL', 'COMPACT'):
        result = ask(twin, 'fact_memory', form, max_bytes=32_000, max_edges=400, max_nodes=200)
        assert result['stop_reason'] == 'BYTES'
        assert result['bytes'] <= 32_000
        counts[form] = [item['fact']['object'] for item in result['items']]
    assert counts['COMPACT'][:len(counts['FULL'])] == counts['FULL']
    # Mesuré : 31 éléments en forme complète, 54 en forme compacte. Un garde-fou : la forme ne doit pas regresser.
    assert (len(counts['FULL']), len(counts['COMPACT'])) == (31, 54)
