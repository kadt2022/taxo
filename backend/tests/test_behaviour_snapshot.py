"""Instantane du comportement public, pour prouver qu'une restructuration ne change rien (TAXO-ARCH-REF-01).

Desactive par defaut : il ne verifie rien seul. Il ecrit les reponses publiques de Taxo sur plusieurs scenarios
(protocole, restitution `/coverage`, comparaison), normalisees pour etre deterministes, dans le fichier que nomme
`TAXO_BEHAVIOUR_SNAPSHOT`. La preuve est la comparaison de deux instantanes : l'un sur la base, l'autre sur la
branche. Procedure : docs/backlog/TAXO-ARCH-REF-01-assainissement-architectural.md, § « Preuve de non-regression ».
"""
import json
import os
import re

import pytest

from test_coverage_bounds import PYTHON, legacy, taxo_on_fixture  # noqa: F401  (fixture partagee)
from test_knowledge_divergences import forget_catalogs, retire_contract
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


def test_behaviour_snapshot(taxo_on, git, monkeypatch):
    result = {name: scenario(taxo_on, git, monkeypatch, *case) for name, case in SCENARIOS.items()}
    with open(OUTPUT, 'w', encoding='utf-8') as handle:
        json.dump(normalized(result), handle, sort_keys=True, ensure_ascii=False, indent=1)
    with open(OUTPUT, encoding='utf-8') as handle:
        assert sorted(json.load(handle)) == sorted(SCENARIOS), 'chaque scenario est dans l instantane'
