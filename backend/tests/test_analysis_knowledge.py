"""TAXO-ARCH-REF-01, tranche C2 : ce qu'une analyse sait d'elle-meme, en un seul foyer.

Les predicats de COV-01 (« a lu un langage present », « atteint la relation », « langages non lus », « langages
peut-etre manquants ») et la zone non lue sont definis une fois ; le verdict, l'enveloppe et le voisinage les
lisent. Une seule source pour les langages d'une analyse, enregistres ou relus dans ses faits.
"""
import re
from pathlib import Path
from types import SimpleNamespace

from app.evaluations.domain.capability import UNREAD_COVERAGE, Reads, languages_complete
from app.knowledge.application.loader import analysis_languages, from_summary, recorded_languages
from app.knowledge.domain.knowledge import AnalysisKnowledge, Analyzer

APP = Path(__file__).resolve().parents[1] / 'app'


def analysed(include='repository:r', exclude=()):
    return {'subject': 'repository:r', 'coverage_type': 'ANALYSED', 'scope': {'include': [include],
                                                                              'exclude': list(exclude)}}


ROUTES = frozenset({'HANDLED_BY'})


def test_reaching_needs_a_finished_capable_execution_that_read_a_present_language():
    java = Analyzer('j', ROUTES, coverage=(analysed(),), reads=Reads.declared(('Java',)))
    failed = Analyzer('f', ROUTES, failed=True, coverage=(analysed(),))
    unsupported = Analyzer('u', ROUTES, coverage=(analysed(),), unsupported=True)
    knowledge = AnalysisKnowledge(('Java',), True, (java, failed, unsupported))
    assert knowledge.reaching('HANDLED_BY') == [java]
    assert knowledge.reaching('CONTAINS') == []
    assert AnalysisKnowledge(('Python',), True, (java,)).reaching('HANDLED_BY') == []


def test_a_subject_outside_the_analysed_scope_is_not_reached():
    scoped = Analyzer('s', ROUTES, coverage=(analysed(exclude=['directory:vendor']),))
    knowledge = AnalysisKnowledge(('Java',), True, (scoped,))
    assert knowledge.reaching('HANDLED_BY', 'file:src/A.java') == [scoped]
    assert knowledge.reaching('HANDLED_BY', 'file:vendor/B.java') == []


def test_the_unread_languages_are_those_no_reaching_execution_reads():
    java = Analyzer('j', ROUTES, coverage=(analysed(),), reads=Reads.declared(('Java',)))
    knowledge = AnalysisKnowledge(('Java', 'Python'), True, (java,))
    assert knowledge.not_analysed('HANDLED_BY') == ('Python',)
    assert knowledge.not_analysed('HANDLED_BY', needed=('Java',)) == ()
    anywhere = Analyzer('a', ROUTES, coverage=(analysed(),))
    assert AnalysisKnowledge(('Java', 'Python'), True, (java, anywhere)).not_analysed('HANDLED_BY') == ()


def test_an_incomplete_inventory_leaves_languages_unknown_unless_an_independent_reader_reached():
    java = Analyzer('j', ROUTES, coverage=(analysed(),), reads=Reads.declared(('Java',)))
    anywhere = Analyzer('a', ROUTES, coverage=(analysed(),))
    assert AnalysisKnowledge(('Java',), False, (java,)).languages_unknown('HANDLED_BY')
    assert not AnalysisKnowledge(('Java',), True, (java,)).languages_unknown('HANDLED_BY')
    assert not AnalysisKnowledge(('Java',), False, (anywhere,)).languages_unknown('HANDLED_BY')


def test_an_analysis_names_its_languages_from_one_source():
    recorded = SimpleNamespace(id='a', result={'languages': ['Java']})
    earlier = SimpleNamespace(id='b', result={})
    facts = SimpleNamespace(objects=lambda scan_id, relation: ['language:Python', 'other', None])
    assert recorded_languages(recorded) == ('Java',)
    assert recorded_languages(earlier) is None
    assert analysis_languages(recorded, facts) == ('Java',)
    assert analysis_languages(earlier, facts) == ('Python',), 'une analyse anterieure les relit dans ses faits'


def test_a_summary_reads_the_contract_its_execution_named_and_nothing_known_without_one():
    evaluations = [{'evaluator_id': 'api', 'status': 'SUCCESS', 'catalog_id': 'c', 'catalog_version': '1',
                    'coverage': [{'coverage_type': 'ANALYSED'}]},
                   {'evaluator_id': 'old', 'status': 'SUCCESS', 'coverage': []}]
    contracts = {('c', '1'): Reads.declared(('Java',))}

    def reads_of(item):
        return contracts.get((item.get('catalog_id'), item.get('catalog_version')), Reads.unknown())
    api, old = from_summary(evaluations, {'api': ROUTES}, reads_of, lambda: [])
    assert api.reads == Reads.declared(('Java',))
    assert api.relations == ROUTES
    assert api.coverage == ({'coverage_type': 'ANALYSED'},)
    assert old.reads == Reads.unknown(), 'aucune execution enregistree : son contrat est inconnu'


def test_the_unread_zone_has_one_definition():
    """« Zone non lue » etait ecrite sept fois ; elle ne l'est plus qu'une (les catalogues declarent leurs types)."""
    pair = re.compile(r"""['"](NOT_INTERPRETED|READ_ERROR)['"]\s*,\s*['"](NOT_INTERPRETED|READ_ERROR)['"]""")
    found = [str(path.relative_to(APP)) for path in APP.rglob('*.py')
             if path.name != 'catalog.py' and pair.search(path.read_text(encoding='utf-8'))]
    assert found == ['evaluations/domain/capability.py']
    assert UNREAD_COVERAGE == frozenset({'NOT_INTERPRETED', 'READ_ERROR'})
    assert not languages_complete({'status': 'SUCCESS', 'coverage': [{'coverage_type': 'READ_ERROR'}]})
