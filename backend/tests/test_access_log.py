"""Le journal d'acces ne recopie jamais la question, ni aucune valeur d'adresse (TAXO-MINIA-SEC-01, E4)."""
import logging

from app.platform.api.access_log import RedactedQueries, redact_access_log, redacted

QUESTION = 'Qui est Ada Lovelace ? password=admin123'


def _record(path):
    # Le message tel qu'uvicorn l'emet : (client, methode, chemin, version HTTP, statut).
    return logging.LogRecord('uvicorn.access', logging.INFO, __file__, 1, '%s - "%s %s HTTP/%s" %d',
                             ('127.0.0.1:5000', 'GET', path, '1.1', 200), None)


def test_a_query_keeps_its_parameter_names_never_their_values():
    assert redacted('/api/projects/p/query?q=Ada%20Lovelace&limit=3') == '/api/projects/p/query?q=******&limit=******'
    assert redacted('/api/projects/p/elements?q=') == '/api/projects/p/elements?q=******'
    assert redacted('/api/health') == '/api/health'
    assert redacted('/api/x?opaque') == '/api/x?opaque=******'


def test_the_access_log_never_writes_the_question(caplog):
    logger = logging.getLogger('test.access')
    logger.addFilter(RedactedQueries())
    with caplog.at_level(logging.INFO, logger='test.access'):
        logger.handle(_record(f'/api/projects/p/elements?q={QUESTION}'))
    assert 'Lovelace' not in caplog.text
    assert 'admin123' not in caplog.text
    assert 'GET /api/projects/p/elements?q=****** HTTP/1.1' in caplog.text


def test_a_record_of_another_shape_passes_unchanged():
    record = logging.LogRecord('uvicorn.access', logging.INFO, __file__, 1, 'démarrage', None, None)
    assert RedactedQueries().filter(record)
    assert record.getMessage() == 'démarrage'


def test_the_filter_is_installed_once():
    logger = logging.getLogger('test.access.once')
    redact_access_log(logger)
    redact_access_log(logger)
    assert sum(isinstance(item, RedactedQueries) for item in logger.filters) == 1


def test_the_application_installs_it_on_the_uvicorn_access_log(tmp_path):
    from app.main import create_app
    create_app(f'sqlite:///{tmp_path / "taxo.db"}', [str(tmp_path)], minia={})
    assert any(isinstance(item, RedactedQueries) for item in logging.getLogger('uvicorn.access').filters)
