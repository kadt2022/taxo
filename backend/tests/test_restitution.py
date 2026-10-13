"""D6 (décision « Taxo témoin ») : chaque analyseur dit ce qu'il a restitué de ce qu'il a lu. Un site d'appel est
restitué s'il prouve un fait, non restitué s'il n'est que dans un diagnostic de couverture ; un sujet illisible ou non
interprété sans site n'est pas lu. Mesuré à l'exécution, gardé dans le résumé de l'analyse, rendu par `describe`."""
from test_get_source_uses import taxo_fixture  # noqa: F401
from test_java_calls import ORACLE, execution_fixture  # noqa: F401

from test_get_source import exchange


def test_the_summary_counts_restituted_and_kept_sites(execution):
    restitution = execution.summary()['restitution']
    proofs = sum(1 for fact in execution.facts for proof in fact['evidence'] if proof.get('role') == 'call-site')
    kept = sum(len(fact['diagnostic']['sites']) for fact in execution.coverage
               if fact['coverage_type'] == 'NOT_INTERPRETED' and fact.get('diagnostic'))
    assert restitution['sites_restituted'] == proofs > 0
    assert restitution['sites_not_restituted'] == kept > 0
    assert kept == len(ORACLE['not_interpreted']), 'chaque site que l’oracle dit non interprété est compté'


def test_describe_gives_the_measure_of_each_analyzer(taxo):
    client, url = taxo
    described = exchange(client, url, ('describe', {}))['responses'][0]
    analyzers = {item['analyzer']: item for item in described['items'] if item['kind'] == 'analyzer'}
    java = analyzers['taxo.java-calls']['restitution']
    assert java['sites_restituted'] >= 2, 'enrol appelle check et save'
    assert set(java) == {'sites_restituted', 'sites_not_restituted', 'subjects_not_read'}
    assert all('restitution' in item for item in analyzers.values())
