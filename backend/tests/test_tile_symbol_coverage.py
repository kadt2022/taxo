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


# --- Remarques de revue de la PR 175 ----------------------------------------------------------------------------------------

def test_a_double_slash_inside_a_string_is_not_a_comment():
    text = measure.clean('String url = "http://host"; call(real);')
    assert 'real' in text, 'le code après la chaîne n’est pas avalé'
    assert 'http' not in text and 'host' not in text, 'le contenu de la chaîne est effacé'
    again = measure.clean('x = 1; // un "guillemet" dans un commentaire\nstring_after = 2;')
    assert 'guillemet' not in again and 'string_after' in again, 'un guillemet dans un commentaire n’ouvre pas de chaîne'
    names = {name for name, _ in measure.symbols('void m() { String url = "http://host"; helper(url); }', 'm')}
    assert 'helper' in names and 'http' not in names


def test_the_arguments_of_a_call_are_not_local_declarations():
    assert measure.declared_names('void m() {\n    use(field, other);\n    helper(a,\n        b);\n}') == set()
    names = measure.declared_names('void m() {\n    Map<String, Integer> counts = null;\n    for (String key : keys) { int[] row = null; }\n}')
    assert names == {'counts', 'key', 'row'}, 'les vraies déclarations, génériques et tableaux compris, restent reconnues'
    code = 'void m() {\n    use(field, other);\n}'
    tile = {'fields': ['private int field;'], 'class': {'text': 'class A {'}, 'types': []}
    states = {item.name: item.state for item in measure.resolve(measure.symbols(code, 'm'), code, tile, {'types': set(), 'calls': set(), 'members': set()})}
    assert states['other'] == measure.UNRESOLVED, 'un argument n’est pas porté par la tuile parce qu’il suit une virgule'
    assert states['field'] == measure.IN_TILE


def test_a_constructor_is_skipped_under_the_name_its_declaration_writes():
    assert measure.written_name('symbol:java:p.Outer.Inner#<init>(int)') == 'Inner'
    assert measure.written_name('symbol:java:Outer#<init>()') == 'Outer'
    assert measure.written_name('symbol:java:p.Outer#run(int)') == 'run'
    code = 'public MessageAction(Builder builder) { this.id = builder.id; }'
    found = measure.symbols(code, measure.written_name('symbol:java:p.MessageAction#<init>(Builder)'))
    assert ('MessageAction', measure.CALL) not in found, 'le nom du constructeur n’est pas un symbole utilisé'
    assert ('Builder', measure.TYPE) in found
# --- S3 : les imports de la tuile et la mesure avant / après ------------------------------------------------------------

IMPORTING_TILE = {
    'fields': [], 'class': {'text': '@Slf4j\n@Component\npublic class Manager {'}, 'types': [],
    'imports': [{'line': 3, 'text': 'import org.spring.Component;'}, {'line': 4, 'text': 'import static org.x.Util.helper;'},
                {'line': 5, 'text': 'import org.web.*;'}]}
NO_KNOWN = {'types': set(), 'calls': set(), 'members': set()}


def test_imports_give_a_full_name_and_wildcards_give_only_candidate_packages():
    named, wildcards = measure.imported_names(IMPORTING_TILE)
    assert named == {'Component': 'import org.spring.Component;', 'helper': 'import static org.x.Util.helper;'}
    assert wildcards == ['import org.web.*;']
    assert measure.imported_names({}) == ({}, [])
    assert measure.imported_names({'imports': [{'line': 1, 'text': 'not an import'}]}) == ({}, [])


def test_an_imported_type_is_identified_not_resolved_and_a_wildcard_invents_nothing():
    code = 'void run() { Component one; Mystery two; }'
    found = measure.symbols(code, 'run')
    states = {item.name: item for item in measure.resolve(found, code, IMPORTING_TILE, NO_KNOWN)}
    assert states['Component'].state == measure.IMPORTED and states['Component'].how == 'import org.spring.Component;'
    assert states['Mystery'].state == measure.UNRESOLVED and 'paquets candidats' in states['Mystery'].how
    assert 'import org.web.*;' in states['Mystery'].how, 'le joker est dit candidat, jamais choisi'


def test_the_tool_fixes_are_off_by_default_and_reported_apart():
    code = 'void run() { log.info(); String text; UUID id; }'
    found_s0, found_fixed = measure.symbols(code, 'run'), measure.symbols(code, 'run', fixed=True)
    old = {item.name: item.state for item in measure.resolve(found_s0, code, IMPORTING_TILE, NO_KNOWN)}
    new = {item.name: item.state for item in measure.resolve(found_fixed, code, IMPORTING_TILE, NO_KNOWN, fixed=True)}
    assert old['String'] == measure.UNRESOLVED and new['String'] == measure.IMPLICIT, 'java.lang : une règle du langage'
    assert old['log'] == measure.UNRESOLVED and new['log'] == measure.IN_TILE, 'le champ log est déclaré par @Slf4j'
    assert {role for (name, role) in found_s0 if name == 'UUID'} == {measure.MEMBER}, 'le biais du lot S0'
    assert {role for (name, role) in found_fixed if name == 'UUID'} == {measure.TYPE}


def test_a_name_in_capitals_is_a_type_only_when_it_is_written_as_one():
    for before, after in [('', 'id = null'), ('', '::fromString'), ('Set<', '> items'), ('', '<T> x'), ('', '[] ids')]:
        assert measure._used_as_type(before, after), (before, after)
    for before, after in [('x = ', '+ 1'), ('if (', '> 0)'), ('f(', ', 3)'), ('return ', ';'), ('', '.equals(path)')]:
        assert not measure._used_as_type(before, after), (before, after)


def test_the_four_measures_run_from_strict_to_wide():
    states = ([measure.Resolution('a', measure.FIELD, measure.IN_TILE, '')] * 2 + [measure.Resolution('b', measure.TYPE, measure.IMPORTED, '')]
              + [measure.Resolution('c', measure.TYPE, measure.IMPLICIT, '')] + [measure.Resolution('d', measure.CALL, measure.KNOWN_NOT_CARRIED, '')]
              + [measure.Resolution('e', measure.TYPE, measure.UNRESOLVED, '')] * 3)
    result = measure.metrics(states)
    assert (result['total'], result['carried'], result['imported'], result['implicit'], result['known'], result['unresolved']) == (8, 2, 1, 1, 1, 3)
    assert (result['strict'], result['identified'], result['language'], result['links']) == (0.25, 0.375, 0.5, 0.625)
    assert measure.metrics([])['strict'] == 1.0


def test_a_capitals_receiver_is_a_type_only_when_an_import_names_it():
    tile = {**IMPORTING_TILE, 'imports': [{'line': 3, 'text': 'import java.util.UUID;'}]}
    code = 'void run() { UUID.fromString(a); TOKEN.equals(b); }'
    found = measure.symbols(code, 'run', fixed=True)
    states = {item.name: (item.role, item.state) for item in measure.resolve(found, code, tile, NO_KNOWN, fixed=True)}
    assert states['UUID'] == (measure.TYPE, measure.IMPORTED), 'un import désigne UUID : c’est un type'
    assert states['TOKEN'] == (measure.MEMBER, measure.UNRESOLVED), 'sans import, le texte ne dit pas que TOKEN est un type'


def test_an_import_after_a_comment_still_names_its_type():
    tile = {'imports': [{'line': 3, 'text': '/* note */ import org.spring.Component;'}, {'line': 4, 'text': '// import a.Hidden;'}]}
    assert measure.imported_names(tile) == ({'Component': '/* note */ import org.spring.Component;'}, [])
