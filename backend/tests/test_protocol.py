"""TAXO-QUERY-02 : les operations v1 du protocole Taxo (ADR 0009), sur les faits d'une analyse."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.bootstrap.database import Base
from app.main import create_app
from app.protocol.application.exchange import MAX_OPERATIONS, MIN_EXCHANGE_BYTES
from app.protocol.domain.envelope import MAX_ERROR_BYTES, OperationError, Response, error, size
from app.protocol.domain.verdict import (CONFIRMED, NOT_ANALYSED, NOT_FOUND_IN_ANALYSED_SCOPE,
                                         NOT_INTERPRETED, NOT_PROVEN, REFUTED, Analyzer, contains, judge)

AUTHOR = 'person:taxo@example.invalid'


@pytest.fixture(name='repo')
def repo_fixture(make_repo, git):
    repo = make_repo({'README.md': 'Taxo\n', 'src/app.txt': 'un\ndeux\ntrois\n'}, 'protocole')
    first = git(repo, 'rev-parse', 'HEAD')
    (repo / 'src/app.txt').write_text('un\nDEUX\ntrois\n')
    (repo / '.env').write_text('SECRET=1\n')
    git(repo, 'add', '-A')
    git(repo, 'commit', '-qm', 'change app')
    return repo, first, git(repo, 'rev-parse', 'HEAD')


def client_for(repo, tmp_path, source_context='off', analyse=True):
    tmp_path.mkdir(parents=True, exist_ok=True)
    app = create_app(f'sqlite:///{tmp_path / "protocol.db"}', [repo], minia={}, source_context=source_context)
    Base.metadata.create_all(app.state.engine)
    client = TestClient(app)
    project = client.post('/api/projects', json={'name': 'Protocole', 'path': str(repo)}).json()
    if analyse:
        client.post(f'/api/projects/{project["id"]}/scans')
    return client, f'/api/projects/{project["id"]}/taxo-query'


@pytest.fixture(name='taxo')
def taxo_fixture(repo, tmp_path):
    client, url = client_for(repo[0], tmp_path)
    with client:
        yield client, url, repo


def exchange(client, url, *requests, **options):
    body = {'requests': [{'operation': name, 'arguments': arguments} for name, arguments in requests], **options}
    response = client.post(url, json=body)
    assert response.status_code == 200, response.text
    return response.json()


def one(client, url, operation, **arguments):
    return exchange(client, url, (operation, arguments))['responses'][0]


def test_no_exchange_before_the_global_analysis(repo, tmp_path):
    client, url = client_for(repo[0], tmp_path, analyse=False)
    response = client.post(url, json={'requests': [{'operation': 'describe'}]})
    assert response.status_code == 409 and 'NO_ANALYSIS' in response.json()['detail']


def test_describe_offers_only_what_taxo_can_serve(taxo):
    client, url, _ = taxo
    result = exchange(client, url, ('describe', {}))
    described = result['responses'][0]
    assert described['protocol'] == 'taxo-query/1' and described['outcome'] == 'OK'
    operations = [item['operation'] for item in described['items'] if item['kind'] == 'operation']
    assert operations == ['describe', 'find_facts', 'get_evidence', 'get_coverage', 'get_commit', 'verify_claim',
                          'diff_facts']
    assert 'get_diff' not in operations, 'sans MINIA_SOURCE_CONTEXT=diff, le diff n est pas propose'
    analyzers = {item['analyzer'] for item in described['items'] if item['kind'] == 'analyzer'}
    assert analyzers == {'taxo.inventory', 'taxo.git'}
    changes = next(item for item in described['items'] if item.get('relation') == 'CHANGES')
    assert (changes['subject_types'], changes['object_types']) == (['commit'], ['file'])
    assert described['coverage'] and described['snapshot'] == result['snapshot']
    assert result['snapshot']['commit'] == taxo[2][2]


def test_find_facts_gives_short_references_stable_in_the_exchange(taxo):
    client, url, (_, _, second) = taxo
    pattern = {'subject': f'commit:{second}', 'relation': 'CHANGES'}
    result = exchange(client, url, ('find_facts', pattern), ('find_facts', pattern))
    first, again = result['responses']
    assert first['count'] == 2 and {item['fact']['object'] for item in first['items']} == {'file:src/app.txt',
                                                                                           'file:.env'}
    assert [item['ref'] for item in first['items']] == ['F1', 'F2']
    assert [item['ref'] for item in again['items']] == ['F1', 'F2'], 'un meme fait, une meme reference'
    assert 'evidence' not in first['items'][0]['fact'] and first['items'][0]['evidence_count'] == 1
    assert all(entry['producer'] == 'taxo.git' for entry in first['coverage'])
    assert first['coverage'][0]['type'] == 'ANALYSED', 'la couverture dit ou Taxo a cherche'
    assert first['bytes'] == size({**first, 'bytes': first['bytes']})


def test_an_empty_answer_still_says_where_taxo_looked(taxo):
    client, url, _ = taxo
    found = one(client, url, 'find_facts', relation='HANDLED_BY')
    assert (found['outcome'], found['items'], found['count']) == ('OK', [], 0)
    assert found['coverage'] == [{'subject': None, 'type': 'NOT_ANALYSED', 'scope': None, 'producer': None,
                                  'relation': 'HANDLED_BY'}]


@pytest.mark.parametrize('arguments', [{}, {'relation': 'INVENTED'}, {'subject': 'pas une reference'},
                                       {'nature': 'OPINION'}, {'relation': 'CHANGES', 'extra': 1}])
def test_invalid_arguments_are_refused_never_interpreted(taxo, arguments):
    client, url, _ = taxo
    refused = one(client, url, 'find_facts', **arguments)
    assert refused['outcome'] == 'ERROR' and refused['error']['code'] == 'INVALID_ARGUMENT'
    assert 'items' not in refused, 'une erreur ne porte aucun resultat'


def test_evidence_is_given_only_for_a_fact_received_in_the_exchange(taxo):
    client, url, (_, _, second) = taxo
    result = exchange(client, url, ('find_facts', {'subject': f'commit:{second}', 'relation': 'AUTHORED_BY'}),
                      ('get_evidence', {'fact': 'F1'}), ('get_evidence', {'fact': 'F9'}))
    _, evidence, unknown = result['responses']
    assert evidence['fact'] == 'F1' and evidence['items'] == []
    assert [(entry['ref'], entry['fact']) for entry in evidence['evidence']] == [('E1', 'F1')]
    assert evidence['evidence'][0]['location']['method'] == 'git.log'
    assert unknown['error']['code'] == 'INVALID_ARGUMENT'
    alone = exchange(client, url, ('get_evidence', {'fact': 'F1'}))['responses'][0]
    assert alone['error']['code'] == 'INVALID_ARGUMENT', 'les references ne survivent pas a l echange'


def test_coverage_can_be_asked_for_a_scope(taxo):
    client, url, _ = taxo
    everything = one(client, url, 'get_coverage')
    assert {item['fact']['produced_by']['producer_id'] for item in everything['items']} == {'taxo.inventory',
                                                                                          'taxo.git'}
    narrowed = one(client, url, 'get_coverage', scope='file:src/app.txt')
    assert narrowed['items'] == [] and narrowed['count'] == 0
    assert one(client, url, 'get_coverage', scope='rien')['error']['code'] == 'INVALID_ARGUMENT'


def test_get_commit_reads_git_facts_without_content(taxo):
    client, url, (_, first, second) = taxo
    commit = one(client, url, 'get_commit', commit=second[:8])
    assert commit['commit'] == f'commit:{second}'
    relations = [item['fact']['relation'] for item in commit['items']]
    assert relations[0] == 'HAS_COMMIT' and relations.count('CHANGES') == 2
    assert {'AUTHORED_BY', 'CHILD_OF'} <= set(relations)
    assert commit['items'][0]['fact']['qualifiers']['subject'] == 'change app'
    assert 'hunks' not in str(commit) and 'SECRET' not in str(commit)
    assert one(client, url, 'get_commit', commit='abcdef1')['error']['code'] == 'OUT_OF_SCOPE'
    assert one(client, url, 'get_commit', commit='xyz')['error']['code'] == 'INVALID_ARGUMENT'


def test_the_diff_needs_both_the_setting_and_the_exchange_consent(repo, tmp_path):
    client, url = client_for(repo[0], tmp_path / 'off')
    second = repo[2]
    with client:
        refused = one(client, url, 'get_diff', commit=second, path='src/app.txt')
        assert refused['error']['code'] == 'NO_CONSENT'
    client, url = client_for(repo[0], tmp_path / 'on', source_context='diff')
    with client:
        described = one(client, url, 'describe')
        assert 'get_diff' in [item.get('operation') for item in described['items']]
        assert described['consent'] == {'diff': False}
        refused = one(client, url, 'get_diff', commit=second, path='src/app.txt')
        assert refused['error']['code'] == 'NO_CONSENT', 'le reglage seul ne suffit pas'
        result = exchange(client, url, ('get_diff', {'commit': second, 'path': 'src/app.txt'}),
                          ('get_diff', {'commit': second, 'path': '.env'}),
                          ('get_diff', {'commit': second, 'path': 'README.md'}), consent={'diff': True})
        diff, secret, untouched = result['responses']
        assert diff['outcome'] == 'OK' and diff['status'] == 'MODIFIED'
        assert diff['items'] == [{'before_start': 1, 'after_start': 1, 'before': 'un\ndeux\ntrois',
                                  'after': 'un\nDEUX\ntrois'}]
        assert secret['items'] == [] and secret['path'] == '.env'
        assert secret['not_sent'] == [{'what': 'diff', 'reason': 'CONFIDENTIAL'}]
        assert 'SECRET' not in str(result)
        assert untouched['error']['code'] == 'OUT_OF_SCOPE'


def test_verify_claim_confirms_with_the_fact_and_its_evidence(taxo):
    client, url, (_, _, second) = taxo
    verdict = one(client, url, 'verify_claim', subject=f'commit:{second}', relation='CHANGES',
                  object='file:src/app.txt')
    assert (verdict['verdict'], verdict['reason']) == (CONFIRMED, None)
    assert verdict['claim'] == {'subject': f'commit:{second}', 'relation': 'CHANGES', 'object': 'file:src/app.txt'}
    assert [item['ref'] for item in verdict['items']] == ['F1']
    assert [entry['fact'] for entry in verdict['evidence']] == ['F1']


def test_verify_claim_refutes_only_on_an_exclusive_relation(taxo):
    client, url, (_, first, second) = taxo
    refuted = one(client, url, 'verify_claim', subject=f'commit:{second}', relation='AUTHORED_BY',
                  object='person:someone@example.invalid')
    assert refuted['verdict'] == REFUTED and refuted['items'][0]['fact']['object'] == AUTHOR
    assert refuted['evidence'], 'ce qui contredit est rendu avec ses preuves'
    missing = one(client, url, 'verify_claim', subject=f'commit:{first}', relation='CHANGES',
                  object='file:.env')
    assert (missing['verdict'], missing['reason']) == (NOT_PROVEN, NOT_FOUND_IN_ANALYSED_SCOPE), \
        'non trouve n est jamais faux'


def test_verify_claim_says_when_no_analyzer_covers_the_dimension(taxo):
    client, url, _ = taxo
    verdict = one(client, url, 'verify_claim', subject='endpoint:POST /items', relation='PROTECTED_BY',
                  object='policy-rule:R1')
    assert (verdict['verdict'], verdict['reason'], verdict['items']) == (NOT_PROVEN, NOT_ANALYSED, [])
    wrong = one(client, url, 'verify_claim', subject='file:a.txt', relation='CHANGES', object='file:b.txt')
    assert wrong['error']['code'] == 'INVALID_ARGUMENT'
    no_object = one(client, url, 'verify_claim', subject='commit:' + '0' * 40, relation='CHANGES')
    assert no_object['error']['code'] == 'INVALID_ARGUMENT'


def test_nothing_is_cut_in_the_middle_and_the_rest_is_counted(taxo):
    client, url, _ = taxo
    small = exchange(client, url, ('find_facts', {'relation': 'CHANGES'}))
    everything = small['responses'][0]
    limited = client.post(url, json={'requests': [{'operation': 'find_facts', 'arguments': {'relation': 'CHANGES'},
                                                   'max_bytes': everything['bytes'] - 1}]}).json()['responses'][0]
    assert limited['outcome'] == 'OK' and limited['bytes'] <= everything['bytes'] - 1
    assert len(limited['items']) == everything['count'] - 1
    assert limited['not_sent'] == [{'what': 'items', 'count': 1, 'reason': 'BUDGET'}]
    tiny = client.post(url, json={'requests': [{'operation': 'find_facts', 'arguments': {'relation': 'CHANGES'},
                                                'max_bytes': 50}]}).json()['responses'][0]
    assert tiny['error']['code'] == 'BUDGET_EXHAUSTED', 'la couverture obligatoire ne tient pas'


def test_the_exchange_budget_is_a_hard_limit_even_for_refusals(taxo):
    client, url, (_, _, second) = taxo
    requests = [{'operation': 'get_commit', 'arguments': {'commit': second}, 'max_bytes': 32_000}] * 5
    requests += [{'operation': 'x' * 100, 'arguments': {'y' * 900: 1}}] * 15
    result = client.post(url, json={'max_bytes': MIN_EXCHANGE_BYTES, 'requests': requests}).json()
    responses = result['responses']
    assert result['budget'] == {'max_bytes': MIN_EXCHANGE_BYTES, 'used': sum(item['bytes'] for item in responses)}
    assert result['budget']['used'] <= MIN_EXCHANGE_BYTES
    assert all(item['bytes'] <= MAX_ERROR_BYTES for item in responses if item['outcome'] == 'ERROR')
    assert responses[5]['operation'] is None, 'un nom arbitraire n est jamais renvoye tel quel'
    too_small = client.post(url, json={'max_bytes': 1500, 'requests': [{'operation': 'describe'}]})
    assert too_small.status_code == 422
    too_many = client.post(url, json={'requests': [{'operation': 'describe'}] * 21})
    assert too_many.status_code == 422


def test_an_exchange_closes_after_its_last_operation(repo, tmp_path):
    client, _ = client_for(repo[0], tmp_path)
    with client:
        project = client.get('/api/projects').json()[0]
        opened = client.app.state.taxo_query.open(project['id'])
        for _ in range(MAX_OPERATIONS):
            opened.call({'operation': 'describe'})
        with pytest.raises(RuntimeError):
            opened.call({'operation': 'describe'})


def test_another_repository_is_out_of_scope(taxo):
    client, url, _ = taxo
    for operation, arguments in (('get_coverage', {'scope': 'repository:ailleurs'}),
                                 ('find_facts', {'subject': 'repository:ailleurs'}),
                                 ('verify_claim', {'subject': 'repository:ailleurs', 'relation': 'CONTAINS',
                                                   'object': 'file:a.txt'})):
        assert one(client, url, operation, **arguments)['error']['code'] == 'OUT_OF_SCOPE'


@pytest.mark.parametrize('relation, target', [('AUTHORED_BY', 'file:x'), ('AUTHORED_BY', 'quelqu’un'),
                                              ('CHANGES', 'commit:' + '1' * 40)])
def test_a_claim_object_must_have_the_type_the_relation_admits(taxo, relation, target):
    client, url, (_, _, second) = taxo
    refused = one(client, url, 'verify_claim', subject=f'commit:{second}', relation=relation, object=target)
    assert refused['error']['code'] == 'INVALID_ARGUMENT', 'jamais un verdict sur une affirmation mal formee'


def test_diff_facts_gives_what_a_commit_changes_according_to_taxo(make_repo, git, tmp_path):
    repo = make_repo({'README.md': 'Taxo\n'}, 'impact')
    (repo / 'main.py').write_text('print(1)\n')
    git(repo, 'add', '-A')
    git(repo, 'commit', '-qm', 'ajoute main.py')
    sha, parent = git(repo, 'rev-parse', 'HEAD'), git(repo, 'rev-parse', 'HEAD~1')
    client, url = client_for(repo, tmp_path)
    with client:
        changed = one(client, url, 'diff_facts', commit=sha[:9])
        assert (changed['outcome'], changed['commit'], changed['parent']) == ('OK', f'commit:{sha}', f'commit:{parent}')
        written = next(item for item in changed['items'] if item['relation'] == 'WRITTEN_IN')
        assert (written['kind'], written['change'], written['subject'], written['after']) == (
            'change', 'INTRODUCED', 'file:main.py', 'language:Python')
        assert written['producer'] == 'taxo.inventory' and written['evidence'][0]['path'] == 'main.py'
        assert 'ref' not in written, 'un changement n est pas un fait de l analyse'
        assert changed['coverage'][0]['producer'] == 'taxo.inventory'
        assert one(client, url, 'diff_facts', commit='abcdef1')['error']['code'] == 'OUT_OF_SCOPE'


def test_reserved_and_unknown_operations_are_said(taxo):
    client, url, _ = taxo
    result = exchange(client, url, ('find_callers', {'symbol': 'symbol:x'}), ('drop_tables', {}))
    reserved, unknown = result['responses']
    assert reserved['error']['code'] == 'NOT_AVAILABLE'
    assert unknown['error']['code'] == 'INVALID_ARGUMENT'
    wrong = client.post(url, json={'protocol': 'taxo-query/2', 'requests': [{'operation': 'describe'}]})
    assert wrong.status_code == 422


def test_scopes_contain_what_they_name():
    assert contains('repository:x', 'file:a/b.txt') and contains('directory:a', 'file:a/b.txt')
    assert not contains('directory:a', 'file:ab/c.txt') and not contains('file:a', 'file:a/b')
    assert contains('file:a/b.txt', 'file:a/b.txt')
    assert contains('repository:x', 'repository:x') and not contains('repository:x', 'repository:y')


def coverage(subject, kind, include=('repository:r',), exclude=()):
    return {'subject': subject, 'coverage_type': kind, 'scope': {'include': list(include), 'exclude': list(exclude)}}


CLAIM = {'subject': 'file:node_modules/x.js', 'relation': 'WRITTEN_IN', 'object': 'language:JavaScript'}


def test_an_excluded_scope_is_not_analysed_and_a_failed_analyzer_is_not_interpreted():
    excluded = Analyzer('a', frozenset({'WRITTEN_IN'}),
                        coverage=(coverage('repository:r', 'ANALYSED', exclude=['directory:node_modules']),))
    assert judge(CLAIM, [], [excluded]).reason == NOT_ANALYSED
    failed = Analyzer('a', frozenset({'WRITTEN_IN'}), failed=True,
                      coverage=(coverage('repository:r', 'NOT_INTERPRETED'),))
    assert judge(CLAIM, [], [failed]).reason == NOT_INTERPRETED
    unreadable = Analyzer('a', frozenset({'WRITTEN_IN'}),
                          coverage=(coverage('repository:r', 'ANALYSED'),
                                    coverage('file:node_modules/x.js', 'READ_ERROR')))
    assert judge(CLAIM, [], [unreadable]).reason == NOT_INTERPRETED


def test_a_confirmed_claim_wins_over_a_contradiction():
    analyzer = Analyzer('a', frozenset({'WRITTEN_IN'}), coverage=(coverage('repository:r', 'ANALYSED'),))
    same = {'subject': CLAIM['subject'], 'relation': 'WRITTEN_IN', 'object': 'language:JavaScript'}
    other = {**same, 'object': 'language:TypeScript'}
    assert judge(CLAIM, [other, same], [analyzer]).verdict == CONFIRMED
    assert judge(CLAIM, [other], [analyzer]).verdict == REFUTED


def test_a_refusal_note_counts_in_the_budget():
    response = Response('get_diff', {'analysis': 'a', 'commit': None}, [], 300, path='p' * 150)
    with pytest.raises(OperationError) as refused:
        response.not_sent({'what': 'diff', 'reason': 'CONFIDENTIAL', 'note': 'n' * 100})
    assert refused.value.code == 'BUDGET_EXHAUSTED'


def test_an_error_never_exceeds_its_bound():
    refused = error('get_evidence', {'analysis': 'a' * 36, 'commit': 'c' * 64}, 'INVALID_ARGUMENT', 'é' * 5000)
    assert refused['bytes'] <= MAX_ERROR_BYTES and refused['error']['message'].endswith('…')


def test_a_response_never_exceeds_its_budget():
    response = Response('find_facts', {'analysis': 'a', 'commit': None}, [], 300)
    added = sum(response.add('items', {'ref': f'F{index}', 'text': 'x' * 40}) for index in range(20))
    closed = response.close()
    assert closed['bytes'] <= 300 and len(closed['items']) == added < 20
    assert closed['not_sent'] == [{'what': 'items', 'count': 20 - added, 'reason': 'BUDGET'}]


# Critere de revue de l'ADR 0009 : aucune operation du coeur ne nomme une technologie ou un projet.
_TECHNOLOGIES = ('java', 'spring', 'python', 'typescript', 'javascript', 'react', 'maven', 'gradle', 'django',
                 'kotlin', 'hibernate', 'express', 'angular', 'dotnet')


def test_the_protocol_names_no_language_framework_or_project():
    source = Path(__file__).parents[1] / 'app' / 'protocol'
    text = ' '.join(path.read_text(encoding='utf-8').lower() for path in source.rglob('*.py'))
    assert [name for name in _TECHNOLOGIES if name in text] == []
