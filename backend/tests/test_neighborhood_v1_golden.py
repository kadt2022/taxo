"""TAXO-01J : `neighborhood/1` ne change pas, à l'octet.

Les réponses de référence ont été capturées sur le moteur à un saut d'avant TAXO-01J (commit 2ae4431), avec
`TAXO_NEIGHBORHOOD_GOLDEN=write`. Le moteur multiniveau doit les rendre à l'identique, reprises comprises, sur
les deux stockages : toute requête valide pour `neighborhood/1` reste servie par `neighborhood/1`.

Une requête invalide pour les deux versions est refusée avec le motif de `neighborhood/2` (TAXO-01J, § 8,
règle 3) : son code ne change pas ; seuls les messages des valeurs dont le domaine s'élargit changent, et ils
sont écrits ici à la main.
"""
import json
import os
from pathlib import Path

import pytest

from test_neighborhood_conformance import ROOT, STORAGES, Twin, edge

GOLDEN = Path(__file__).parent / 'fixtures' / 'neighborhood_v1_golden.json'
WRITE = os.environ.get('TAXO_NEIGHBORHOOD_GOLDEN') == 'write'
HUB = 'module:hub'


def graph():
    """Un graphe générique : priorités, boucle sur l'ancre, fort degré, entrant, occurrences multiples, gros fait."""
    facts = [edge('module:z'), edge(ROOT), edge('module:a'), edge('module:b', 'CONTAINS'),
             edge('module:a', line=7),  # une seconde occurrence de la même identité, preuve différente
             edge('module:big', qualifiers={'label': 'x' * 5000}),
             edge('module:a', subject='module:other')]
    facts += [edge(f'module:n{index:02}', subject=HUB) for index in reversed(range(30))]
    facts += [edge(HUB, 'CONTAINS', subject=f'module:p{index}') for index in range(5)]
    return facts


def requests():
    """(nom, arguments, pages au plus) : chaque reprise suit le jeton de la page précédente."""
    both = {'follow': ['CONTAINS', 'DEPENDS_ON']}
    return [
        ('defaults', {}, 1),
        ('priority', {**both, 'priority': ['DEPENDS_ON', 'CONTAINS']}, 1),
        ('edges_paged', {'max_edges': 2}, 8),
        ('nodes_cut', {'max_nodes': 2}, 8),
        ('work_cut', {**both, 'max_work': 1}, 12),
        ('bytes_cut', {'max_bytes': 4500}, 6),
        ('hub_paged', {'root': HUB, 'max_edges': 7, 'max_work': 9}, 8),
        ('incoming', {'root': 'module:a', 'direction': 'INCOMING'}, 1),
        ('incoming_hub', {'root': HUB, 'direction': 'INCOMING', 'follow': ['CONTAINS'], 'max_edges': 2}, 5),
        ('unknown_root', {'root': 'module:missing'}, 1),
        ('context', {'follow': ['CALLS', 'DEPENDS_ON']}, 1),
        ('empty_covered', {'follow': ['CONTAINS'], 'root': 'module:z'}, 1),
        ('envelope_too_small', {'max_bytes': 100}, 1),
        ('explicit_v1_values', {'depth': 1, 'max_nodes': 200, 'max_edges': 200, 'max_work': 1000}, 1),
    ]


# Les messages qui changent, et seulement eux : le domaine accepté par `neighborhood/2` est plus large.
WIDENED = {5: 'direction : INCOMING, OUTGOING ou BOTH.', 6: 'depth doit être un entier entre 1 et 4.',
           7: 'depth doit être un entier entre 1 et 4.', 8: 'max_work doit être un entier entre 1 et 2000.'}
ERRORS = [{'follow': []}, {'follow': ['NO_RELATION']}, {'follow': ['CALLS', 'CALLS']}, {'priority': ['CONTAINS']},
          {'priority': [{}]}, {'direction': 'SIDEWAYS'}, {'depth': 0}, {'depth': True}, {'max_work': 0},
          {'max_nodes': -1}, {'continuation': 'invalid'}, {'extra': 1}, {'analysis': 'analysis-2'},
          {'root': 'not a reference'}]


def observed(twin, name):
    found = {}
    for label, arguments, limit in requests():
        found[label] = [[page, proofs] for page, proofs in twin.pages(name, limit=limit, **arguments)]
    found['errors'] = [twin.ask(twin.exchange(name), **arguments) for arguments in ERRORS]
    with_gap = dict(twin.evaluation)
    twin.evaluation = {**with_gap, 'coverage': [*with_gap['coverage'],
                                                 {'coverage_type': 'NOT_INTERPRETED', 'count': 3, 'subjects': ['file:x']}]}
    found['knowledge'] = twin.ask(twin.exchange(name))
    twin.evaluation = with_gap
    return found


@pytest.mark.parametrize('name', STORAGES)
def test_neighborhood_v1_is_unchanged(tmp_path, name):
    twin = Twin(tmp_path)
    twin.add(graph())
    found = json.loads(json.dumps(observed(twin, name)))
    if WRITE:
        recorded = json.loads(GOLDEN.read_text()) if GOLDEN.exists() else {}
        recorded[name] = found
        GOLDEN.parent.mkdir(exist_ok=True)
        GOLDEN.write_text(json.dumps(recorded, ensure_ascii=False, indent=1, sort_keys=True) + '\n')
    expected = json.loads(GOLDEN.read_text())[name]
    assert sorted(found) == sorted(expected)
    for label in expected:
        if label != 'errors':
            assert found[label] == expected[label], label
    for index, (refused, recorded) in enumerate(zip(found['errors'], expected['errors'], strict=True)):
        assert refused['error']['code'] == recorded['error']['code'], ERRORS[index]
        assert refused['error']['message'] == WIDENED.get(index, recorded['error']['message']), ERRORS[index]
