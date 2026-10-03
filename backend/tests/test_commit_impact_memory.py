"""TAXO-01F, tranche E : l'impact d'un commit depuis la memoire, sans relire le depot.

Le banc est un depot Git scenarise. La verite de chaque commit est ecrite ici a la main, a partir de ce que le
commit change dans le code : elle ne vient d'aucun calcul de Taxo. Les deux chemins (memoire et relecture) sont
chacun confrontes a cette verite, puis l'un a l'autre ; l'egalite seule ne suffirait pas, les deux chemins
pourraient partager la meme erreur.
"""
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy.orm import Session

from app.comparison.domain.comparison import NOT_SUPPORTED_AFTER, NOT_SUPPORTED_BEFORE, REASONS
from app.history.application.recorded import MEMORY, REREAD, RecordedImpact, _evaluation
from app.scans.infrastructure.sqlalchemy.scan_repository import ScanRow
from test_coverage_bounds import PYTHON, taxo_on_fixture  # noqa: F401  (fixture partagee)
from test_knowledge_divergences import retire_contract

API = 'taxo.spring-api'
CONTROLLER = 'src/main/java/com/acme/web/OrderController.java'
SYMBOL = 'symbol:java:com.acme.web.OrderController#'
ORDERS, COUNT = 'endpoint:GET /orders', 'endpoint:GET /orders/count'


def source(*methods, comment=''):
    """Un controleur Spring : chaque methode est (route, nom)."""
    body = ''.join(f'    @GetMapping("{route}")\n    public String {name}() {{ return ""; }}\n'
                   for route, name in methods)
    return ('package com.acme.web;\n\nimport org.springframework.web.bind.annotation.GetMapping;\n'
            'import org.springframework.web.bind.annotation.RestController;\n\n'
            f'@RestController\npublic class OrderController {{\n{comment}{body}}}\n')


# Un fichier Java illisible, present dans tout le scenario : une zone que les analyseurs Java n'interpretent pas.
BROKEN = 'src/main/java/com/acme/web/Broken.java'
START = {CONTROLLER: source(('/orders', 'list')), 'build.gradle': "plugins { id 'org.springframework.boot' }\n",
         BROKEN: 'package com.acme.web;\npublic class Broken { public String x( { }\n'}
MOVED = '    // Les commandes.\n    // Lecture seule.\n    // Sans effet.\n'
# Le scenario : chaque commit, son contenu, et ce qu'il change pour l'analyseur d'API, ecrit a la main.
SCENARIO = (
    ('renomme le gestionnaire et ajoute un compte', source(('/orders', 'all'), ('/orders/count', 'count')),
     {('MODIFIED', ORDERS, f'{SYMBOL}list()', f'{SYMBOL}all()'), ('INTRODUCED', COUNT, None, f'{SYMBOL}count()')},
     0),
    # Trois lignes ajoutees au-dessus des deux methodes : leurs preuves se deplacent, aucun fait ne change.
    ('deplace le code', source(('/orders', 'all'), ('/orders/count', 'count'), comment=MOVED), set(), 2),
    ('retire le compte', source(('/orders', 'all'), comment=MOVED), {('REMOVED', COUNT, f'{SYMBOL}count()', None)}, 1),
)


@pytest.fixture(name='bench')
def bench_fixture(taxo_on, git):
    taxo, root = taxo_on(START)
    commits = [git(root, 'rev-parse', 'HEAD')]
    for message, content, _, _ in SCENARIO:
        (root / CONTROLLER).write_text(content)
        git(root, 'commit', '-qam', message)
        commits.append(git(root, 'rev-parse', 'HEAD'))
    return taxo, root, commits


def impact(taxo, sha, **params):
    response = taxo.client.get(f'{taxo.base}/history/commits/{sha}/impact', params=params)
    assert response.status_code == 200, response.text
    return response.json()


def by_evaluator(found):
    return {item['evaluator_id']: item for item in found['evaluations']}


def api_changes(found):
    return {(item['change'], item['subject'], item['before'], item['after'])
            for item in by_evaluator(found)[API]['changes'] if item['relation'] == 'HANDLED_BY'}


def analyse_all(taxo, commits):
    return {sha: taxo.analyse(sha)['id'] for sha in commits}


def test_both_paths_find_the_changes_written_by_hand(bench):
    taxo, _, commits = bench
    reread = {sha: impact(taxo, sha) for sha in commits[1:]}
    analyses = analyse_all(taxo, commits)
    for (message, _, expected, unchanged), parent, sha in zip(SCENARIO, commits, commits[1:]):
        remembered = impact(taxo, sha)
        assert reread[sha]['source'] == REREAD
        assert remembered['source'] == MEMORY
        assert remembered['analyses']['before']['id'] == analyses[parent]
        assert remembered['analyses']['after']['id'] == analyses[sha]
        for found in (reread[sha], remembered):
            assert api_changes(found) == expected, f'{message} ({found["source"]})'
            assert by_evaluator(found)[API]['unchanged_count'] == unchanged, message
            unread = by_evaluator(found)[API]
            assert unread['not_interpreted_before'] == unread['not_interpreted_after'] == [f'file:{BROKEN}']


def test_memory_and_reread_agree_wherever_both_compare(bench):
    """Au-dela de la verite ecrite a la main (l'analyseur d'API), chaque evaluateur comparable des deux cotes
    rend les memes changements, preuves comprises, et le meme nombre de faits inchanges."""
    taxo, _, commits = bench
    reread = {sha: by_evaluator(impact(taxo, sha)) for sha in commits[1:]}
    analyse_all(taxo, commits)
    compared = 0
    for sha in commits[1:]:
        for identifier, remembered in by_evaluator(impact(taxo, sha)).items():
            other = reread[sha][identifier]
            if remembered['comparable'] and other['comparable']:
                compared += 1
                for key in ('changes', 'unchanged_count', 'not_interpreted_before', 'not_interpreted_after',
                            'status_before', 'status_after'):
                    assert remembered[key] == other[key], f'{sha[:7]} {identifier} {key}'
    assert compared >= len(SCENARIO) * 2, 'le banc compare effectivement plusieurs evaluateurs'


def test_a_moved_evidence_is_seen_by_the_comparison_but_stays_unchanged_in_the_impact(bench):
    taxo, _, commits = bench
    analyses = analyse_all(taxo, commits)
    before, after = commits[1], commits[2]  # « deplace le code »
    counts = taxo.compare(analyses[before], analyses[after])[API]['counts']
    assert counts['EVIDENCE_CHANGED'] == 2, 'la comparaison voit les deux preuves deplacees'
    assert counts['MODIFIED'] == 0
    found = by_evaluator(impact(taxo, after))[API]
    assert found['changes'] == [], "l'impact n'en fait aucun MODIFIED"
    assert found['unchanged_count'] == 2


def test_the_memory_path_opens_no_snapshot_and_runs_no_evaluator(bench, monkeypatch):
    taxo, _, commits = bench
    analyse_all(taxo, commits)

    def forbidden(*_args, **_kwargs):
        raise AssertionError('le depot a ete relu')
    monkeypatch.setattr('app.snapshots.infrastructure.git.reader.GitSnapshotReader.open', forbidden)
    monkeypatch.setattr('app.evaluations.application.run_evaluator.RunEvaluator.__call__', forbidden)
    assert api_changes(impact(taxo, commits[3])) == SCENARIO[2][2]


def test_without_both_analyses_the_repository_is_reread_and_the_answer_says_so(bench):
    taxo, _, commits = bench
    taxo.analyse(commits[1])  # le commit seul : son parent n'a pas d'analyse
    found = impact(taxo, commits[1])
    assert found['source'] == REREAD
    assert found['analyses'] == {'before': {'kind': 'REREAD', 'id': None, 'commit': commits[0], 'created_at': None},
                                 'after': {'kind': 'REREAD', 'id': None, 'commit': commits[1], 'created_at': None}}
    root = impact(taxo, commits[0])
    assert root['source'] == REREAD, 'un commit sans parent'
    assert root['analyses']['before'] is None


def test_the_most_recent_complete_commit_analysis_of_each_exact_commit_is_chosen(bench):
    taxo, _, commits = bench
    parent, sha = commits[2], commits[3]
    first, kept = taxo.analyse(parent)['id'], taxo.analyse(sha)['id']
    latest = taxo.analyse(parent)['id']
    taxo.client.post(f'{taxo.base}/scans', params={'mode': 'working-tree'})  # le meme commit, pas en mode COMMIT
    newest = taxo.analyse(sha)['id']
    with Session(taxo.engine) as db:  # une consolidation interrompue n'est pas une analyse
        row = db.get(ScanRow, newest)
        row.result = {**row.result, 'memory': 'INCOMPLETE'}
        db.commit()
    found = impact(taxo, sha)
    assert (found['analyses']['before']['id'], found['analyses']['after']['id']) == (latest, kept)
    assert first != latest


def test_equal_dates_are_decided_by_the_identifier():
    at = datetime(2026, 10, 3, tzinfo=timezone.utc)

    def scan(identifier, commit, mode='COMMIT'):
        return SimpleNamespace(id=identifier, created_at=at,
                               result={'evaluation_summary': {'snapshot': {'commit': commit, 'mode': mode}}})
    scans = SimpleNamespace(list=lambda project: [scan('b', 'c'), scan('a', 'c'), scan('z', 'p'),
                                                  scan('zz', 'p', 'WORKING_TREE')])
    before, after = RecordedImpact(scans, None).pair('project', 'c', 'p')
    assert (before.id, after.id) == ('z', 'b')


def test_an_explicit_pair_is_used_as_named(bench):
    taxo, _, commits = bench
    parent, sha = commits[0], commits[1]
    older = taxo.analyse(parent)['id']
    taxo.analyse(parent)
    named = taxo.analyse(sha)['id']
    found = impact(taxo, sha, before=older, after=named)
    assert found['source'] == MEMORY
    assert (found['analyses']['before']['id'], found['analyses']['after']['id']) == (older, named)
    assert api_changes(found) == SCENARIO[0][2]


def test_an_incompatible_explicit_pair_is_refused_and_never_reread(bench, taxo_on):
    taxo, _, commits = bench
    parent, sha = commits[0], commits[1]
    before, after = taxo.analyse(parent)['id'], taxo.analyse(sha)['id']
    other, _ = taxo_on(PYTHON)
    elsewhere = other.analyse()['id']
    url = f'{taxo.base}/history/commits/{sha}/impact'
    cases = {
        'inversees': ({'before': after, 'after': before}, 422, 'INCOMPATIBLE_ANALYSES'),
        'une seule': ({'before': before}, 422, 'INCOMPATIBLE_ANALYSES'),
        "d'un autre commit": ({'before': before, 'after': taxo.analyse(commits[2])['id']}, 422,
                              'INCOMPATIBLE_ANALYSES'),
        'inconnue': ({'before': before, 'after': 'nope'}, 404, 'UNKNOWN_ANALYSIS'),
        "d'un autre projet": ({'before': before, 'after': elsewhere}, 404, 'UNKNOWN_ANALYSIS'),
    }
    for name, (params, status, code) in cases.items():
        response = taxo.client.get(url, params=params)
        assert response.status_code == status, name
        assert response.json()['detail'].startswith(code), name
    root = taxo.client.get(f'{taxo.base}/history/commits/{parent}/impact', params={'before': before, 'after': before})
    assert root.status_code == 422, 'un commit sans parent : aucune analyse ne peut etre celle du parent'


def test_an_analyzer_with_nothing_to_read_is_never_an_absence_of_change(taxo_on, git):
    """Un depot Python : l'analyseur d'API Java n'avait rien a lire. Relu, il « ne voit rien changer » ; depuis la
    memoire, il n'est pas comparable, et la reponse dit pourquoi."""
    taxo, root = taxo_on(PYTHON)
    parent = git(root, 'rev-parse', 'HEAD')
    (root / 'api/main.py').write_text(PYTHON['api/main.py'] + '\n@app.get("/api/version")\ndef version():\n'
                                      '    return {}\n')
    git(root, 'commit', '-qam', 'version')
    sha = git(root, 'rev-parse', 'HEAD')
    reread = by_evaluator(impact(taxo, sha))[API]
    assert (reread['comparable'], reread['changes']) == (True, [])
    taxo.analyse(parent)
    taxo.analyse(sha)
    remembered = by_evaluator(impact(taxo, sha))[API]
    assert remembered['comparable'] is False
    assert remembered['reason'] == NOT_SUPPORTED_BEFORE
    assert remembered['failures'] == [REASONS[NOT_SUPPORTED_BEFORE]]
    assert remembered['changes'] == []


def test_a_reason_keeps_the_recorded_warnings_of_a_failed_execution():
    found = {'reason': NOT_SUPPORTED_AFTER, 'message': REASONS[NOT_SUPPORTED_AFTER],
             'unread': {'before': [], 'after': []}}
    before = {API: {'status': 'FAILED', 'warnings': ['lecture impossible'], 'producer_version': '1'}}
    after = {API: {'status': 'UNSUPPORTED', 'producer_version': '2'}}
    result = _evaluation(API, found, before, after)
    assert result['failures'] == [REASONS[NOT_SUPPORTED_AFTER], 'lecture impossible']
    recorded = (result['status_before'], result['status_after'], result['producer_version'])
    assert recorded == ('FAILED', 'UNSUPPORTED', '2')


def test_every_consumer_of_the_impact_reads_the_memory(bench):
    taxo, _, commits = bench
    sha = commits[1]
    reread = taxo.client.get(f'{taxo.base}/history/commits/{sha}/diff/facts', params={'path': CONTROLLER}).json()
    analyses = analyse_all(taxo, commits)
    linked = taxo.client.get(f'{taxo.base}/history/commits/{sha}/diff/facts', params={'path': CONTROLLER}).json()
    assert (reread['source'], linked['source']) == (REREAD, MEMORY)
    assert linked['facts'] == reread['facts'], 'les memes faits relies aux memes lignes du diff'
    assert {(item['change'], item['subject']) for item in linked['facts'] if item['evaluator_id'] == API} == {
        ('MODIFIED', ORDERS), ('INTRODUCED', COUNT)}
    protocol, = taxo.ask(('diff_facts', {'commit': sha}), analysis=analyses[commits[-1]])
    assert protocol['source'] == MEMORY
    assert protocol['analyses'] == {'before': analyses[commits[0]], 'after': analyses[sha]}


def test_a_non_comparable_evaluator_still_names_the_zones_it_could_not_interpret(bench):
    """Ne pas comparer les faits ne fait pas oublier ce que chaque analyse n'a pas interprete : la relecture le
    dit, la memoire aussi. Ici le contrat de catalogue enregistre n'est plus connu : aucun fait n'est compare."""
    taxo, _, commits = bench
    analyse_all(taxo, commits)
    retire_contract(taxo, API)
    found = by_evaluator(impact(taxo, commits[1]))[API]
    assert found['comparable'] is False
    assert found['not_interpreted_before'] == found['not_interpreted_after'] == [f'file:{BROKEN}']
