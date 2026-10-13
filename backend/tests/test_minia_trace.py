"""Le journal de développement des échanges (MINIA_TRACE) : désactivé par défaut ; `summary` dit chaque opération de
Taxo et chaque tour du modèle ; `full` y ajoute les messages complets. Le message journalisé est celui qui part vers le
modèle, après protection : un secret masqué l'est aussi dans le journal."""
import io

import pytest

from app.bootstrap import settings
from app.minia.application import trace
from test_minia_explore import ScriptedModel, answer, call, completed, repo_fixture, run, statement  # noqa: F401


@pytest.fixture(name='journal')
def journal_fixture():
    out = io.StringIO()
    yield out
    trace.configure(trace.OFF)


def traced(mode, journal, monkeypatch):
    """Le journal tel que le serveur le configure au démarrage, écrit dans `journal`."""
    monkeypatch.setenv('MINIA_TRACE', mode)
    original = trace.configure
    monkeypatch.setattr(trace, 'configure', lambda value, stream=None: original(value, journal))


def test_the_journal_is_off_by_default(monkeypatch):
    monkeypatch.delenv('MINIA_TRACE', raising=False)
    assert settings.minia_trace() == 'off'


def test_an_unknown_level_is_refused():
    with pytest.raises(ValueError, match='MINIA_TRACE'):
        trace.configure('bavard')


def test_off_writes_nothing(repo, tmp_path, journal, monkeypatch):
    traced('off', journal, monkeypatch)
    run(repo[0], tmp_path, ScriptedModel(call('find_facts', relation='CHANGES'), answer(statement('unknown', 'Rien.'))))
    assert journal.getvalue() == ''


def test_summary_says_each_taxo_operation_and_each_model_turn(repo, tmp_path, journal, monkeypatch):
    traced('summary', journal, monkeypatch)
    result = completed(run(repo[0], tmp_path, ScriptedModel(call('find_facts', relation='CHANGES'),
                                                            answer(statement('unknown', 'Rien.')))))
    said = journal.getvalue()
    assert result['mode'] == 'exploration'
    assert 'TAXO describe' in said and 'TAXO find_facts {"relation": "CHANGES"} -> OK' in said
    assert said.count('LLM -> scripted/scripted-1') == 2 and said.count('LLM <- scripted/scripted-1') == 2
    assert 'LLM message :' not in said and 'TAXO réponse :' not in said, 'summary ne recopie pas les messages'


def test_full_adds_the_messages_as_sent_and_the_answers(repo, tmp_path, journal, monkeypatch):
    traced('full', journal, monkeypatch)
    run(repo[0], tmp_path, ScriptedModel(call('find_facts', relation='CHANGES'), answer(statement('unknown', 'Rien.'))))
    said = journal.getvalue()
    assert 'TAXO réponse :' in said and 'LLM consignes :' in said and 'LLM message :' in said
    assert '"calls_left"' in said, 'le message complet, tel que le modèle le reçoit'


def test_the_journal_never_sees_more_than_the_model(repo, tmp_path, journal, monkeypatch):
    """L'auteur du commit est pseudonymisé avant le modèle : il l'est aussi dans le journal."""
    traced('full', journal, monkeypatch)
    run(repo[0], tmp_path, ScriptedModel(call('find_facts', relation='AUTHORED_BY'), answer(statement('unknown', 'Rien.'))))
    said = journal.getvalue()
    assert 'person:personne-1' in said
    assert 'taxo@example.invalid' not in said.split('TAXO réponse :')[0].split('LLM message :')[-1]
    assert all('taxo@example.invalid' not in line for line in said.splitlines() if line.startswith('[minia-trace] LLM'))


def test_a_streamed_answer_keeps_what_the_stream_returns():
    def pieces():
        yield 'a'
        yield 'b'
        return 'modèle-réel'

    out = io.StringIO()
    trace.configure(trace.SUMMARY, out)
    try:
        stream = trace.streamed(ScriptedModel(), pieces())
        said = []
        while True:
            try:
                said.append(next(stream))
            except StopIteration as end:
                assert end.value == 'modèle-réel'
                break
        assert said == ['a', 'b'] and 'LLM <- scripted/scripted-1 : 2 octets : ab' in out.getvalue()
    finally:
        trace.configure(trace.OFF)
