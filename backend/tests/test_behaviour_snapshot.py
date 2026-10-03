"""Instantane du comportement public, pour prouver qu'une restructuration ne change rien (TAXO-ARCH-REF-01).

Desactive par defaut : il ne verifie rien seul. Il ecrit les reponses publiques de Taxo sur plusieurs scenarios
(protocole et ses refus, historique et diff, restitution `/coverage`, comparaison), normalisees pour etre
deterministes, dans le fichier que nomme
`TAXO_BEHAVIOUR_SNAPSHOT`. La preuve est la comparaison de deux instantanes : l'un sur la base, l'autre sur la
branche. Procedure : docs/backlog/TAXO-ARCH-REF-01-assainissement-architectural.md, § « Preuve de non-regression ».
"""
import json
import os
import re

import pytest
from fastapi.testclient import TestClient

from app.bootstrap.database import Base
from app.main import create_app
from test_coverage_bounds import PYTHON, legacy, taxo_on_fixture  # noqa: F401  (fixture partagee)
from test_knowledge_divergences import forget_catalogs, retire_contract
from conftest import run_git
from test_spring_boot import controller, repository

OUTPUT = os.environ.get('TAXO_BEHAVIOUR_SNAPSHOT')
pytestmark = pytest.mark.skipif(not OUTPUT, reason='instantane a la demande : TAXO_BEHAVIOUR_SNAPSHOT=<fichier>')

# Ce qui change d'une execution a l'autre sans rien dire du comportement : identifiants, dates, empreintes.
_IDENTIFIER = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}')
_DIGEST = re.compile(r'\b[0-9a-f]{40,64}\b')
_TIMESTAMP = re.compile(r'\d{4}-\d{2}-\d{2}T[0-9:.+]+Z?')

QUERIES = [('describe', {}),
           ('verify_claim', {'subject': 'endpoint:GET /missing', 'relation': 'HANDLED_BY',
                             'object': 'symbol:java:x#y()'}),
           ('verify_claim', {'subject': 'endpoint:GET /api/health', 'relation': 'HANDLED_BY',
                             'object': 'symbol:python:api.main#health'}),
           ('verify_claim', {'subject': 'file:api/main.py', 'relation': 'WRITTEN_IN', 'object': 'language:Python'}),
           ('get_coverage', {}),
           ('find_facts', {'relation': 'HANDLED_BY'})]
ROOTS = ('endpoint:GET /orders', 'endpoint:GET /api/health', 'endpoint:GET /status')


def normalized(value):
    text = json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
    identifiers = {}
    text = _IDENTIFIER.sub(lambda found: identifiers.setdefault(found.group(0), f'<id{len(identifiers)}>'), text)
    return json.loads(_TIMESTAMP.sub('<ts>', _DIGEST.sub('<h>', text)))


def observed(taxo, scan):
    neighborhoods = [('get_neighborhood', {'analysis': scan, 'root': root, 'follow': ['HANDLED_BY'],
                                           'direction': 'OUTGOING'}) for root in ROOTS]
    return {'query': taxo.ask(*QUERIES, *neighborhoods, analysis=scan),
            'coverage': taxo.client.get(f'{taxo.base}/scans/{scan}/coverage').json()}


def add_controller(root):
    path = root / 'shop-app/src/main/java/com/acme/web/StatusController.java'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(controller('com.acme.web', 'StatusController', '/status'))


def add_module(root):
    (root / 'api/admin.py').write_text('from api.main import app\n')


def forget_languages(taxo, before, after):
    taxo.forget_languages(before)
    taxo.forget_languages(after)


def forget_both_catalogs(taxo, before, after):
    forget_catalogs(taxo, before)
    forget_catalogs(taxo, after)


def retire_api(taxo, *_):
    retire_contract(taxo, 'taxo.spring-api')


def forget_catalogs_and_retire_boot(taxo, before, after):
    forget_both_catalogs(taxo, before, after)
    retire_contract(taxo, 'taxo.spring-boot')


def forget_earlier_languages(taxo, before, _):
    taxo.forget_languages(before)


MIXED = {**repository(), **PYTHON}
# nom : (depot, changement entre les deux analyses, alteration des analyses enregistrees, moteur d'avant COV-01)
SCENARIOS = {
    'java': (repository(), add_controller, None, False),
    'python': (PYTHON, add_module, None, False),
    'mixed': (MIXED, add_module, None, False),
    'mixed_forgot_languages': (MIXED, add_module, forget_languages, False),
    'mixed_forgot_catalogs': (MIXED, add_module, forget_both_catalogs, False),
    'mixed_retired': (MIXED, add_module, retire_api, False),
    'mixed_forgot_catalogs_retired': (MIXED, add_module, forget_catalogs_and_retire_boot, False),
    'python_legacy_engine': (PYTHON, add_module, forget_earlier_languages, True),
}


def scenario(taxo_on, git, monkeypatch, files, change, alter, earlier_engine):
    with monkeypatch.context() as patch:
        if earlier_engine:
            legacy(patch)
        taxo, root = taxo_on(files)
        before = taxo.analyse()['id']
        change(root)
        git(root, 'add', '-A')
        git(root, 'commit', '-qm', 'change')
        after = taxo.analyse()['id']
    if alter:
        alter(taxo, before, after)
    compared = taxo.client.get(f'{taxo.base}/comparisons', params={'before': before, 'after': after}).json()
    return {'before': observed(taxo, before), 'after': observed(taxo, after), 'compare': compared}


def requests(*operations):
    return [operation if isinstance(operation, dict) else {'operation': operation[0], 'arguments': operation[1]}
            for operation in operations]


def exchange(client, base, consent, *operations):
    body = {'requests': requests(*operations), 'consent': {'diff': consent}}
    return client.post(f'{base}/taxo-query', json=body).json()


def protocol(make_repo, git, tmp_path):
    """Les operations d'historique et du diff, et chaque refus du protocole, sur un Taxo qui lit le diff."""
    root = make_repo(MIXED)
    add_module(root)
    (root / 'README.md').write_text('Un service HTTP en Python, et ses routes Java.\n')
    git(root, 'add', '-A')
    git(root, 'commit', '-qm', 'change')
    head = git(root, 'rev-parse', 'HEAD')
    app = create_app(f'sqlite:///{tmp_path / "protocol.db"}', [root], minia={}, source_context='diff')
    Base.metadata.create_all(app.state.engine)
    with TestClient(app) as client:
        project = client.post('/api/projects', json={'name': root.name, 'path': str(root)}).json()
        base = f'/api/projects/{project["id"]}'
        scan = client.post(f'{base}/scans').json()['id']
        history = exchange(client, base, True, ('describe', {}), ('get_commit', {'commit': head}),
                           ('get_commit', {'commit': head[:7]}), ('diff_facts', {'commit': head}),
                           ('get_diff', {'commit': head, 'path': 'api/admin.py'}),
                           ('get_diff', {'commit': head, 'path': 'README.md'}),
                           ('get_diff', {'commit': head, 'path': 'pom.xml'}),
                           ('get_commit', {'commit': 'zzzzzzz'}), ('get_commit', {'commit': '0000000'}))
        refused = exchange(client, base, True, ('find_callers', {}), ('nope', {}),
                           {'operation': 'describe', 'protocol': 'other'},
                           {'operation': 'describe', 'max_bytes': 0}, ('describe', {'x': 1}),
                           ('get_evidence', {'fact': 'F999'}), ('find_facts', {}),
                           ('find_facts', {'relation': 'NOT_A_RELATION'}),
                           ('verify_claim', {'subject': 'repository:other', 'relation': 'CONTAINS',
                                             'object': 'file:a.py'}),
                           ('verify_claim', {'subject': 'file:a.py', 'relation': 'HANDLED_BY'}),
                           ('get_neighborhood', {'analysis': 'other', 'root': 'endpoint:GET /orders',
                                                 'follow': ['HANDLED_BY'], 'direction': 'OUTGOING'}),
                           {'operation': 'describe', 'max_bytes': 200})
        without_consent = exchange(client, base, False, ('get_diff', {'commit': head, 'path': 'api/admin.py'}))
        ask = {'requests': requests(('get_neighborhood', {'analysis': scan, 'root': 'endpoint:GET /orders',
                                                          'follow': ['HANDLED_BY'], 'direction': 'OUTGOING'}))}
        neighborhood = client.post(f'{base}/taxo-query', json=ask).json()
    return {'history': history, 'refused': refused, 'without_consent': without_consent,
            'neighborhood': neighborhood}


def without_diff(taxo_on):
    """Un Taxo qui ne lit pas le diff : l'operation est refusee, pas absente."""
    taxo, root = taxo_on(PYTHON)
    taxo.analyse()
    head = run_git(root, 'rev-parse', 'HEAD')
    return taxo.client.post(f'{taxo.base}/taxo-query', json={
        'requests': requests(('get_diff', {'commit': head, 'path': 'api/main.py'}), ('describe', {})),
        'consent': {'diff': True}}).json()


def test_behaviour_snapshot(taxo_on, git, monkeypatch, make_repo, tmp_path):
    result = {name: scenario(taxo_on, git, monkeypatch, *case) for name, case in SCENARIOS.items()}
    result['protocol'] = protocol(make_repo, git, tmp_path)
    result['without_diff'] = without_diff(taxo_on)
    with open(OUTPUT, 'w', encoding='utf-8') as handle:
        json.dump(normalized(result), handle, sort_keys=True, ensure_ascii=False, indent=1)
    with open(OUTPUT, encoding='utf-8') as handle:
        assert sorted(json.load(handle)) == sorted([*SCENARIOS, 'protocol', 'without_diff']), \
            'chaque scenario est dans l instantane'
