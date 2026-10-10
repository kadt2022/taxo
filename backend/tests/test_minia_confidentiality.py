"""TAXO-MINIA-SEC-01, E3 : ce qui part vers un fournisseur de modele est protege dans une couche unique ;
Taxo garde localement les valeurs d'origine et repond lui-meme a « qui est l'auteur ? »."""
import json

import pytest
from fastapi.testclient import TestClient

from app.bootstrap.database import Base
from app.main import create_app
from app.minia.application.protected_model import ProtectedModel
from app.minia.domain.authorship import asks_author
from app.minia.domain.confidentiality import MASK, Disclosure
from app.minia.domain.errors import CONFIDENTIALITY_REFUSED, MiniaError

NAME, EMAIL = 'Ada Lovelace', 'ada@example.org'
FORBIDDEN = (NAME, 'Lovelace', EMAIL, 'admin123', 's3cr3t-value', 'Co-authored-by', 'bob@example.org')


def protect(payload, disclosure=None):
    return json.loads((disclosure or Disclosure()).protect(json.dumps(payload, ensure_ascii=False)))


def authored(email=EMAIL, name=NAME, sha='abc'):
    return {'subject': f'commit:{sha}', 'relation': 'AUTHORED_BY', 'object': f'person:{email}',
            'qualifiers': {'name': name}}


# La representation controlee ------------------------------------------------------------------------------

def test_an_author_becomes_one_pseudonym_wherever_it_appears():
    sent = protect({'question': f'Qu’a fait Ada, alias {EMAIL} ?', 'commit': {'author': NAME},
                    'facts': [authored()]})
    assert sent['facts'][0]['object'] == 'person:personne-1'
    assert sent['facts'][0]['qualifiers']['name'] == 'personne-1'
    assert sent['commit']['author'] == 'personne-1'
    assert sent['question'] == 'Qu’a fait personne-1, alias personne-1 ?'


def test_an_identity_written_in_another_case_is_the_same_person():
    sent = protect({'facts': [authored()], 'message': 'merci à ADA LOVELACE et à ada lovelace', 'question': 'Et Lovelace ?'})
    assert sent['message'] == 'merci à personne-1 et à personne-1'
    assert sent['question'] == 'Et personne-1 ?'


def test_two_people_sharing_a_first_name_keep_two_pseudonyms():
    sent = protect({'facts': [authored(), authored('ada.b@example.org', 'Ada Byron', 'def')]})
    assert [fact['object'] for fact in sent['facts']] == ['person:personne-1', 'person:personne-2']


def test_pseudonyms_belong_to_one_request():
    first, second = Disclosure(), Disclosure()
    protect({'facts': [authored('x@example.org', 'Xavier Dupont')]}, first)
    assert protect({'facts': [authored()]}, second)['facts'][0]['object'] == 'person:personne-1'


def test_commit_trailers_are_removed_and_unknown_emails_masked():
    disclosure = Disclosure()
    sent = protect({'message': 'fix: corrige\n\nCo-authored-by: Bob <bob@example.org>\nSigned-off-by: X <x@y.org>\n',
                    'diff': 'contact: carol@example.org'}, disclosure)
    assert sent['message'] == 'fix: corrige'
    assert sent['diff'] == 'contact: personne-1'
    assert disclosure.report() == {'identities': 1, 'secrets': 0, 'trailers': 2}


def test_only_the_final_trailer_paragraph_of_a_message_is_removed():
    source = 'spring:\n  data:\n    order-by: created_at\n    cc: ops\nport: 8080'
    assert protect({'source': source})['source'] == source, 'une ligne de fichier n’est pas un trailer'


def test_same_named_authors_with_different_addresses_keep_two_pseudonyms():
    disclosure = Disclosure()
    sent = protect({'facts': [authored(), authored(email='ada@other.org', sha='def')]}, disclosure)
    assert [fact['object'] for fact in sent['facts']] == ['person:personne-1', 'person:personne-2']
    assert disclosure.restore('person:personne-2') == 'person:ada@other.org'


def test_same_named_authors_keep_their_own_pseudonym_as_name():
    sent = protect({'facts': [authored(), authored(email='ada@other.org', sha='def')]})
    assert [fact['qualifiers']['name'] for fact in sent['facts']] == ['personne-1', 'personne-2']


@pytest.mark.parametrize('line', [
    'password: correct horse battery staple',
    '- password: correct horse battery staple',
    'spring.datasource.password=correct horse battery staple',
])
def test_a_plain_secret_of_several_words_is_masked_whole(line):
    key = line.split('correct')[0]
    assert protect({'source': f'{line}\nport: 8080'})['source'] == f'{key}{MASK}\nport: 8080'


def test_a_plain_secret_keeps_its_end_of_line_comment():
    assert protect({'source': 'password: two words # rotate'})['source'] == f'password: {MASK} # rotate'


@pytest.mark.parametrize('source', [
    'password: "correct\n  horse"\nport: 8080',
    "password: 'correct\n  horse'\nport: 8080",
    'password: "correct \\\n  horse"\nport: 8080',
])
def test_a_quoted_secret_continued_on_the_next_lines_is_masked_whole(source):
    quote = source[len('password: ')]
    assert protect({'source': source})['source'] == f'password: {quote}{MASK}{quote}\nport: 8080'


def test_an_unterminated_quoted_secret_is_masked_to_the_end():
    assert protect({'source': 'password: "correct\n  horse'})['source'] == f'password: "{MASK}"'
    assert protect({'source': 'token = "correct'})['source'] == f'token = {MASK}'


@pytest.mark.parametrize('source', [
    "password: 'correct ''horse'' battery'\nport: 8080",
    'password: correct\n  horse battery\nport: 8080',
    'password: "correct # not a comment"\nport: 8080',
    'password:\n  correct horse\nport: 8080',
])
def test_every_form_of_a_yaml_secret_value_is_masked_whole(source):
    sent = protect({'source': source})['source']
    assert 'horse' not in sent and 'correct' not in sent, sent
    assert sent.endswith('\nport: 8080'), 'les entrées sœurs restent'


def test_a_yaml_secret_keeps_its_name_and_quote_style():
    assert protect({'source': "- token: 'a ''b'''"})['source'] == f"- token: '{MASK}'"


@pytest.mark.parametrize('address', ['josé@exemple.fr', 'john!doe@example.com', 'ana@münchen.de'])
def test_an_address_is_masked_whole_even_when_international(address):
    assert protect({'text': f'écrire à {address} demain'}) == {'text': 'écrire à personne-1 demain'}


def test_a_code_line_is_not_a_plain_secret():
    line = 'password = encoder.encode(raw, salt);'
    assert protect({'source': line})['source'] == line


def test_a_yaml_secret_block_in_a_sequence_ends_at_its_siblings():
    source = '- password: |\n    secret\n  port: 8080'
    assert protect({'source': source})['source'] == f'- password: {MASK}\n  port: 8080'


def test_a_yaml_secret_block_is_masked_across_blank_lines():
    sent = protect({'source': 'password: |\n  first\n\n  second\nport: 8080'})['source']
    assert sent == f'password: {MASK}\nport: 8080'


def test_a_yaml_secret_block_ends_where_its_indentation_ends():
    nested = 'database:\n  password: |2-\n    secret\n\n    more\n  port: 8080'
    assert protect({'source': nested})['source'] == f'database:\n  password: {MASK}\n  port: 8080'


def test_a_masked_password_still_shows_that_a_password_is_hardcoded():
    code = ('private String password = "admin123";\n'
            'spring.datasource.password=s3cr3t-value\n'
            'User.withUsername("u").password("admin123")\n'
            'db:\n  password: admin123\n')
    sent = protect({'diff': code})['diff']
    assert 'admin123' not in sent and 's3cr3t-value' not in sent
    assert f'password = "{MASK}"' in sent, 'le constat « mot de passe codé en dur » reste visible'
    assert f'spring.datasource.password={MASK}' in sent
    assert f'.password("{MASK}")' in sent and f'password: {MASK}' in sent


def test_placeholders_variables_and_calls_are_not_secrets():
    code = ('password=${DB_PASSWORD}\nString hash = encoder.encode(password);\nuser.password(encoded)\n'
            'token: null\npassword = encoder.encode(raw)\n')
    assert protect({'diff': code})['diff'] == code


@pytest.mark.parametrize('secret', [
    'AKIAABCDEFGHIJKLMNOP', 'ghp_' + 'a' * 36, 'sk-ant-' + 'b' * 24, 'xoxb-1234567890-abcdef',
    'eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U',
    '-----BEGIN RSA PRIVATE KEY-----\nMIIEow\n-----END RSA PRIVATE KEY-----'])
def test_secrets_of_known_shape_are_masked(secret):
    assert protect({'diff': f'cle {secret} fin'})['diff'] == f'cle {MASK} fin'


def test_credentials_in_a_url_are_masked():
    sent = protect({'diff': 'url=jdbc:postgresql://admin:hunter2@db:5432/app'})['diff']
    assert sent == f'url=jdbc:postgresql://{MASK}:{MASK}@db:5432/app'


def test_taxo_references_keep_their_names():
    sent = protect({'facts': [authored(), {'subject': 'file:src/Lovelace.java', 'relation': 'CONTAINS',
                                           'object': 'class:demo.Lovelace'}]})
    assert sent['facts'][1] == {'subject': 'file:src/Lovelace.java', 'relation': 'CONTAINS',
                                'object': 'class:demo.Lovelace'}, 'une référence de Taxo reste citable'


def test_a_known_author_named_without_any_fact_is_protected_by_whole_forms_only():
    disclosure = Disclosure(known=[f'{NAME} <{EMAIL}>'])
    sent = protect({'question': f'Qu’a changé {NAME.upper()} ?', 'code': 'class Ada {}'}, disclosure)
    assert sent == {'question': 'Qu’a changé personne-1 ?', 'code': 'class Ada {}'}, \
        'un mot isolé d’un nom connu reste un mot du code'
    assert protect({'code': 'taxo.java-calls'}, Disclosure(known=['taxo'])) == {'code': 'taxo.java-calls'}, \
        'un nom d’un seul mot ressemble à un mot du code'


def test_an_address_without_a_dotted_domain_is_still_an_address():
    sent = protect({'text': 'alerte envoyée à root@localhost'})
    assert sent == {'text': 'alerte envoyée à personne-1'}


def test_multiline_and_escaped_secrets_are_masked_entirely():
    config = 'password: |\n  admin123\n  suite\nport: 8080\ntoken = "ab\\"cd"'
    sent = protect({'source': config})['source']
    assert sent == f'password: {MASK}\nport: 8080\ntoken = "{MASK}"'


def test_a_reference_is_restored_only_if_protection_changed_it():
    disclosure = Disclosure()
    sent = protect({'facts': [authored()], 'files': ['file:docs/personne-1.md', f'file:notes/{EMAIL}']}, disclosure)
    assert sent['files'][0] == 'file:docs/personne-1.md'
    assert disclosure.restore(sent['files']) == ['file:docs/personne-1.md', f'file:notes/{EMAIL}'], \
        'une référence de Taxo n’est jamais réécrite avec un nom'


def test_a_message_of_unexpected_shape_is_refused():
    with pytest.raises(MiniaError) as refused:
        Disclosure().protect('texte libre adressé à ada@example.org')
    assert refused.value.code == CONFIDENTIALITY_REFUSED
    assert EMAIL not in str(refused.value), 'le refus ne divulgue pas la valeur'


def test_what_the_model_returns_is_restored_locally():
    disclosure = Disclosure()
    protect({'facts': [authored()]}, disclosure)
    assert disclosure.restore({'object': 'person:personne-1', 'text': 'personne-1 a écrit le commit.',
                               'other': ['personne-9', 3]}) == {
        'object': f'person:{EMAIL}', 'text': f'{NAME} a écrit le commit.', 'other': ['personne-9', 3]}


@pytest.mark.parametrize('question', [
    'Qui est l’auteur de ce commit ?', 'Qui est l\'auteur ?', 'Qui a écrit les 2 derniers commits ?',
    'Quels sont les auteurs des 3 derniers commits ?', 'Who is the author?', 'Who wrote this commit?',
    'Qui est l’auteur du commit abc1234 ?'])
def test_an_explicit_author_question_is_recognised(question):
    assert asks_author(question)


@pytest.mark.parametrize('question', [
    'Qui a fait échouer les tests ?', 'Who did this change affect?', 'Que change ce commit selon son auteur ?',
    'Quel risque apporte ce commit ?', 'Qui appelle CourseService.register ?',
    'Who authored this commit and what security impact did it have?', 'Qui est l’auteur et pourquoi ?'])
def test_a_question_that_only_mentions_an_author_stays_with_minia(question):
    assert not asks_author(question), 'l’intention de la question n’est jamais écartée'


# Le seul passage vers un fournisseur ----------------------------------------------------------------------

class Recorder:
    provider, model_name, remote, explores = 'enregistreur', 'r-1', True, True

    def __init__(self, reply='{}'):
        self.reply, self.calls = reply, []

    def complete(self, system, user, schema=None):
        self.calls.append(user)
        return self.reply

    def capacity(self, system):
        return 1000


def test_the_protected_model_is_the_model_with_protected_messages():
    inner = Recorder()
    model = ProtectedModel(inner, Disclosure())
    assert (model.provider, model.model_name, model.remote, model.explores) == ('enregistreur', 'r-1', True, True)
    assert model.capacity('consignes') == 1000
    assert not hasattr(model, 'stream'), 'un fournisseur sans diffusion le reste'
    model.complete('consignes', json.dumps({'question': f'Et {EMAIL} ?'}))
    assert EMAIL not in inner.calls[0] and 'personne-1' in inner.calls[0]


def test_a_streaming_model_streams_protected_messages():
    class Streaming(Recorder):
        def stream(self, system, user, cancel=None):
            self.calls.append(user)
            yield 'morceau'
    inner = Streaming()
    model = ProtectedModel(inner, Disclosure())
    assert list(model.stream('consignes', json.dumps({'diff': 'password="admin123"'}))) == ['morceau']
    assert inner.calls == [json.dumps({'diff': f'password="{MASK}"'}, separators=(',', ':'))]


# De bout en bout : ce que les fournisseurs recoivent reellement ---------------------------------------------

class CapturingModel:
    """Un fournisseur qui garde chaque message recu : la charge reellement envoyee."""

    provider, model_name = 'capture', 'capture-1'

    def __init__(self, *replies):
        self.replies, self.calls = list(replies), []

    def complete(self, system, user, schema=None):
        self.calls.append(user)
        return self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]


@pytest.fixture(name='leaky')
def leaky_fixture(make_repo, git):
    repo = make_repo({'src/Config.java': 'class Config {}\n'}, 'confidentiel')
    (repo / 'src' / 'Config.java').write_text(
        'class Config {\n  private String password = "admin123";\n  // contact bob@example.org\n}\n')
    git(repo, 'add', '-A')
    git(repo, '-c', f'user.name={NAME}', '-c', f'user.email={EMAIL}', 'commit', '-qm',
        'feat: configuration token=s3cr3t-value')
    return repo, git(repo, 'rev-parse', 'HEAD')


def open_client(tmp_path, repo, model, source='off'):
    app = create_app(f'sqlite:///{tmp_path / "confidentiel.db"}', [repo], minia=model, source_context=source)
    Base.metadata.create_all(app.state.engine)
    client = TestClient(app)
    project = client.post('/api/projects', json={'name': 'Confidentiel', 'path': str(repo)}).json()
    return client, project['id']


def test_nothing_forbidden_reaches_the_provider_and_the_answer_names_the_author_locally(leaky, tmp_path):
    repo, sha = leaky
    model = CapturingModel(json.dumps({'cited': [], 'unknown': '',
                                       'answer': 'personne-1 aurait ajouté un mot de passe écrit en dur.'}))
    client, project = open_client(tmp_path, repo, model, source='diff')
    with client:
        result = client.post(f'/api/projects/{project}/history/commits/{sha}/ask',
                             json={'question': 'Quel risque apporte ce commit ?', 'source_context': True}).json()
    assert result['status'] == 'ANSWERED' and model.calls
    for sent in model.calls:
        assert not [value for value in FORBIDDEN if value in sent], sent
    assert f'password = \\"{MASK}\\"' in model.calls[0], 'le constat de sécurité survit au masquage'
    assert result['answer'] == f'{NAME} aurait ajouté un mot de passe écrit en dur.'
    assert result['git']['author'] == NAME, 'Taxo garde localement la valeur d’origine'
    assert result['withheld']['identities'] >= 1 and result['withheld']['secrets'] >= 2


def test_taxo_answers_who_wrote_a_commit_without_any_model(leaky, tmp_path):
    repo, sha = leaky
    model = CapturingModel('{}')
    client, project = open_client(tmp_path, repo, model)
    with client:
        result = client.post(f'/api/projects/{project}/history/commits/{sha}/ask',
                             json={'question': 'Qui est l’auteur de ce commit ?'}).json()
    assert model.calls == [], 'aucune identité ne part vers un fournisseur'
    assert (result['mode'], result['status']) == ('taxo', 'ANSWERED')
    assert result['answer'] == f'Selon Git, l’auteur du commit {sha[:12]} est {NAME}.'


def test_taxo_answers_who_wrote_a_selection_of_commits_without_any_model(leaky, tmp_path):
    repo, sha = leaky
    model = CapturingModel('{}')
    client, project = open_client(tmp_path, repo, model)
    with client:
        client.post(f'/api/projects/{project}/scans')
        result = client.post(f'/api/projects/{project}/ask',
                             json={'question': 'Qui a écrit les 2 derniers commits ?'}).json()
    assert model.calls == []
    assert (result['mode'], result['status']) == ('taxo', 'ANSWERED')
    assert f'{sha[:12]} : {NAME}' in result['answer']
    assert {fact['relation'] for fact in result['facts']} == {'AUTHORED_BY'}
    assert f'person:{EMAIL}' in {fact['object'] for fact in result['facts']}


def test_in_exploration_taxo_receives_the_original_references(leaky, tmp_path):
    repo, sha = leaky

    def call(operation, **arguments):
        return json.dumps({'action': 'call', 'operation': operation, 'arguments': json.dumps(arguments),
                           'statements': []})
    claim = {'type': 'claim', 'text': 'personne-1 a écrit ce commit.', 'subject': f'commit:{sha}',
             'relation': 'AUTHORED_BY', 'object': 'person:personne-1'}
    model = CapturingModel(call('get_commit', commit=sha),
                           call('find_facts', relation='AUTHORED_BY', object='person:personne-1'),
                           json.dumps({'action': 'answer', 'operation': '', 'arguments': '',
                                       'statements': [claim]}))
    model.explores = True
    client, project = open_client(tmp_path, repo, model)
    with client:
        client.post(f'/api/projects/{project}/scans')
        stream = client.post(f'/api/projects/{project}/ask/stream', json={'question': 'Que change ce projet ?'})
    events = [json.loads(block.split('\n')[1][len('data: '):]) for block in stream.text.strip().split('\n\n')
              if block.startswith('event: minia.completed')]
    [result] = events
    found = next(step for step in result['trajectory'] if step['operation'] == 'find_facts')
    assert found['arguments']['object'] == f'person:{EMAIL}' and found['items'] >= 1
    [statement] = result['statements']
    assert statement['verdict'] == 'CONFIRMED' and statement['text'] == f'{NAME} a écrit ce commit.'
    for sent in model.calls:
        assert NAME not in sent and EMAIL not in sent


def test_a_project_question_naming_an_author_does_not_send_the_name(leaky, tmp_path):
    repo, _ = leaky
    model = CapturingModel(json.dumps({'cited': [], 'unknown': '', 'answer': 'personne-1 a configuré le projet.'}))
    client, project = open_client(tmp_path, repo, model)
    with client:
        client.post(f'/api/projects/{project}/scans')
        result = client.post(f'/api/projects/{project}/ask',
                             json={'question': f'Qu’a changé {NAME} dans les 2 derniers commits ?'}).json()
    assert model.calls, result
    for sent in model.calls:
        assert NAME not in sent and EMAIL not in sent, sent
    assert result['answer'] == f'{NAME} a configuré le projet.'


def test_an_author_older_than_the_latest_commits_is_still_protected(leaky, git, tmp_path):
    repo, _ = leaky
    for index in range(101):
        git(repo, '-c', 'user.name=Bob Martin', '-c', 'user.email=bob.martin@example.org', 'commit', '-q',
            '--allow-empty', '-m', f'chore: étape {index}')
    model = CapturingModel(json.dumps({'cited': [], 'unknown': '', 'answer': 'Rien à signaler.'}))
    client, project = open_client(tmp_path, repo, model)
    with client:
        client.post(f'/api/projects/{project}/scans')
        client.post(f'/api/projects/{project}/ask',
                    json={'question': f'Qu’a changé {NAME} dans les 2 derniers commits ?'})
    assert model.calls
    for sent in model.calls:
        assert NAME not in sent and EMAIL not in sent, 'tout l’historique est connu, pas seulement les derniers commits'


def test_taxo_answers_who_wrote_a_commit_even_without_any_configured_model(leaky, tmp_path):
    repo, sha = leaky
    client, project = open_client(tmp_path, repo, {})
    with client:
        response = client.post(f'/api/projects/{project}/history/commits/{sha}/ask',
                               json={'question': 'Qui est l’auteur de ce commit ?'})
    assert response.status_code == 200, response.text
    assert response.json()['answer'] == f'Selon Git, l’auteur du commit {sha[:12]} est {NAME}.'
