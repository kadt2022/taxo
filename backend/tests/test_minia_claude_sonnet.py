"""Un second modèle Claude à côté du premier : même adaptateur, même clé, même contrat ; seuls l'identifiant du
fournisseur et le modèle changent. Le fournisseur Claude existant ne change pas."""
from app.bootstrap import settings
from app.bootstrap.application import minia_models
from app.minia.infrastructure.claude import ClaudeModel, ClaudeSonnetModel


def test_both_claude_models_are_offered_side_by_side(monkeypatch):
    monkeypatch.setenv('MINIA_CLAUDE_MODEL', 'claude-haiku-4-5-20251001')
    monkeypatch.setenv('MINIA_CLAUDE_SONNET_MODEL', 'claude-sonnet-5-5')
    models = minia_models(settings.minia())
    assert (models['claude'].provider, models['claude'].model_name) == ('claude', 'claude-haiku-4-5-20251001')
    assert (models['claude-sonnet'].provider, models['claude-sonnet'].model_name) == (
        'claude-sonnet', 'claude-sonnet-5-5')


def test_the_second_model_is_off_without_its_own_setting(monkeypatch):
    monkeypatch.setenv('MINIA_CLAUDE_MODEL', 'claude-haiku-4-5-20251001')
    monkeypatch.delenv('MINIA_CLAUDE_SONNET_MODEL', raising=False)
    assert 'claude-sonnet' not in minia_models(settings.minia())


def test_the_second_model_alone_does_not_enable_the_first_one(monkeypatch):
    monkeypatch.delenv('MINIA_CLAUDE_MODEL', raising=False)
    monkeypatch.setenv('MINIA_CLAUDE_SONNET_MODEL', 'claude-sonnet-5-5')
    models = minia_models(settings.minia())
    assert 'claude' not in models and 'claude-sonnet' in models


def test_the_second_model_is_the_same_adapter_with_the_same_protections():
    sonnet = ClaudeSonnetModel('claude-sonnet-5-5')
    assert isinstance(sonnet, ClaudeModel)
    assert sonnet.remote is True and sonnet.explores is True
    assert ClaudeModel.provider == 'claude' and ClaudeSonnetModel.provider == 'claude-sonnet'


def test_the_second_model_can_be_the_default_provider(monkeypatch):
    monkeypatch.setenv('MINIA_CLAUDE_SONNET_MODEL', 'claude-sonnet-5-5')
    assert 'claude-sonnet' in minia_models(settings.minia(provider='claude-sonnet'))
