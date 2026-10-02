"""TAXO-ARCH-REF-01 : ce que lit un contrat de catalogue, en trois cas explicites.

Avant `Reads`, « independant du langage » s'ecrivait `None` et « contrat inconnu » `frozenset()` : la confusion
des deux (P2 de #74) etait possible a ecrire. Ces tests fixent les trois cas et la composition des contrats.
"""
import pytest

from app.evaluations.domain.capability import CatalogContracts, Reads, applicable, unread
from app.evaluations.domain.evaluator import EvaluatorCatalog


def test_the_three_cases_are_never_confused():
    anywhere, java, unknown = Reads.any(), Reads.declared(('Java',)), Reads.unknown()
    assert anywhere.independent and anywhere.known
    assert not java.independent and java.known
    assert not unknown.independent and not unknown.known, 'un contrat inconnu n est jamais independant du langage'
    assert Reads.declared(None) == anywhere


def test_what_each_case_reads_of_the_present_languages():
    present = ('Java', 'Python')
    assert Reads.any().reads_present(()) and Reads.any().unread(present) == ()
    assert Reads.declared(('Java',)).reads_present(present)
    assert not Reads.declared(('Java',)).reads_present(('Python',))
    assert Reads.declared(('Java',)).unread(present) == ('Python',)
    assert not Reads.unknown().reads_present(present), 'un contrat inconnu ne lit rien de connu'
    assert Reads.unknown().unread(present) == present


def test_the_public_form_keeps_its_three_shapes():
    assert Reads.any().listed() is None
    assert Reads.declared(('Python', 'Java')).listed() == ['Java', 'Python']
    assert Reads.unknown().listed() == []


@pytest.mark.parametrize('kind, languages', [('ANY', frozenset({'Java'})), ('UNKNOWN', frozenset({'Java'})),
                                             ('LANGUAGES', frozenset()), ('OTHER', frozenset())])
def test_an_inconsistent_reading_cannot_be_written(kind, languages):
    with pytest.raises(ValueError):
        Reads(kind, languages)


def test_contracts_are_known_by_identity_and_version_and_unknown_otherwise():
    contracts = CatalogContracts([EvaluatorCatalog('api', '2', languages=('Java',)), EvaluatorCatalog('git', '1')])
    assert contracts and not CatalogContracts()
    assert contracts.reads('api', '2') == Reads.declared(('Java',))
    assert contracts.reads('git', '1') == Reads.any()
    assert contracts.reads('api', '1') == Reads.unknown(), 'une autre version est un autre contrat'
    assert contracts.reads(None, None) == Reads.unknown()
    assert contracts.knows('git', '1') and not contracts.knows('api', '1')


def test_the_shared_predicates_read_through_the_same_value():
    assert applicable(None, ()) and applicable(('Java',), ('Java',)) and not applicable(('Java',), ('Python',))
    assert unread(('Java', 'Python'), [Reads.declared(('Java',))]) == ('Python',)
    assert unread(('Java', 'Python'), [Reads.declared(('Java',)), Reads.any()]) == ()
    assert unread(('Java',), [Reads.unknown()]) == ('Java',)
    assert unread(('Java',), []) == ('Java',)
