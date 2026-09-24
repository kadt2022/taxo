"""CLOCHETTE LAB : une conversation locale, hors produit, qui ne produit aucun fait."""
import hashlib
import json
from pathlib import Path

import pytest

from app.hypotheses.infrastructure.model_store import ModelStore, ModelStoreError
from lab import clochette_chat as lab

APP = Path(__file__).parents[1] / 'app'
REVISION = 'b' * 40


def test_the_product_never_imports_the_lab():
    for path in APP.rglob('*.py'):
        source = path.read_text(encoding='utf-8')
        assert 'from lab' not in source and 'import lab' not in source, path


def test_only_the_recent_history_is_kept():
    history = [{'role': 'user', 'content': str(index)} for index in range(20)]
    assert lab.recent(history) == history[-2 * lab.HISTORY_TURNS:]


def test_the_chat_uses_only_the_instruct_model_never_the_lab_01_model():
    assert lab.MODEL == 'smollm2-135m-instruct'
    assert lab.verified_directory.__defaults__ == ('smollm2-135m-instruct',)


def test_the_official_chat_template_is_mandatory():
    class Tokenizer:
        chat_template = None

    with pytest.raises(ModelStoreError, match='chat template'):
        lab.require_chat_template(Tokenizer())
    Tokenizer.chat_template = '{{ messages }}'
    assert lab.require_chat_template(Tokenizer()).chat_template


def cache(tmp_path, content=b'weights'):
    directory = tmp_path / 'cache' / lab.MODEL / REVISION
    directory.mkdir(parents=True)
    (directory / 'model.safetensors').write_bytes(content)
    manifest = tmp_path / 'models.json'
    manifest.write_text(json.dumps({lab.MODEL: {
        'family': 'smollm2-instruct', 'repository': 'HuggingFaceTB/SmolLM2-135M-Instruct', 'revision': REVISION,
        'files': {'model.safetensors': hashlib.sha256(b'weights').hexdigest()}}}))
    return manifest


class NoNetwork:
    def download(self, url, destination):
        pytest.fail('Le laboratoire ne telecharge jamais')


def test_an_intact_cache_gives_the_pinned_revision(tmp_path):
    store = ModelStore(tmp_path / 'cache', cache(tmp_path), NoNetwork())
    assert lab.verified_directory(store).name == REVISION


def test_an_altered_cache_is_refused_without_download(tmp_path):
    store = ModelStore(tmp_path / 'cache', cache(tmp_path, b'altered'), NoNetwork())
    with pytest.raises(ModelStoreError, match='model.safetensors corrupt'):
        lab.verified_directory(store)


class EchoClochette:
    def __init__(self, directory):
        self.seen = []

    def reply(self, history):
        self.seen.append(len(history))
        return f'echo {history[-1]["content"]}'


def test_a_conversation_has_several_turns_a_reset_and_an_exit(monkeypatch, tmp_path):
    monkeypatch.setenv('TAXO_MODELS_DIR', str(tmp_path / 'cache'))
    lines = iter(['Bonjour Clochette', '', "Comment tu t'appelles ?", '/reset', 'Encore', '/quit'])
    written, models = [], []

    def factory(directory):
        models.append(EchoClochette(directory))
        return models[-1]

    assert lab.main(['--manifest', str(cache(tmp_path))], read=lambda prompt: next(lines),
                    write=written.append, model_factory=factory) == 0
    assert written[0] == lab.BANNER
    assert 'pas des faits Taxo' in written[0] and '/quit' in written[0]
    assert 'Clochette > echo Bonjour Clochette\n' in written
    assert "Clochette > echo Comment tu t'appelles ?\n" in written
    assert '(historique vidé)' in written
    assert models[0].seen == [1, 3, 1], "le deuxieme tour voit l'historique, /reset le vide"


def test_end_of_input_leaves_cleanly(monkeypatch, tmp_path):
    monkeypatch.setenv('TAXO_MODELS_DIR', str(tmp_path / 'cache'))

    def closed(prompt):
        raise EOFError

    assert lab.main(['--manifest', str(cache(tmp_path))], read=closed, write=lambda text: None,
                    model_factory=EchoClochette) == 0


def test_a_missing_cache_stops_before_loading(monkeypatch, tmp_path):
    monkeypatch.setenv('TAXO_MODELS_DIR', str(tmp_path / 'empty'))
    written = []

    def forbidden(directory):
        pytest.fail('Aucun modele ne se charge sans cache verifie')

    assert lab.main(['--manifest', str(cache(tmp_path))], write=written.append, model_factory=forbidden) == 1
    assert 'fetch' in written[0]


def test_a_tokenizer_without_chat_template_stops_the_chat(monkeypatch, tmp_path):
    monkeypatch.setenv('TAXO_MODELS_DIR', str(tmp_path / 'cache'))
    written = []

    def without_template(directory):
        raise ModelStoreError('Le tokenizer ne fournit pas de chat template : conversation refusee.')

    assert lab.main(['--manifest', str(cache(tmp_path))], read=lambda prompt: pytest.fail('aucun tour'),
                    write=written.append, model_factory=without_template) == 1
    assert 'chat template' in written[-1]


def test_both_models_stay_separate_in_the_manifest():
    from app.hypotheses.infrastructure.model_store import MANIFEST_PATH

    models = json.loads(MANIFEST_PATH.read_text())
    assert models['smollm2-135m']['repository'] == 'HuggingFaceTB/SmolLM2-135M'
    assert models['smollm2-135m']['revision'] == '93efa2f097d58c2a74874c7e644dbc9b0cee75a2'
    assert models['smollm2-135m-instruct']['repository'] == 'HuggingFaceTB/SmolLM2-135M-Instruct'
    assert 'LAB-01' in models['smollm2-135m-instruct']['usage']
