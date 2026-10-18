"""La mesure de couverture des symboles des tuiles (récit contrat de suffisance, lot S0) : l'analyse lexicale, la résolution
et les couvertures, sur du code écrit ici."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

import tile_symbol_coverage as measure  # noqa: E402

METHOD = '''@Override
public AuthorizationDecision authorize(Supplier<Authentication> supplier, RequestAuthorizationContext context) {
    // commentaire : ignoré, comme "une chaîne"
    Authentication authentication = supplier.get();
    String path = request.getPath();
    if (authentication instanceof Anonymous anonymous && MAX_SIZE > 0) {
        log.warn("refusé {}", anonymous);
    }
    try {
        roles.forEach(role -> evaluator.check(role, new Subject(path)));
    } catch (IllegalStateException failure) {
        return fallback(failure);
    }
    return null;
}'''


def test_the_code_is_read_without_comments_and_strings():
    text = measure.clean('a(); // note\nb("x(y)"); /* c(d) */ e();')
    assert 'note' not in text and 'x(y)' not in text and 'c(d)' not in text
    assert 'a()' in text and 'e()' in text
    assert text.count('\n') == 1, 'les sauts de ligne sont conservés'


def test_a_method_declares_its_own_parameters_locals_lambda_catch_and_pattern_names():
    names = measure.declared_names(METHOD)
    assert {'supplier', 'context', 'authentication', 'path', 'anonymous', 'role', 'failure'} <= names
    assert 'authorize' not in names and 'request' not in names, 'ni le nom de la méthode ni un champ'
    assert measure.declared_names('void nothing()') == set(), 'sans paramètre ni variable'


def test_symbols_are_found_with_their_role():
    found = measure.symbols(METHOD, 'authorize')
    roles = {name: role for (name, role), _ in found.items()}
    assert roles['Override'] == measure.TYPE, 'une annotation est un type'
    assert roles['Subject'] == measure.TYPE, 'new X() désigne un type'
    assert roles['MAX_SIZE'] == measure.MEMBER, 'une constante'
    assert roles['request'] == measure.FIELD
    assert roles['fallback'] == measure.CALL
    assert (('getPath', measure.MEMBER_CALL)) in found and (('warn', measure.MEMBER_CALL)) in found
    assert ('authorize', measure.CALL) not in found, 'le nom de la méthode dans sa signature n’est pas un symbole utilisé'
    assert all(name not in measure.KEYWORDS for name, _ in found)
    assert 'note' not in {name for name, _ in found}, 'un commentaire n’est pas un symbole'
    generic = measure.symbols('<T> void m(T value)', 'm')
    assert ('T', measure.TYPE) not in generic, 'une variable de type d’une lettre n’est pas un type'


def test_tile_contents_are_read_for_fields_and_types():
    tile = {'fields': ['private final PolicyEvaluator policyEvaluator;', 'private int counter = 0;'],
            'class': {'text': '@Component\npublic class Manager implements AuthorizationManager {'},
            'types': [{'text': 'public record Subject(String id) {'}, {'text': 'interface Port {'}]}
    assert measure.field_names(tile['fields']) == {'policyEvaluator', 'counter'}
    assert measure.type_names(tile) == {'Manager', 'Subject', 'Port'}
    assert measure.type_names({}) == set()


def test_each_symbol_is_in_the_tile_known_not_carried_or_unresolved():
    tile = {'fields': ['private final Evaluator evaluator;'], 'class': {'text': 'public class Manager {'}, 'types': []}
    code = 'void run(Request request) { evaluator.check(request); helper(); Other.use(); service.save(); ghost(); String s; }'
    known = {'types': {'Request', 'Other'}, 'calls': {'check', 'save'}, 'members': {'helper'}}
    states = {(item.name, item.role): item.state for item in measure.resolve(measure.symbols(code, 'run'), code, tile, known)}
    assert states[('request', measure.LOCAL)] == measure.IN_TILE, 'un paramètre'
    assert states[('evaluator', measure.FIELD)] == measure.IN_TILE, 'un champ dont la tuile porte la déclaration'
    assert states[('Request', measure.TYPE)] == measure.KNOWN_NOT_CARRIED, 'type du projet, en-tête absent'
    assert states[('check', measure.MEMBER_CALL)] == measure.KNOWN_NOT_CARRIED, 'un appel que Taxo relie'
    assert states[('helper', measure.CALL)] == measure.KNOWN_NOT_CARRIED, 'une méthode de la classe'
    assert states[('ghost', measure.CALL)] == measure.UNRESOLVED
    assert states[('service', measure.FIELD)] == measure.UNRESOLVED
    assert states[('String', measure.TYPE)] == measure.UNRESOLVED


def test_a_type_whose_header_the_tile_carries_is_resolved():
    tile = {'fields': [], 'class': {'text': 'public class Manager {'}, 'types': []}
    code = 'Manager self() { return null; }'
    states = {item.name: item.state for item in measure.resolve(measure.symbols(code, 'self'), code, tile,
                                                                  {'types': set(), 'calls': set(), 'members': set()})}
    assert states['Manager'] == measure.IN_TILE


def test_coverage_is_strict_when_carried_and_wider_with_the_links_taxo_knows():
    items = [measure.Resolution('a', measure.FIELD, measure.IN_TILE, ''), measure.Resolution('b', measure.CALL, measure.KNOWN_NOT_CARRIED, ''),
             measure.Resolution('c', measure.TYPE, measure.UNRESOLVED, ''), measure.Resolution('d', measure.TYPE, measure.UNRESOLVED, '')]
    assert measure.coverage(items) == (0.25, 0.5)
    assert measure.coverage([]) == (1.0, 1.0), 'une méthode sans symbole n’a rien à identifier'


def test_the_sample_is_deterministic_and_keeps_the_wanted_methods_first():
    methods = [f'symbol:java:p.C#m{index}()' for index in range(40)] + ['symbol:java:p.D#authorize(A)']
    picked = measure.pick(methods, 10, ['authorize'])
    assert picked[0] == 'symbol:java:p.D#authorize(A)' and len(picked) == 10
    assert picked == measure.pick(methods, 10, ['authorize']), 'même échantillon à chaque lancement'
    assert measure.pick(methods[:3], 10, []) == methods[:3]
    assert measure.pick(methods, 0, []) == []


def test_imports_explain_a_type_name_or_say_why_they_cannot():
    source = 'import java.util.List;\nimport static org.x.Util.helper;\nimport org.spring.Component;\n'
    assert measure.import_kind('Component', source) == 'import'
    assert measure.import_kind('String', source) == 'java.lang', 'visible sans import'
    assert measure.import_kind('Mystery', source) == 'none'
    assert measure.import_kind('Mystery', source + 'import org.other.*;\n') == 'wildcard', 'un joker ne désigne pas un type'
