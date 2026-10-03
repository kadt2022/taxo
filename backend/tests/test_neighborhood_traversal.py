"""TAXO-01J : le parcours d'une Tuile, sans base de données ni protocole.

D'abord des cas dont la Tuile attendue est écrite à la main ; puis des propriétés vérifiées sur des graphes
générés (Hypothesis), contre l'oracle de `neighborhood_graphs`, qui ne partage aucune ligne avec le moteur.
"""
import json

import pytest
from hypothesis import HealthCheck, given, settings, strategies as st

from app.neighborhood.domain.frontier import BYTES, DEPTH, EDGES, FANOUT, NODES, NOT_REACHED, WORK, Position
from app.neighborhood.domain.request import Limits, Step, TileRequest
from app.neighborhood.domain.traversal import EnvelopeTooLarge, Traversal
from neighborhood_graphs import IN, OUT, Graph, reachable

A, B, C, D, E, F = (f'module:{name}' for name in 'abcdef')
DEP, HAS = 'DEPENDS_ON', 'CONTAINS'
WIDE = Limits(max_nodes=200, max_edges=400, max_work=2000)


def is_node(value):
    return isinstance(value, str) and value.startswith('module:')


def always(_tile):
    return True


def walk(graph, root=A, steps=((DEP, OUT),), depth=1, limits=WIDE, fanout=None, batched=True, gauge=always,
         start=None, capable=(DEP, HAS)):
    request = TileRequest(root, tuple(Step(*step) for step in steps), depth, limits, fanout, batched)
    return Traversal(request, graph, capable, gauge, is_node, start).run()


def edges(tile):
    return [(item.adjacent.fact['subject'], item.adjacent.fact['object']) for item in tile.elements]


def nodes(tile):
    return {node.reference: (node.level, node.parents, node.expanded) for node in tile.nodes}


# ——— Cas écrits à la main ———

def test_a_chain_is_walked_level_by_level_and_stops_at_the_requested_depth():
    graph = Graph([(A, DEP, B), (B, DEP, C), (C, DEP, D), (D, DEP, E), (E, DEP, F)])
    tile = walk(graph, depth=3)
    assert edges(tile) == [(A, B), (B, C), (C, D)]
    assert nodes(tile) == {A: (0, 0, True), B: (1, 1, True), C: (2, 1, True), D: (3, 1, False)}
    assert [(node.reference, reason) for node, reason in tile.unexpanded()] == [(D, DEPTH)]
    assert tile.stop is None


def test_a_cycle_and_a_loop_terminate_and_are_shown_as_revisits():
    graph = Graph([(A, DEP, A), (A, DEP, B), (B, DEP, C), (C, DEP, A)])
    tile = walk(graph, depth=4)
    assert edges(tile) == [(A, A), (A, B), (B, C), (C, A)]
    assert [item.revisit for item in tile.elements] == [True, False, False, True]
    assert nodes(tile) == {A: (0, 2, True), B: (1, 1, True), C: (2, 1, True)}


def test_a_diamond_gives_one_node_at_its_first_level_with_two_parents():
    graph = Graph([(A, DEP, B), (A, DEP, C), (B, DEP, D), (C, DEP, D)])
    tile = walk(graph, depth=3)
    assert edges(tile) == [(A, B), (A, C), (B, D), (C, D)]
    by_reference = {node.reference: node for node in tile.nodes}
    assert (by_reference[D].level, by_reference[D].parents, by_reference[D].discovered_by) == (2, 2, 2)


def test_parallel_links_and_repeated_occurrences_are_all_rendered():
    """Deux relations entre les mêmes nœuds, et deux occurrences d'un même fait : quatre éléments, jamais fusionnés."""
    graph = Graph([(A, DEP, B), (A, HAS, B), (A, DEP, B), (A, HAS, B)])
    tile = walk(graph, steps=((DEP, OUT), (HAS, OUT)))
    assert [item.adjacent.occurrence for item in tile.elements] == ['0', '2', '1', '3']
    assert [item.revisit for item in tile.elements] == [False, True, True, True]
    identities = [item.adjacent.identity for item in tile.elements]
    assert identities[0] == identities[1] != identities[2] == identities[3]


def test_both_directions_render_an_occurrence_reached_twice_only_once():
    graph = Graph([(A, DEP, A), (A, DEP, B), (C, DEP, A)])
    tile = walk(graph, steps=((DEP, OUT), (DEP, IN)))
    assert edges(tile) == [(A, A), (A, B), (C, A)]
    assert [tile.request.steps[item.step].direction for item in tile.elements] == [OUT, OUT, IN]


def test_an_incoming_step_keeps_the_real_orientation_of_each_fact():
    graph = Graph([(B, DEP, A), (C, DEP, B)])
    tile = walk(graph, steps=((DEP, IN),), depth=2)
    assert edges(tile) == [(B, A), (C, B)]
    assert [node.reference for node in tile.nodes] == [A, B, C]


def test_mixed_steps_follow_their_own_directions():
    graph = Graph([(A, DEP, B), (C, HAS, B), (B, DEP, D)])
    tile = walk(graph, steps=((DEP, OUT), (HAS, IN)), depth=2)
    assert edges(tile) == [(A, B), (B, D), (C, B)]


def test_a_global_budget_stops_at_the_first_refusal_and_never_skips():
    """Le budget de nœuds refuse b : la revisite qui la suit dans l'ordre stable (z → z), qui ne coûte aucun
    nœud, n'est pas rendue pour autant."""
    root = 'module:z'
    graph = Graph([(root, DEP, root), (root, DEP, B)])
    tile = walk(graph, root=root, limits=Limits(1, 400, 2000))
    assert tile.elements == ()
    assert (tile.stop.reason, tile.stop.found, tile.stop.position) == (NODES, True, Position(root, 0, ''))
    assert edges(walk(graph, root=root)) == [(root, B), (root, root)]


def test_the_element_budget_cut_says_at_least_one_only_when_an_unrendered_occurrence_was_read():
    graph = Graph([(A, DEP, B), (A, DEP, C), (A, DEP, D)])
    batched = walk(graph, limits=Limits(200, 2, 2000))
    assert (batched.stop.reason, batched.stop.found, batched.work) == (EDGES, True, 1)
    single = walk(graph, limits=Limits(200, 2, 2000), batched=False)
    assert (single.stop.reason, single.stop.found, single.work) == (EDGES, False, 2)
    exhausted = walk(Graph([(A, DEP, B), (A, DEP, C)]), limits=Limits(200, 2, 2000))
    assert exhausted.stop is None, 'deux rendues : la lecture de trois a montré qu’il n’y en a pas d’autre'


def test_a_high_degree_node_is_read_in_bounded_batches_and_resumed_to_the_last_neighbour():
    graph = Graph([(A, DEP, f'module:n{index:04}') for index in range(1000)])
    tile = walk(graph, fanout=10)
    assert len(tile.elements) == 10
    assert [limit for *_, limit in graph.reads] == [11]
    cut, = tile.cuts
    assert (cut.reason, cut.found) == (FANOUT, True)
    seen, start, pages = [], cut.position, 0
    while start is not None:
        page = walk(graph, fanout=200, start=start)
        seen += [item.adjacent.occurrence for item in page.elements]
        cuts = [*page.cuts, *([page.stop] if page.stop else [])]
        start, pages = (cuts[0].position if cuts else None), pages + 1
    assert len(seen) + 10 == 1000
    assert pages == 5, '990 voisins restants, 199 au plus par page : le budget de nœuds compte l’ancre'
    assert len(set(seen)) == len(seen)
    assert max(limit for *_, limit in graph.reads) == 201


def test_work_counts_every_read_including_empty_ones():
    graph = Graph([(A, DEP, B)])
    tile = walk(graph, steps=((DEP, OUT), (HAS, OUT), (DEP, IN)), limits=Limits(200, 400, 2))
    assert edges(tile) == [(A, B)]
    assert (tile.stop.reason, tile.stop.position) == (WORK, Position(A, 2, ''))


def test_a_step_without_capable_analyzer_is_never_read():
    graph = Graph([(A, DEP, B)])
    tile = walk(graph, steps=((HAS, OUT), (DEP, OUT)), capable=(DEP,))
    assert edges(tile) == [(A, B)]
    assert [step.relation for _, step, _, _ in graph.reads] == [DEP]


def test_a_stop_leaves_the_discovered_nodes_not_reached():
    graph = Graph([(A, DEP, B), (A, DEP, C), (B, DEP, D)])
    tile = walk(graph, depth=3, limits=Limits(200, 2, 2000))
    assert [(node.reference, reason) for node, reason in tile.unexpanded()] == [(C, NOT_REACHED)]
    assert tile.stop.position == Position(B, 0, '')


def test_the_byte_gauge_stops_before_the_element_that_does_not_fit_and_keeps_the_last_admitted_tile():
    graph = Graph([(A, DEP, B), (A, DEP, C), (A, DEP, D)])
    seen = []

    def gauge(tile):
        seen.append(len(tile.elements))
        return len(tile.elements) <= 2

    request = TileRequest(A, (Step(DEP, OUT),), 1, WIDE)
    traversal = Traversal(request, graph, (DEP,), gauge, is_node)
    tile = traversal.run()
    assert edges(tile) == [(A, B), (A, C)]
    assert (tile.stop.reason, tile.stop.found) == (BYTES, True)
    assert len(traversal.admitted.elements) == 2
    with pytest.raises(EnvelopeTooLarge):
        Traversal(request, graph, (DEP,), lambda tile: False, is_node).run()


# ——— Propriétés, contre l'oracle ———

STEPS = [(DEP, OUT), (DEP, IN), (HAS, OUT), (HAS, IN)]
NAMES = [f'module:x{index}' for index in range(7)]


@st.composite
def cases(draw):
    triples = draw(st.lists(st.tuples(st.sampled_from(NAMES), st.sampled_from([DEP, HAS]), st.sampled_from(NAMES)),
                            max_size=24))
    steps = draw(st.lists(st.sampled_from(STEPS), min_size=1, max_size=4, unique=True))
    return Graph(triples), tuple(steps), draw(st.integers(1, 4)), draw(st.sampled_from(NAMES))


def limits():
    return st.builds(Limits, st.integers(1, 9), st.integers(1, 14), st.integers(1, 14))


def sized(budget):
    """Une jauge d'octets fictive mais monotone : la taille des faits rendus et un coût par nœud."""
    def gauge(tile):
        return sum(len(json.dumps(item.adjacent.fact)) for item in tile.elements) + 20 * len(tile.nodes) <= budget
    return gauge


def run(case, limits_=WIDE, depth=None, fanout=None, gauge=always, batched=True, root=None, start=None):
    graph, steps, drawn_depth, drawn_root = case
    return walk(graph, root or drawn_root, steps, depth or drawn_depth, limits_, fanout, batched, gauge, start)


PROPERTIES = settings(max_examples=300, deadline=None, suppress_health_check=[HealthCheck.too_slow])


@PROPERTIES
@given(cases(), limits(), st.none() | st.integers(1, 4), st.booleans())
def test_every_tile_is_honest_bounded_unique_and_deterministic(case, bounds, fanout, batched):
    graph, steps, depth, root = case
    tile = run(case, bounds, fanout=fanout, batched=batched)
    assert tile == run(case, bounds, fanout=fanout, batched=batched), 'déterminisme'
    present = {node.reference for node in tile.nodes}
    for item in tile.elements:
        step = steps[item.step]
        fact = item.adjacent.fact
        anchor, far = ((fact['subject'], fact['object']) if step[1] == OUT else (fact['object'], fact['subject']))
        assert (fact['relation'], anchor) == (step[0], item.origin), 'un fait rendu vient du pas qui le dit'
        assert fact in graph.facts, 'aucun fait fabriqué'
        assert far in present
    assert len(tile.nodes) <= bounds.max_nodes
    assert len(tile.elements) <= bounds.max_edges
    assert tile.work <= bounds.max_work
    occurrences = [item.adjacent.occurrence for item in tile.elements]
    assert len(occurrences) == len(set(occurrences)), 'chaque occurrence une fois'
    assert len(present) == len(tile.nodes), 'chaque nœud une fois'
    if fanout is not None:
        per_node = {}
        for item in tile.elements:
            per_node[item.origin] = per_node.get(item.origin, 0) + 1
        assert max(per_node.values(), default=0) <= fanout
    assert all(node.level <= depth for node in tile.nodes)


@PROPERTIES
@given(cases(), limits())
def test_every_level_is_the_distance_in_the_rendered_tile(case, bounds):
    tile = run(case, bounds)
    distance = {tile.request.root: 0}
    for item in tile.elements:  # en largeur : l'origine est toujours placée avant ses éléments
        fact = item.adjacent.fact
        far = fact['object'] if tile.request.steps[item.step].direction == OUT else fact['subject']
        distance.setdefault(far, distance[item.origin] + 1)
        assert item.level == distance[item.origin] + 1
    assert {node.reference: node.level for node in tile.nodes} == distance


@PROPERTIES
@given(cases(), limits(), limits(), st.integers(0, 3), st.integers(200, 2000), st.integers(0, 2000))
def test_raising_global_budgets_and_depth_extends_the_same_sequence(case, small, extra, deeper, budget, more):
    """§ 4, propriété 1 et 3 : la petite Tuile est un préfixe de la grande, nœuds compris."""
    graph, steps, depth, root = case
    large = Limits(small.max_nodes + extra.max_nodes, small.max_edges + extra.max_edges,
                   small.max_work + extra.max_work)
    little = run(case, small, gauge=sized(budget))
    big = run(case, large, depth=min(4, depth + deeper), gauge=sized(budget + more))
    head = [item.adjacent.occurrence for item in little.elements]
    assert [item.adjacent.occurrence for item in big.elements][:len(head)] == head
    assert [node.reference for node in big.nodes][:len(little.nodes)] == [node.reference for node in little.nodes]


@PROPERTIES
@given(cases(), st.integers(1, 3), st.integers(1, 3))
def test_raising_the_fanout_only_includes_and_only_without_a_global_stop(case, fanout, extra):
    """§ 4, propriété 4 : l'éventail change l'ordre ; seule l'inclusion vaut, et seulement sans arrêt global."""
    little, big = run(case, fanout=fanout), run(case, fanout=fanout + extra)
    if big.stop is None:
        smaller = {item.adjacent.occurrence for item in little.elements}
        assert smaller <= {item.adjacent.occurrence for item in big.elements}


def test_raising_the_fanout_is_not_a_prefix():
    """Le contre-exemple écrit à la main : avec un éventail de 1, b passe avant la seconde occurrence de a."""
    graph = Graph([(A, DEP, B), (A, DEP, C), (B, DEP, D)])
    one = walk(graph, depth=2, fanout=1)
    two = walk(graph, depth=2, fanout=2)
    assert edges(one) == [(A, B), (B, D)]
    assert edges(two) == [(A, B), (A, C), (B, D)]


def expanded_everywhere(graph, root, steps, depth, bounds, fanout, start=None):
    """Une Tuile et toutes les reprises de sa frontière de sélection, récursivement : ce qu'un client atteint."""
    tile = walk(graph, root, steps, depth, bounds, fanout, start=start)
    found = {item.adjacent.occurrence for item in tile.elements}
    levels = {node.reference: node.level for node in tile.nodes}
    for cut in [*tile.cuts, *([tile.stop] if tile.stop else [])]:
        node = cut.position.node
        found |= expanded_everywhere(graph, node, steps, depth - levels[node], bounds, fanout, cut.position)
    for node, reason in tile.unexpanded():
        if reason == NOT_REACHED:
            found |= expanded_everywhere(graph, node.reference, steps, depth - node.level, bounds, fanout)
    return found


@PROPERTIES
@given(cases(), st.integers(2, 6), st.integers(2, 6), st.none() | st.integers(1, 3))
def test_resuming_every_selection_frontier_reaches_exactly_what_the_oracle_reaches(case, nodes_, edges_, fanout):
    graph, steps, depth, root = case
    bounds = Limits(nodes_, edges_, 2000)
    assert expanded_everywhere(graph, root, steps, depth, bounds, fanout) == reachable(graph, root, steps, depth)


@PROPERTIES
@given(cases(), limits(), st.none() | st.integers(1, 3))
def test_every_node_left_unexpanded_is_in_the_frontier(case, bounds, fanout):
    tile = run(case, bounds, fanout=fanout)
    cut = {item.position.node for item in tile.cuts} | ({tile.stop.position.node} if tile.stop else set())
    waiting = {node.reference for node, _ in tile.unexpanded()}
    for node in tile.nodes:
        assert node.expanded or node.reference in cut | waiting
        assert not (node.expanded and node.reference in waiting)
