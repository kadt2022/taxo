"""D4 (décision « Taxo témoin ») : un fichier binaire (octet nul, comme Git le reconnaît) n'a aucun texte à lire. Il est
recensé, dit hors du périmètre de lecture (`OUT_OF_SCOPE`, avec sa raison), et ne rend plus l'inventaire incomplet : un
cache de build ne change rien à ce que Taxo sait du code. Un texte d'un autre encodage, lui, peut cacher du code : il
reste non interprété, et l'inventaire reste incomplet."""
from app.evaluations.application.run_evaluator import RunEvaluator
from app.evaluations.domain.capability import languages_complete
from app.evaluators.inventory.evaluator import BINARY_REASON, InventoryEvaluator
from app.facts.contract import validate_fact
from app.snapshots.infrastructure.git.reader import open_snapshot

BINARY = bytes([0x00, 0x01, 0xff, 0xfe, 0x00, 0x10])
LATIN = 'class Café {}\n'.encode('latin-1')


def run(make_repo, files):
    repo = make_repo(files)
    return RunEvaluator()(InventoryEvaluator(), open_snapshot(repo, 'demo', 'COMMIT', None))


def coverage(execution, kind):
    return {fact['subject'] for fact in execution.coverage if fact['coverage_type'] == kind}


def test_a_binary_file_is_out_of_scope_with_its_reason(make_repo):
    execution = run(make_repo, {'Hello.java': 'class Hello {}\n', '.gradle/cache.bin': BINARY})
    assert coverage(execution, 'OUT_OF_SCOPE') == {'file:.gradle/cache.bin'}
    assert not coverage(execution, 'NOT_INTERPRETED')
    out, = [fact for fact in execution.coverage if fact['coverage_type'] == 'OUT_OF_SCOPE']
    assert out['reason'] == BINARY_REASON
    assert validate_fact(out) is None


def test_a_binary_file_no_longer_makes_the_inventory_incomplete(make_repo):
    execution = run(make_repo, {'Hello.java': 'class Hello {}\n', 'gradle/wrapper.jar': BINARY})
    assert languages_complete(execution.summary())


def test_a_text_in_another_encoding_stays_not_interpreted(make_repo):
    execution = run(make_repo, {'Cafe.java': LATIN})
    assert coverage(execution, 'NOT_INTERPRETED') == {'file:Cafe.java'}
    assert not coverage(execution, 'OUT_OF_SCOPE')
    assert not languages_complete(execution.summary()), 'il peut cacher du code : rien n’est dit absent'
