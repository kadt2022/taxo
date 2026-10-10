"""Classification des Tuiles MIP et restrictions de divulgation (récit TAXO-MIP-ADT-01 § 21 bis).

La règle testée partout : une catégorie est annoncée si et seulement si la Tuile transmise en contient, y compris
quand elle est coupée par un budget, quand l'ancre est inconnue ou quand la requête est refusée. La vérité vient du
dépôt scénarisé des appels Java (`test_java_calls.fixture_files`) et de son historique Git.
"""
import pytest

from app.mip.domain.classification import CATEGORIES, nature
from app.facts import is_reference
from test_coverage_bounds import taxo_on_fixture  # noqa: F401  (fixture partagée)
from test_java_calls import fixture_files
from test_mip import CONTROLLER, REGISTER, ask, expand
from test_mip_profiles import profiled

CLASSIFICATION_FIELDS = {'version', 'nature', 'language', 'profile', 'content', 'provenance'}


def expected_content(tile):
    """Les catégories que le contenu transmis justifie, recalculées indépendamment de l'adaptateur."""
    facts = tile['facts']
    present = {
        'FACTS': bool(facts),
        'RELATIONS': any(isinstance(item['fact'].get('object'), str) and is_reference(item['fact']['object'])
                         for item in facts),
        'EVIDENCE': any(item.get('evidence') for item in facts),
        'CODE_SOURCE': False,
        'COMMIT_METADATA': any(item['fact']['relation'] in {'HAS_COMMIT', 'CHILD_OF', 'AUTHORED_BY', 'CHANGES'}
                               for item in facts),
        'COVERAGE': bool(tile['coverage']),
        'FRONTIER': bool(tile['frontier']),
    }
    return [category for category in CATEGORIES if present[category]]


def assert_consistent(tile):
    classification = tile['classification']
    assert set(classification) - {'commit_metadata'} == CLASSIFICATION_FIELDS, 'aucun champ interprétatif'
    assert classification['content'] == expected_content(tile)
    assert 'CODE_SOURCE' not in classification['content'], 'une Tuile de faits ne transporte jamais de code'
    assert classification['provenance']['snapshot'] == tile['snapshot']
    assert classification['provenance']['facts_revision'] == tile['wire']['facts_revision']
    producers = {item['fact']['produced_by']['producer_id'] for item in tile['facts']}
    assert {producer['id'] for producer in classification['provenance']['producers']} == producers
    assert tile['disclosure']['version'] == 'tile-disclosure/1'


@pytest.fixture(name='courses')
def courses_fixture(taxo_on):
    taxo, _ = taxo_on(fixture_files())
    return taxo, taxo.analyse()['id']


@pytest.mark.parametrize('reference, expected', [
    (REGISTER, 'METHOD'),
    (CONTROLLER, 'TYPE'),
    (f'{CONTROLLER}#service', 'MEMBER'),
    (f'{CONTROLLER}#register(String)#title', 'MEMBER'),
    ('endpoint:POST /api/courses', 'ENDPOINT'),
    ('route-pattern:/api/**', 'ROUTE_PATTERN'),
    ('commit:' + 'a' * 40, 'COMMIT'),
    ('module:demo', 'MODULE'),
    ('file:src/Items.list(String)', 'FILE'),
])
def test_the_nature_is_read_in_the_reference_syntax_only(reference, expected):
    assert nature(reference) == expected


def test_a_method_tile_is_classified_by_what_it_carries(courses):
    taxo, _ = courses
    tile = ask(taxo, profiled(REGISTER, 'method-context/1', bounds={'max_bytes': 32_000}))
    classification = tile['classification']
    assert (classification['nature'], classification['language'], classification['profile']) == (
        'METHOD', 'java', 'method-context/1')
    assert {'FACTS', 'RELATIONS', 'EVIDENCE', 'COVERAGE', 'FRONTIER'} <= set(classification['content'])
    assert 'COMMIT_METADATA' not in classification['content'] and 'commit_metadata' not in classification
    assert tile['disclosure']['restrictions'] == []
    assert_consistent(tile)


def test_an_explicit_query_is_classified_without_profile(courses):
    taxo, _ = courses
    tile = ask(taxo, expand(REGISTER))
    assert tile['classification']['profile'] is None
    assert_consistent(tile)


@pytest.mark.parametrize('budget', [5_000, 6_000, 8_000])
def test_a_truncated_tile_announces_only_what_was_transmitted(courses, budget):
    taxo, _ = courses
    tile = ask(taxo, profiled(REGISTER, 'method-context/1', bounds={'max_bytes': budget}))
    assert tile['outcome'] == 'OK'
    assert_consistent(tile)


def test_an_unknown_anchor_announces_no_fact(courses):
    taxo, _ = courses
    tile = ask(taxo, expand(f'{CONTROLLER}#missing()'))
    assert tile['root']['known'] is False
    assert not {'FACTS', 'RELATIONS', 'EVIDENCE'} & set(tile['classification']['content'])
    assert tile['classification']['nature'] == 'METHOD' and tile['classification']['language'] == 'java'
    assert_consistent(tile)


def test_a_refusal_carries_no_classification(courses):
    taxo, _ = courses
    refused = ask(taxo, {**expand(REGISTER), 'expression': 'PROJECT'})
    assert refused['outcome'] == 'ERROR' and 'classification' not in refused and 'disclosure' not in refused
    too_small = ask(taxo, profiled(REGISTER, 'method-context/1', bounds={'max_bytes': 1_000}))
    assert too_small['outcome'] == 'ERROR' and 'classification' not in too_small


def test_commit_metadata_is_what_git_facts_carry_and_the_author_identity_is_restricted(courses):
    taxo, scan = courses
    commit = 'commit:' + ask(taxo, expand(REGISTER))['snapshot']['commit']
    tile = ask(taxo, expand(commit, relations=('HAS_COMMIT', 'AUTHORED_BY'), direction='BOTH', analysis=scan,
                            bounds={'max_bytes': 32_000}))
    relations = {item['fact']['relation'] for item in tile['facts']}
    assert {'HAS_COMMIT', 'AUTHORED_BY'} <= relations, 'le dépôt de test a un historique Git'
    classification = tile['classification']
    assert (classification['nature'], classification['language']) == ('COMMIT', None)
    assert 'COMMIT_METADATA' in classification['content']
    qualifiers = next(item['fact']['qualifiers'] for item in tile['facts'] if item['fact']['relation'] == 'HAS_COMMIT')
    assert classification['commit_metadata'] == {
        'commits': 1, 'fields': ['sha', 'author', *sorted(name for name in ('authored_at', 'committed_at', 'message')
                                                         if name in qualifiers)]}
    codes = [restriction['code'] for restriction in tile['disclosure']['restrictions']]
    assert 'PERSON_IDENTITY' in codes
    assert ('COMMIT_MESSAGE' in codes) == ('message' in qualifiers)
    assert_consistent(tile)
