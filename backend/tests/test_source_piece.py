"""La pièce source sans dépôt ni base : plage Java, limites, refus de lecture (TAXO-MIP-ADT-01, PR B)."""
import pytest

from app.evaluators.java_calls.source_range import DeclarationLines, declaration_lines
from app.facts import content_hash
from app.history.domain.diff import BINARY, CONFIDENTIAL, Blob
from app.protocol.application.source import SourceOperation
from app.protocol.domain import source as policy
from app.protocol.domain.envelope import OperationError

JAVA = '\n'.join([
    'package p;',
    'public class Outer {',
    '    Outer(int a) {',
    '    }',
    '    static class Inner {',
    '        void run() { }',
    '    }',
    '    int count;',
    '}',
    ''])
PATH = 'src/p/Outer.java'
METHOD = 'symbol:java:p.Outer.Inner#run()'


@pytest.mark.parametrize('reference, expected', [
    ('symbol:java:p.Outer', DeclarationLines(2, 9, 2)),
    ('symbol:java:p.Outer#<init>(int)', DeclarationLines(3, 4, 3)),
    ('symbol:java:p.Outer.Inner', DeclarationLines(5, 7, 5)),
    (METHOD, DeclarationLines(6, 6, 6)),
    ('symbol:java:p.Outer#count', None),
    ('symbol:java:p.Outer#run()', None),
    ('symbol:java:q.Outer', None),
    ('symbol:kotlin:p.Outer', None),
])
def test_the_java_reader_gives_the_lines_of_one_declaration(reference, expected):
    assert declaration_lines(PATH, JAVA.encode(), reference) == expected


def test_a_piece_stops_on_a_whole_line_at_the_byte_limit(monkeypatch):
    monkeypatch.setattr(policy, 'MAX_SOURCE_BYTES', 12)
    source = b'abcde\nfghij\nklmno\n'
    found = policy.piece(source, 1, 3)
    assert (found.text, found.line_end, found.declared_end, found.truncated) == ('abcde\nfghij', 2, 3, True)
    assert found.content_hash == content_hash(source, 1, 2)
    monkeypatch.setattr(policy, 'MAX_SOURCE_BYTES', 3)
    assert policy.piece(source, 1, 3) is None


def test_carriage_returns_are_counted_like_the_evidence():
    found = policy.piece(b'a\r\nb\r\n', 1, 2)
    assert found.text == 'a\nb' and found.content_hash == content_hash(b'a\r\nb\r\n', 1, 2)


class _History:
    def __init__(self, content=None, reason=None):
        self.content, self.reason, self.reads = content, reason, []

    def source(self, project_id, revision, path):
        self.reads.append(path)
        return self.content, self.reason


class _Exchange:
    """Une analyse au commit `c1` dont la seule déclaration est `METHOD` à la ligne 6 de `path`."""

    def __init__(self, path=PATH, line=6):
        self.snapshot, self.project_id, self.source_consent = {'analysis': 'a', 'commit': 'c1'}, 'p', True
        self.committed = True
        proof = {'path': path, 'line_start': line, 'line_end': line, 'symbol': METHOD, 'commit': 'c1',
                 'content_hash': content_hash(JAVA.encode(), line, line)}
        self.fact = {'kind': 'ASSERTION', 'status': 'OBSERVED', 'relation': 'CONTAINS', 'subject': 'x',
                     'object': METHOD, 'evidence': [proof], 'produced_by': {'producer_id': 'java'}}

    def query(self, **_):
        return [self.fact]

    def own(self, *_):
        pass

    def envelope_coverage(self, *_):
        return []

    def response(self, operation, coverage, max_bytes, **fields):
        from app.protocol.domain.envelope import Response
        return Response(operation, self.snapshot, coverage, max_bytes, **fields)


def _read(exchange, history):
    operation = SourceOperation(exchange, history, {'java': declaration_lines})
    return operation.get_source({'reference': METHOD}, 8000).close()


@pytest.mark.parametrize('reason', [CONFIDENTIAL, BINARY, 'TOO_LARGE', 'NOT_A_REGULAR_FILE'])
def test_a_refused_file_sends_no_code_and_says_why(reason):
    response = _read(_Exchange(), _History(reason=reason))
    assert response['items'] == [] and response['not_sent'] == [{'what': 'source', 'reason': reason}]
    assert response['classification']['content'] == [] and response['disclosure']['restrictions'] == []


def test_a_generated_file_is_never_read():
    history = _History(JAVA.encode())
    response = _read(_Exchange(path='dist/app.min.js'), history)
    assert response['not_sent'] == [{'what': 'source', 'reason': 'GENERATED'}] and history.reads == []


def test_a_declaration_not_found_at_the_evidence_line_sends_nothing():
    exchange = _Exchange()
    exchange.fact['evidence'][0].update(line_start=5, line_end=5, content_hash=content_hash(JAVA.encode(), 5, 5))
    response = _read(exchange, _History(JAVA.encode()))
    assert response['not_sent'] == [{'what': 'source', 'reason': 'NOT_DECLARED'}]


def test_an_inferred_declaration_or_another_commit_is_not_read():
    exchange = _Exchange()
    exchange.fact['status'] = 'INFERRED'
    with pytest.raises(OperationError, match='Aucune déclaration'):
        _read(exchange, _History(JAVA.encode()))
    exchange = _Exchange()
    exchange.fact['evidence'][0]['commit'] = 'c0'
    with pytest.raises(OperationError, match='commit de l’analyse'):
        _read(exchange, _History(JAVA.encode()))


def test_a_working_tree_analysis_is_refused_before_any_read():
    """Le commit n'est pas ce que l'analyse du dossier de travail a lu : aucun fichier n'est ouvert."""
    exchange, history = _Exchange(), _History(JAVA.encode())
    exchange.committed = False
    with pytest.raises(OperationError, match='dossier de travail') as refused:
        _read(exchange, history)
    assert refused.value.code == 'NOT_AVAILABLE' and history.reads == []


def test_the_consent_is_checked_again_by_the_operation():
    exchange = _Exchange()
    exchange.source_consent = False
    with pytest.raises(OperationError) as refused:
        _read(exchange, _History(JAVA.encode()))
    assert refused.value.code == 'NO_CONSENT'


def test_the_piece_is_read_and_classified():
    response = _read(_Exchange(), _History(JAVA.encode()))
    piece, = response['items']
    assert piece['text'] == '        void run() { }' and response['classification']['nature'] == 'METHOD'
    assert piece['declaration_hash'] == content_hash(JAVA.encode(), 6, 6)


class _Reader:
    def __init__(self, blob, content=b''):
        self.found, self.data, self.calls = blob, content, []

    def blob(self, root, revision, path):
        self.calls.append(('blob', path))
        return self.found

    def content(self, root, oid):
        self.calls.append(('content', oid))
        return self.data


def _history(reader):
    from app.history.application.queries import ProjectHistory
    history = ProjectHistory(None, None, reader, None, (), None)
    history._root = lambda project_id: (None, '/repo')
    return history


@pytest.mark.parametrize('blob, content, expected', [
    (Blob('o', '100644', 4), b'ok\n', (b'ok\n', None)),
    (Blob('o', '100644', 4), b'\x00\x01', (None, BINARY)),
    (Blob('o', '120000', 4), b'', (None, 'NOT_A_REGULAR_FILE')),
    (Blob('o', '100644', 10 ** 7), b'', (None, 'TOO_LARGE')),
])
def test_the_history_reads_a_file_with_the_refusals_of_the_diff(blob, content, expected):
    assert _history(_Reader(blob, content)).source('p', 'c1', 'src/A.java') == expected


def test_a_confidential_file_is_never_opened():
    reader = _Reader(Blob('o', '100644', 4), b'SECRET=1\n')
    assert _history(reader).source('p', 'c1', 'config/.env') == (None, CONFIDENTIAL) and reader.calls == []


def test_a_truncated_piece_never_ends_on_a_blank_line(monkeypatch):
    """Un texte qui finirait par un saut de ligne ferait perdre une ligne à qui compte avec `splitlines()`."""
    monkeypatch.setattr(policy, 'MAX_SOURCE_LINES', 3)
    source = b'a\nb\n\nc\nd\n'
    cut = policy.piece(source, 1, 5)
    assert cut.truncated and (cut.line_start, cut.line_end, cut.declared_end) == (1, 2, 5)
    assert cut.text == 'a\nb' and not cut.text.endswith('\n')
    assert len(cut.text.splitlines()) == cut.line_end - cut.line_start + 1, 'les lignes comptées égalent la plage annoncée'
    assert cut.content_hash == content_hash(source, 1, 2), 'l’empreinte est celle de ce qui est transmis'


def test_several_blank_lines_at_the_cut_are_all_left_out(monkeypatch):
    monkeypatch.setattr(policy, 'MAX_SOURCE_LINES', 4)
    cut = policy.piece(b'a\n\n\n\nb\n', 1, 5)
    assert (cut.line_end, cut.text) == (1, 'a') and cut.truncated


def test_a_piece_of_blank_lines_only_gives_nothing(monkeypatch):
    monkeypatch.setattr(policy, 'MAX_SOURCE_LINES', 2)
    assert policy.piece(b'\n\n\nx\n', 1, 4) is None


def test_a_piece_that_is_not_cut_keeps_its_declared_range(monkeypatch):
    whole = policy.piece(b'a\n\nb\n', 1, 3)
    assert not whole.truncated and (whole.line_end, whole.text) == (3, 'a\n\nb')
    monkeypatch.setattr(policy, 'MAX_SOURCE_LINES', 3)
    exact = policy.piece(b'a\nb\n\n', 1, 3)
    assert not exact.truncated and exact.line_end == 3, 'une plage qui tient entière n’est pas rognée'
FILE_WITH_IMPORTS = b"""package p;

// import x.Commented;
/* import y.InBlock;
   import z.AlsoInBlock; */
import a.b.C;
import static a.b.D.helper;
import a.e.*;
  import   f.G  ;

public class Outer {
}
"""


def test_the_import_lines_are_read_as_written_and_never_from_a_comment():
    found = policy.import_lines(FILE_WITH_IMPORTS, 11)
    assert found == [(6, 'import a.b.C;'), (7, 'import static a.b.D.helper;'), (8, 'import a.e.*;'), (9, 'import   f.G  ;')]


def test_the_import_lines_stop_before_the_declaration():
    assert policy.import_lines(FILE_WITH_IMPORTS, 7) == [(6, 'import a.b.C;')]
    assert policy.import_lines(FILE_WITH_IMPORTS, 1) == []
    assert policy.import_lines(b'', 5) == []
