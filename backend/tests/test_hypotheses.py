"""ADR 0006 : l'hypothese statistique n'est pas un fait, et ses poids restent hors du depot."""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from app.bootstrap import settings
from app.hypotheses.application.propose_hypothesis import ProposeHypothesis
from app.hypotheses.domain.hypothesis import (ABSTAIN, UNCALIBRATED, WHO_CAN_CALL, ModelIdentity,
                                              Question, Representation, decide)
from app.hypotheses.infrastructure.model_store import MANIFEST_PATH, ModelStore, ModelStoreError

APP = Path(__file__).parents[1] / 'app'
IDENTITY = ModelIdentity('fake', 'fake-1', '1', 42, 'f' * 64)
REPRESENTATION = Representation(
    'endpoint:PUT /api/orders/{id}', WHO_CAN_CALL,
    known=('HANDLED_BY symbol:OrderController#update',),
    unknown=('chaine de filtres : securityMatcher non interprete',),
    withheld=('MATCHED_BY route-pattern:/**',))


class FakeModel:
    identity = IDENTITY

    def __init__(self, scores):
        self.scores = scores

    def score(self, representation):
        return self.scores


def test_the_decision_is_the_best_label_only_above_the_threshold():
    scores = {'AUTHENTICATED_ONLY': 0.7, 'PUBLIC': 0.1, 'RESTRICTED': 0.2}
    assert decide(scores, WHO_CAN_CALL, 0.6) == 'AUTHENTICATED_ONLY'
    assert decide(scores, WHO_CAN_CALL, 0.8) == ABSTAIN


@pytest.mark.parametrize('scores', [
    {'PUBLIC': 0.5, 'RESTRICTED': 0.5},
    {'AUTHENTICATED_ONLY': 0.5, 'PUBLIC': 0.5, 'RESTRICTED': 0.5},
    {'AUTHENTICATED_ONLY': 1.2, 'PUBLIC': -0.1, 'RESTRICTED': -0.1},
    {'AUTHENTICATED_ONLY': 0.5, 'PUBLIC': 0.5, 'RESTRICTED': 0.0, ABSTAIN: 0.0},
])
def test_scores_must_be_a_distribution_over_exactly_the_question_labels(scores):
    with pytest.raises(ValueError):
        decide(scores, WHO_CAN_CALL, 0.5)


def test_abstain_is_a_decision_never_a_label():
    with pytest.raises(ValueError, match='decision'):
        Question('q', '1', (ABSTAIN, 'PUBLIC'))


def test_a_proposed_hypothesis_carries_its_model_and_representation():
    propose = ProposeHypothesis(FakeModel({'AUTHENTICATED_ONLY': 0.2, 'PUBLIC': 0.1, 'RESTRICTED': 0.7}), 0.6)
    hypothesis = propose(REPRESENTATION, {'repository': 'shop', 'commit': 'a' * 40})
    assert hypothesis.decision == 'RESTRICTED'
    assert hypothesis.model == IDENTITY
    assert hypothesis.calibration == UNCALIBRATED
    assert hypothesis.representation == REPRESENTATION.fingerprint()
    assert 'MATCHED_BY route-pattern:/**' not in REPRESENTATION.text(), 'un fait retire ne parle pas au modele'


def test_the_fact_side_of_taxo_never_knows_hypotheses():
    """Une hypothese ne peut devenir une premisse que si le cote fait la connait : il ne la connait pas."""
    for capability in ('facts', 'evaluations', 'evaluators', 'snapshots'):
        for path in (APP / capability).rglob('*.py'):
            assert 'app.hypotheses' not in path.read_text(encoding='utf-8'), path


def test_the_domain_and_use_case_load_no_model_runtime():
    code = '''
import sys
import app.hypotheses.domain.hypothesis
import app.hypotheses.application.propose_hypothesis
assert not {'torch', 'transformers', 'urllib.request'} & set(sys.modules)
'''
    subprocess.run([sys.executable, '-c', code], cwd=APP.parent, check=True)


class Transport:
    def __init__(self, contents, revision='c' * 40):
        self.contents, self.revision, self.downloads = contents, revision, []

    def download(self, url, destination):
        self.downloads.append(url)
        Path(destination).write_bytes(self.contents[url.rsplit('/', 1)[-1]])

    def json(self, url):
        return {'sha': self.revision}


CONTENTS = {'config.json': b'{}', 'model.safetensors': b'weights'}


def manifest(tmp_path, revision='c' * 40, files=None):
    files = files or {name: hashlib.sha256(data).hexdigest() for name, data in CONTENTS.items()}
    path = tmp_path / 'models.json'
    path.write_text(json.dumps({'tiny': {'family': 'tiny', 'repository': 'org/tiny',
                                         'revision': revision, 'files': files}}))
    return path


def store(tmp_path, transport, manifest_path):
    return ModelStore(tmp_path / 'models', manifest_path, transport, log=lambda message: None)


def test_a_pinned_model_is_downloaded_once_then_verified_offline(tmp_path):
    transport = Transport(CONTENTS)
    models = store(tmp_path, transport, manifest(tmp_path))
    directory = models.ensure('tiny')
    assert (directory / 'model.safetensors').read_bytes() == b'weights'
    assert len(transport.downloads) == 2
    models.ensure('tiny')
    assert len(transport.downloads) == 2, 'un modele intact ne se retelecharge pas'
    assert set(models.status('tiny').values()) == {'ok'}


def test_an_altered_file_is_downloaded_again(tmp_path):
    transport = Transport(CONTENTS)
    models = store(tmp_path, transport, manifest(tmp_path))
    directory = models.ensure('tiny')
    (directory / 'model.safetensors').write_bytes(b'tampered')
    assert models.status('tiny')['model.safetensors'] == 'corrupt'
    models.ensure('tiny')
    assert (directory / 'model.safetensors').read_bytes() == b'weights'


def test_a_download_with_the_wrong_digest_is_refused_and_leaves_nothing(tmp_path):
    transport = Transport({**CONTENTS, 'model.safetensors': b'other weights'})
    models = store(tmp_path, transport, manifest(tmp_path))
    with pytest.raises(ModelStoreError, match='Empreinte inattendue pour model.safetensors'):
        models.ensure('tiny')
    directory = tmp_path / 'models' / 'tiny' / ('c' * 40)
    assert not (directory / 'model.safetensors').exists()
    assert not list(directory.glob('*.part'))


def test_an_unpinned_model_is_never_used_unless_explicitly_recorded(tmp_path):
    path = manifest(tmp_path, revision=None, files={'config.json': None, 'model.safetensors': None})
    transport = Transport(CONTENTS, revision='d' * 40)
    models = store(tmp_path, transport, path)
    assert set(models.status('tiny').values()) == {'unpinned'}
    with pytest.raises(ModelStoreError, match="n'est pas epingle"):
        models.ensure('tiny')
    assert transport.downloads == []
    models.ensure('tiny', record=True)
    pinned = json.loads(path.read_text())['tiny']
    assert pinned['revision'] == 'd' * 40
    assert pinned['files']['model.safetensors'] == hashlib.sha256(b'weights').hexdigest()
    assert all(f'/resolve/{"d" * 40}/' in url for url in transport.downloads)


def test_the_shipped_manifest_names_its_source_and_license():
    entry = json.loads(MANIFEST_PATH.read_text())['smollm2-135m']
    assert entry['repository'] == 'HuggingFaceTB/SmolLM2-135M'
    assert 'model.safetensors' in entry['files']
    assert entry['license']


def test_the_documentary_mode_downloads_nothing():
    assert settings.hypotheses_models('') == []
    assert settings.hypotheses_models(' smollm2-135m , ') == ['smollm2-135m']


def test_the_hypotheses_mode_prepares_its_models_at_startup():
    from app.bootstrap.application import create_app

    class Store:
        def __init__(self):
            self.prepared = []

        def ensure(self, name):
            self.prepared.append(name)

    store = Store()
    create_app('sqlite://', ['.'], hypotheses='', model_store=store)
    assert store.prepared == []
    create_app('sqlite://', ['.'], hypotheses='smollm2-135m', model_store=store)
    assert store.prepared == ['smollm2-135m']


def test_the_smollm_adapter_scores_labels_from_logits(tmp_path):
    """Modele Llama minuscule et aleatoire, meme architecture que SmolLM2 ; tourne la ou torch est installe."""
    pytest.importorskip('torch')
    transformers = pytest.importorskip('transformers')
    from tokenizers import Tokenizer, models, pre_tokenizers
    from app.hypotheses.infrastructure.smollm import SmolLmHypothesisModel

    source = tmp_path / 'source'
    words = 'subject known unknown question labels answer public authenticated only restricted'.split()
    vocabulary = {'[UNK]': 0, '<s>': 1, '</s>': 2, **{word: index + 3 for index, word in enumerate(words)}}
    tokenizer = Tokenizer(models.WordLevel(vocabulary, unk_token='[UNK]'))
    tokenizer.pre_tokenizer = pre_tokenizers.Whitespace()
    transformers.PreTrainedTokenizerFast(tokenizer_object=tokenizer, unk_token='[UNK]', bos_token='<s>',
                                         eos_token='</s>').save_pretrained(source)
    config = transformers.LlamaConfig(vocab_size=len(vocabulary), hidden_size=16, intermediate_size=32,
                                      num_hidden_layers=1, num_attention_heads=2, num_key_value_heads=2)
    transformers.LlamaForCausalLM(config).save_pretrained(source)
    files = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in source.iterdir()}
    path = tmp_path / 'models.json'
    path.write_text(json.dumps({'tiny': {'family': 'llama', 'repository': 'local/tiny',
                                         'revision': 'r1', 'files': files}}))

    class Local:
        def download(self, url, destination):
            Path(destination).write_bytes((source / url.rsplit('/', 1)[-1]).read_bytes())

    model = SmolLmHypothesisModel.load(ModelStore(tmp_path / 'models', path, Local(), log=lambda m: None), 'tiny')
    assert model.identity.weights_sha256 == files['model.safetensors']
    assert model.identity.parameter_count > 0
    scores = model.score(REPRESENTATION)
    assert set(scores) == set(WHO_CAN_CALL.labels)
    assert abs(sum(scores.values()) - 1) < 1e-9
