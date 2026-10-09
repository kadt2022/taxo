"""TAXO-01M, PR C : les décomptes par catégorie d'une zone non lue, dans `neighborhood/2`, sur les deux stockages.

Champ additif d'une entrée `KNOWLEDGE`/`NODE` : rien d'autre ne change. Les décomptes attendus sont écrits à la
main ; un décompte n'est jamais inventé, et une catégorie non observée n'est jamais lue comme un zéro exact.
"""
from copy import deepcopy

import pytest

from app.facts.contract import validate_fact
from app.facts.domain.diagnostic import CATEGORIES, category_counts
from app.neighborhood.application.knowledge_frontier import local_frontier
from app.protocol.application.neighborhood_form import compact
from test_neighborhood_conformance import RUN, SNAPSHOT, STORAGES
from test_neighborhood_v2 import A, D, V2, ask, twin  # noqa: F401  (fixture partagée)

RULE = 'python.synthetic.frontier-classification/1'


def site(column, reason, category=None):
    found = {'role': 'call-site', 'line_start': 4, 'line_end': 4, 'column_start': column,
             'column_end': column + 3, 'reason': reason}
    return {**found, 'category': category} if category else found


def unread(subject, sites, seen=None, classification=RULE, kind='NOT_INTERPRETED'):
    diagnostic = {'sites_seen': len(sites) if seen is None else seen, 'sites': sites}
    if classification:
        diagnostic['classification'] = classification
    fact = {'contract_version': 1, 'kind': 'COVERAGE', 'status': 'OBSERVED', 'validity': 'VALID', 'subject': subject,
            'coverage_type': kind, 'scope': {'include': [subject]}, 'snapshot': dict(SNAPSHOT),
            'produced_by': RUN.produced_by(), 'diagnostic': diagnostic}
    validate_fact(fact)
    return fact


def six_sites():
    """3 `UNKNOWN`, 2 `AMBIGUOUS`, 1 `UNSUPPORTED` : l'exemple du récit."""
    kinds = ['UNKNOWN'] * 3 + ['AMBIGUOUS'] * 2 + ['UNSUPPORTED']
    return [site(index * 4, f'CODE_{kind}', kind) for index, kind in enumerate(kinds)]


def exact(**counts):
    return [{'category': name, 'count': {'kind': 'EXACT', 'value': counts[name]}} for name in CATEGORIES
            if name in counts]


def at_least(**counts):
    return [{'category': name, 'count': {'kind': 'AT_LEAST', 'value': counts.get(name, 0)}} for name in CATEGORIES]


def node_gaps(result):
    return [entry for entry in result['frontier'] if entry['nature'] == 'KNOWLEDGE' and entry.get('scope') == 'NODE']


def test_a_complete_list_gives_exact_counts_and_omits_a_zero():
    assert category_counts(unread(D, six_sites())) == exact(UNKNOWN=3, AMBIGUOUS=2, UNSUPPORTED=1)


def test_a_truncated_list_gives_the_four_categories_at_least_zero_included():
    """10 sites vus, 6 retenus : 3, 2, 1 et 0 au moins ; jamais un `OUT_OF_SCOPE` absent lu comme zéro."""
    assert category_counts(unread(D, six_sites(), seen=10)) == at_least(UNKNOWN=3, AMBIGUOUS=2, UNSUPPORTED=1)


def test_an_unclassified_or_absent_diagnostic_has_no_count():
    old = unread(D, [site(0, 'CODE_UNKNOWN')], classification=None)
    assert category_counts(old) is None
    without = deepcopy(old)
    del without['diagnostic']
    assert category_counts(without) is None


@pytest.mark.parametrize('name', STORAGES)
def test_a_classified_gap_carries_its_counts_on_its_node_entry_only(twin, name):  # noqa: F811
    twin.add([unread(D, six_sites())])
    result = ask(twin, name, depth=3, max_bytes=30_000, **V2)
    gaps = node_gaps(result)
    assert [(entry['node'], entry['reason'], entry['causes'], entry['count']) for entry in gaps] == [
        (D, 'NOT_INTERPRETED', ['CODE_AMBIGUOUS', 'CODE_UNKNOWN', 'CODE_UNSUPPORTED'], {'kind': 'UNKNOWN'})]
    assert gaps[0]['categories'] == exact(UNKNOWN=3, AMBIGUOUS=2, UNSUPPORTED=1)
    assert all('categories' not in entry for entry in result['frontier'] if entry not in gaps)


@pytest.mark.parametrize('name', STORAGES)
def test_a_truncated_gap_lists_four_lower_bounds(twin, name):  # noqa: F811
    twin.add([unread(D, six_sites(), seen=10)])
    [entry] = node_gaps(ask(twin, name, depth=3, max_bytes=30_000, **V2))
    assert entry['categories'] == at_least(UNKNOWN=3, AMBIGUOUS=2, UNSUPPORTED=1)


@pytest.mark.parametrize('name', STORAGES)
def test_an_analysis_written_before_the_categories_reads_as_before(twin, name):  # noqa: F811
    """Le même diagnostic, sans classification : aucune entrée n'a `categories`, et le reste est identique."""
    old = [site(index * 4, item['reason']) for index, item in enumerate(six_sites())]
    twin.add([unread(D, old, classification=None)])
    before = ask(twin, name, depth=3, max_bytes=30_000, **V2)
    assert all('categories' not in entry for entry in before['frontier'])
    [entry] = node_gaps(before)
    assert entry['causes'] == ['CODE_AMBIGUOUS', 'CODE_UNKNOWN', 'CODE_UNSUPPORTED']


@pytest.mark.parametrize('name', STORAGES)
def test_classified_gaps_that_do_not_fit_are_counted_never_cut_in_half(twin, name):  # noqa: F811
    twin.add([unread(subject, six_sites(), seen=10) for subject in (A, D)])
    complete = ask(twin, name, depth=3, max_bytes=30_000, **V2)
    assert len(node_gaps(complete)) == 2
    seen = set()
    for budget in range(complete['bytes'], 3000, -60):
        result = ask(twin, name, depth=3, max_bytes=budget, **V2)
        if result['outcome'] != 'OK':
            break
        assert result['bytes'] <= budget
        assert all(entry['categories'] == at_least(UNKNOWN=3, AMBIGUOUS=2, UNSUPPORTED=1)
                   for entry in node_gaps(result))
        counted = sum(entry['count'] for entry in result['not_sent'] if entry['what'] == 'local_coverage')
        seen.add(counted > 0)
    assert True in seen, 'un budget où des lacunes classées ne tiennent pas, et sont comptées'


@pytest.mark.parametrize('name', STORAGES)
def test_the_compact_form_carries_the_counts_as_they_are(twin, name):  # noqa: F811
    twin.add([unread(D, six_sites())])
    full = ask(twin, name, depth=3, max_bytes=30_000, **V2)
    assert compact(full)['frontier'] == full['frontier']
    compacted = ask(twin, name, depth=3, max_bytes=30_000, form='COMPACT', **V2)
    assert [entry['categories'] for entry in node_gaps(compacted)] == [exact(UNKNOWN=3, AMBIGUOUS=2, UNSUPPORTED=1)]


def test_two_producers_on_one_symbol_keep_two_entries():
    class Reader:
        def unread(self, scan_id, references):
            return [{'subject': D, 'coverage_type': 'NOT_INTERPRETED', 'producer': producer, 'reasons': ['X'],
                     'categories': exact(UNKNOWN=1)} for producer in ('taxo.java-calls', 'test.synthetic-python')]

    class Node:
        reference = D

    class Tile:
        known, nodes, elements = True, [Node()], []

    found = local_frontier(Reader(), 'scan', Tile())
    assert [(entry['producer'], entry['categories']) for entry in found] == [
        ('taxo.java-calls', exact(UNKNOWN=1)), ('test.synthetic-python', exact(UNKNOWN=1))]
