"""TAXO-ARCH-REF-01, tranche A : deux divergences de la connaissance d'une analyse, trouvees par l'audit.

Chaque test ecrit le comportement attendu et echoue aujourd'hui (`xfail(strict=True)`) : il n'est ni masque ni
corrige dans une restructuration. Quand une correction dediee le fera passer, `strict` obligera a retirer la
marque, et le test deviendra un garde-fou ordinaire.
"""
import pytest
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.protocol.domain.verdict import NOT_ANALYSED
from app.scans.infrastructure.sqlalchemy.fact_memory import ProducerExecutionRow
from test_coverage_bounds import HEALTH, PYTHON, legacy, taxo_on_fixture  # noqa: F401  (fixture partagee)


def retire_contract(taxo, producer):
    """Le catalogue enregistre avec ces executions n'est plus connu de ce Taxo (version retiree)."""
    with Session(taxo.engine) as db:
        db.execute(update(ProducerExecutionRow).where(ProducerExecutionRow.producer_id == producer)
                   .values(catalog_version='retiree'))
        db.commit()


@pytest.mark.xfail(strict=True, reason='TAXO-ARCH-REF-01, divergence 1 : la comparaison tient un contrat inconnu '
                                       'pour independant du langage, le verdict pour un contrat qui ne lit rien.')
def test_an_unknown_contract_justifies_no_negative_conclusion_anywhere(taxo_on, git, monkeypatch):
    legacy(monkeypatch)
    taxo, root = taxo_on(PYTHON)
    before = taxo.analyse()['id']
    (root / 'api/admin.py').write_text('from api.main import app\n')
    git(root, 'add', '-A')
    git(root, 'commit', '-qm', 'admin')
    after = taxo.analyse()['id']
    retire_contract(taxo, 'taxo.spring-api')
    verdict, = taxo.ask(('verify_claim', HEALTH), analysis=after)
    assert verdict['reason'] == NOT_ANALYSED, 'le verdict ne tire rien d un contrat inconnu'
    compared = taxo.compare(before, after)['taxo.spring-api']
    assert not compared['comparable'], 'la comparaison ne doit pas en tirer « aucun changement »'


@pytest.mark.xfail(strict=True, reason='TAXO-ARCH-REF-01, divergence 2 : le voisinage d une analyse anterieure '
                                       'ne nomme pas les langages que verify_claim nomme, dans le meme echange.')
def test_an_earlier_analysis_names_the_same_unread_languages_in_every_operation(taxo_on, monkeypatch):
    legacy(monkeypatch)
    taxo, _ = taxo_on(PYTHON)
    scan = taxo.analyse()['id']
    taxo.forget_languages(scan)
    verdict, tile = taxo.ask(('verify_claim', HEALTH), ('get_neighborhood', {
        'analysis': scan, 'root': HEALTH['subject'], 'follow': ['HANDLED_BY'], 'direction': 'OUTGOING'}), analysis=scan)
    named = sorted(entry['subject'] for entry in verdict['coverage'] if entry['type'] == 'NOT_ANALYSED' and entry['subject'])
    assert named == ['language:Python']
    frontier = [item for item in tile['frontier'] if item.get('reason') == 'NOT_ANALYSED']
    assert [item['languages'] for item in frontier] == [['Python']], 'le voisinage dit la meme limite que le verdict'
