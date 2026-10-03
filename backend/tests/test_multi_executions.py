"""TAXO-ARCH-REF-01, tranche C3 : une seule regle quand plusieurs executions d'un producteur se melent.

Une analyse n'a qu'une execution par evaluateur (invariant prouve par #78) ; ce cas ne se construit qu'en test.
Avant C3, trois regles y coexistaient : le verdict prenait le contrat de la premiere couverture, la comparaison
l'union des contrats, le voisinage « inconnu ». Desormais, partout : leur contrat commun, sinon inconnu. Aucun
contrat n'est choisi a la place d'un autre ; des contrats differents ne justifient aucune conclusion negative.
"""
from app.comparison.application.compare import CompareAnalyses
from app.evaluations.domain.capability import CatalogContracts, Reads
from app.evaluations.domain.evaluator import EvaluatorCatalog
from app.facts.domain.provenance import ProducerExecution
from app.knowledge.application.loader import from_coverage, recorded_contracts

CONTRACTS = CatalogContracts([EvaluatorCatalog('api', '1', languages=('Java',)),
                              EvaluatorCatalog('api', '2', languages=('Java', 'Kotlin'))])
JAVA, WIDER = Reads.declared(('Java',)), Reads.declared(('Java', 'Kotlin'))


def execution(name, version):
    return ProducerExecution('EVALUATOR', 'taxo.api', '1', name, 'api', version)


def coverage(execution_id, version):
    return {'subject': 'repository:r', 'coverage_type': 'ANALYSED', 'scope': {'include': ['repository:r']},
            'produced_by': {'producer_id': 'taxo.api', 'execution_id': execution_id, 'catalog_id': 'api',
                            'catalog_version': version}}


def by_coverage(*versions):
    facts = [coverage(f'e{index}', version) for index, version in enumerate(versions)]
    analyzer, = from_coverage([{'evaluator_id': 'taxo.api', 'status': 'SUCCESS'}], facts, {},
                              CONTRACTS.reads)
    return analyzer.reads


def by_comparison(*versions):
    return CompareAnalyses(None, None, None, CONTRACTS)._read(
        [execution(f'e{index}', version) for index, version in enumerate(versions)])


def by_summary(*versions):
    found = recorded_contracts([execution(f'e{index}', version) for index, version in enumerate(versions)],
                               lambda item: CONTRACTS.reads(item['catalog_id'], item['catalog_version']))
    return found['taxo.api']


def test_the_rule_keeps_a_common_contract_and_never_chooses_between_different_ones():
    assert Reads.combined([JAVA, JAVA], Reads.unknown()) == JAVA
    assert Reads.combined([JAVA, WIDER], Reads.any()) == Reads.unknown()
    assert Reads.combined([Reads.any(), JAVA], Reads.any()) == Reads.unknown()
    assert Reads.combined([], Reads.any()) == Reads.any(), 'sans execution, chacun dit ce que vaut l absence'


def test_the_verdict_no_longer_takes_the_contract_of_the_first_coverage():
    assert by_coverage('1', '2') == Reads.unknown()
    assert by_coverage('2', '1') == Reads.unknown(), 'l ordre des couvertures ne decide plus'
    assert by_coverage('1', '1') == JAVA


def test_the_comparison_no_longer_reads_the_union_of_different_contracts():
    assert by_comparison('1', '2') == Reads.unknown()
    assert by_comparison('2', '2') == WIDER


def test_every_operation_reads_the_same_contract_from_the_same_executions():
    for versions in (('1',), ('2',), ('1', '1'), ('1', '2'), ('2', '1')):
        readings = {by_coverage(*versions), by_comparison(*versions), by_summary(*versions)}
        assert len(readings) == 1, f'{versions} : {readings}'
