"""`verify_claim` sur un symbole : il est situé dans le fichier qui le déclare, et seuls les langages de ce fichier
comptent pour dire « non trouvé là où Taxo a lu ». Avant, un sujet symbole n'était situé nulle part : quand
l'inventaire n'avait pas tout lu (cas réel de `student-course-demo`), la réponse disait à tort « aucun analyseur ne
couvre encore cette dimension » pour une annotation que l'analyseur Java avait bien lue, sous un autre nom."""
import pytest
from fastapi.testclient import TestClient

from app.bootstrap.database import Base
from app.main import create_app
from app.protocol.application.exchange import Exchange

CONTROLLER = 'symbol:java:com.acme.web.Orders'
ENROLL = f'{CONTROLLER}#create(Long)'
FILES = {
    'src/main/java/com/acme/web/Orders.java': '\n'.join([
        'package com.acme.web;',
        '',
        'import org.springframework.web.bind.annotation.*;',
        '',
        '@RestController',
        'public class Orders {',
        '    @PostMapping("/orders")',
        '    public String create(Long id) {',
        '        return "ok";',
        '    }',
        '}',
        '']),
    'src/main/resources/application.yml': 'server:\n  port: 8080\n',
}


@pytest.fixture(name='taxo')
def taxo_fixture(make_repo, tmp_path, monkeypatch):
    # L'inventaire n'a pas tout lu : sans fichier qui situe le sujet, des langages présents peuvent manquer.
    monkeypatch.setattr(Exchange, 'complete', property(lambda self: False))
    repo = make_repo(FILES, 'portee')
    app = create_app(f'sqlite:///{tmp_path / "portee.db"}', [repo], minia={})
    Base.metadata.create_all(app.state.engine)
    with TestClient(app) as client:
        project = client.post('/api/projects', json={'name': 'Portée', 'path': str(repo)}).json()
        client.post(f'/api/projects/{project["id"]}/scans')
        yield client, f'/api/projects/{project["id"]}/taxo-query'


def verify(taxo, subject, relation, target):
    client, url = taxo
    body = {'requests': [{'operation': 'verify_claim',
                          'arguments': {'subject': subject, 'relation': relation, 'object': target}}]}
    return client.post(url, json=body).json()['responses'][0]


def test_an_annotation_written_under_another_name_is_not_found_where_taxo_read(taxo):
    """Taxo garde `annotation:PostMapping` (import `*`) : la forme qualifiée n'est pas établie, mais le fichier Java a
    été lu ; ce n'est pas une dimension que personne n'analyse."""
    response = verify(taxo, ENROLL, 'ANNOTATED_WITH', 'annotation:org.springframework.web.bind.annotation.PostMapping')
    assert response['verdict'] == 'NOT_PROVEN'
    assert response['reason'] == 'NOT_FOUND_IN_ANALYSED_SCOPE'


def test_the_name_taxo_holds_is_confirmed(taxo):
    assert verify(taxo, ENROLL, 'ANNOTATED_WITH', 'annotation:PostMapping')['verdict'] == 'CONFIRMED'


def test_a_file_without_an_established_language_keeps_the_scope_unknown(taxo, monkeypatch):
    """Le symbole est situé, mais aucun `WRITTEN_IN` ne dit le langage de son fichier : rien ne change."""
    original = Exchange.query

    def without_languages(self, **criteria):
        return [] if criteria.get('relation') == 'WRITTEN_IN' else original(self, **criteria)
    monkeypatch.setattr(Exchange, 'query', without_languages)
    response = verify(taxo, ENROLL, 'ANNOTATED_WITH', 'annotation:org.springframework.web.bind.annotation.PostMapping')
    assert response['reason'] == 'NOT_ANALYSED'


def test_a_symbol_taxo_cannot_place_in_a_file_keeps_the_whole_repository_scope(taxo):
    """Sans déclaration qui le situe, rien ne change : tous les langages présents comptent."""
    response = verify(taxo, 'symbol:java:com.acme.web.Absent#m()', 'ANNOTATED_WITH', 'annotation:PostMapping')
    assert response['verdict'] == 'NOT_PROVEN'
    assert response['reason'] == 'NOT_ANALYSED'
