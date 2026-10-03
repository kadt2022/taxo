"""TAXO-ARCH-REF-01, tranche E : une meme analyse dit la meme chose de ce qu'elle n'a pas lu, quelle que soit
l'operation qui le demande.

Le garde-fou qui aurait attrape les divergences 2 et 3 : sur une meme analyse, pour la relation `HANDLED_BY`
(qu'un seul analyseur produit), le verdict, le voisinage, la restitution `/coverage` et la comparaison nomment
les memes langages non lus. Ce n'est pas Taxo jugeant Taxo sur le fond : la verite de chaque cas est ecrite a
la main, et le test exige en plus que les quatre operations l'ecrivent pareil.

Une seule forme differe, et c'est une regle (ARCHITECTURE § 9.3, TAXO-COV-01 regle 6) : quand aucune execution
n'est capable de la relation (son analyseur n'avait rien a lire), le voisinage le dit par une frontiere de
contexte, `NO_ANALYZER`, et non par des langages. Il ne se tait jamais, et ne nomme jamais d'autres langages.
"""
import pytest

from test_coverage_bounds import HEALTH, PYTHON, legacy, taxo_on_fixture  # noqa: F401  (fixture partagee)
from test_knowledge_divergences import forget_catalogs, retire_contract
from test_spring_boot import repository

PRODUCER, RELATION = 'taxo.spring-api', 'HANDLED_BY'
ROOT = {'root': HEALTH['subject'], 'follow': [RELATION], 'direction': 'OUTGOING'}


def forget_both(taxo, before, after):
    for scan in (before, after):
        forget_catalogs(taxo, scan)
    retire_contract(taxo, PRODUCER)


def forget_languages(taxo, before, after):
    for scan in (before, after):
        taxo.forget_languages(scan)


NO_ANALYZER = 'NO_ANALYZER'
# nom : (depot, moteur d'avant COV-01, alteration des analyses, langages non lus, ecrits a la main, et ce que dit
# le voisinage s'il ne les nomme pas)
CASES = {
    'java': (repository(), False, None, [], None),
    'python': (PYTHON, False, None, ['Python'], NO_ANALYZER),
    'mixed': ({**repository(), **PYTHON}, False, None, ['Python'], None),
    'earlier_engine': (PYTHON, True, forget_languages, ['Python'], None),
    'unknown_contract': ({**repository(), **PYTHON}, False, forget_both, ['Java', 'Python'], None),
}


def unread_by_each_operation(taxo, before, after):
    verdict, tile = taxo.ask(('verify_claim', HEALTH), ('get_neighborhood', {'analysis': after, **ROOT}),
                             analysis=after)
    named = sorted(entry['subject'].split(':', 1)[1] for entry in verdict['coverage']
                   if entry['type'] == 'NOT_ANALYSED' and (entry['subject'] or '').startswith('language:'))
    frontier = [language for item in tile['frontier'] if item.get('reason') == 'NOT_ANALYSED'
                and item.get('relation') == RELATION for language in item['languages']]
    if any(item.get('reason') == NO_ANALYZER and item.get('relation') == RELATION for item in tile['frontier']):
        frontier = [NO_ANALYZER, *frontier]
    reading = taxo.client.get(f'{taxo.base}/scans/{after}/coverage').json()
    restituted, = [item['unread'] for item in reading['evaluators'] if item['evaluator_id'] == PRODUCER]
    compared = taxo.compare(before, after)[PRODUCER]['not_analysed']['after']
    return {'verify_claim': named, 'get_neighborhood': sorted(frontier), '/coverage': restituted,
            'comparison': compared}


@pytest.mark.parametrize('case', sorted(CASES))
def test_every_operation_names_the_same_unread_languages(case, taxo_on, git, monkeypatch):
    files, earlier_engine, alter, expected, neighborhood = CASES[case]
    if earlier_engine:
        legacy(monkeypatch)
    taxo, root = taxo_on(files)
    before = taxo.analyse()['id']
    (root / 'NOTES.md').write_text('Une note.\n')
    git(root, 'add', '-A')
    git(root, 'commit', '-qm', 'note')
    after = taxo.analyse()['id']
    if alter:
        alter(taxo, before, after)
    found = unread_by_each_operation(taxo, before, after)
    neighbor = found.pop('get_neighborhood')
    assert found == dict.fromkeys(found, expected), f'{case} : {found}'
    assert neighbor == ([neighborhood] if neighborhood else expected), f'{case} : voisinage {neighbor}'
