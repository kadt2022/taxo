"""La regle `java.calls.declared-receiver-unique-target/4` (TAXO-01K, TAXO-01L, ARCHITECTURE § 14) : d'un site
d'appel a la declaration qu'il vise, ou a la raison fermee pour laquelle elle n'est pas etablie.

Le receveur est `this`, implicite, un champ du type courant (`champ`, `this.champ`), ou, depuis la version 3, un
parametre ou une variable locale visible au site, dont le type declare est un type des sources. La cible est la
seule declaration de meme nom et meme arite dans la hierarchie de ce type, toute dans les sources hors les
supertypes de la JDK connus du contrat (`KNOWN_SUPERTYPES`, version 2), qui ne declarent aucune autre methode que
celles d'`Object`. Depuis la version 4, l'accesseur implicite d'un composant de record est une declaration
candidate comme une autre, sa premisse etant le `CONTAINS` infere de `java.record.implicit-accessor/1`. Toute
autre forme, et tout doute (surcharge, supertype externe, argument litteral contraire), laisse le site non
interprete : moins d'appels, mais vrais.
"""
from dataclasses import dataclass, field

from app.evaluators.java import sites
from . import accessors, arguments
from .declarations import OBJECT_METHODS, external_name, premise, symbol

RULE = 'java.calls.declared-receiver-unique-target/4'
KNOWN_GAPS = ('applicabilité des arguments non vérifiée ; suppose un code qui compile',)

RECEIVER_TYPE_UNKNOWN = 'RECEIVER_TYPE_UNKNOWN'
RECEIVER_TYPE_AMBIGUOUS = 'RECEIVER_TYPE_AMBIGUOUS'
TARGET_TYPE_OUTSIDE_SNAPSHOT = 'TARGET_TYPE_OUTSIDE_SNAPSHOT'
TARGET_DECLARATION_OUTSIDE_SNAPSHOT = 'TARGET_DECLARATION_OUTSIDE_SNAPSHOT'
NO_MATCHING_DECLARATION = 'NO_MATCHING_DECLARATION'
OVERLOAD_AMBIGUOUS = 'OVERLOAD_AMBIGUOUS'
SUPER_TYPE_UNRESOLVED = 'SUPER_TYPE_UNRESOLVED'
UNSUPPORTED_CALL_FORM = 'UNSUPPORTED_CALL_FORM'
RECEIVER_KIND_DEFERRED = 'RECEIVER_KIND_DEFERRED'
LAMBDA_OR_LOCAL_CONTEXT = 'LAMBDA_OR_LOCAL_CONTEXT'
PARSE_ERROR = 'PARSE_ERROR'
# `super.f()` et tout receveur qui n'est ni `this`, ni un nom, ni `this.champ` : hors du premier fragment.
_OUTSIDE_FRAGMENT = (sites.SUPER, sites.EXPRESSION)


@dataclass(frozen=True)
class Outcome:
    """Une cible etablie (`target`, avec ses premisses), ou une raison fermee et ce que le diagnostic en dit."""
    target: str | None = None
    reason: str | None = None
    premises: tuple = ()
    counter_examples: tuple = ()
    details: dict = field(default_factory=dict)
    # Les declarations (`OBSERVED`) que les premisses citent et que l'evaluateur n'ecrit pas deja : celles d'un
    # parametre ou d'une variable receveur, (sujet, relation, objet, ligne).
    declarations: tuple = ()


@dataclass(frozen=True)
class _Receiver:
    qualified: str
    premises: tuple = ()
    declarations: tuple = ()


class _Stop(Exception):
    def __init__(self, reason, **details):
        super().__init__(reason)
        self.reason, self.details = reason, details


class Resolver:
    def __init__(self, sources):
        self.sources = sources

    def resolve(self, site, java_file):
        details = _written(site)
        try:
            receiver = self._receiver(site, java_file)
            details['receiver_type'] = receiver.qualified
            target, premises, counter_examples = self._target(site, receiver, java_file)
        except _Stop as stop:
            return Outcome(reason=stop.reason, details={**details, **stop.details})
        return Outcome(target, premises=premises, counter_examples=counter_examples, details=details,
                       declarations=receiver.declarations)

    def _receiver(self, site, java_file):
        """Le type declare du receveur, pour les seules formes du fragment."""
        if site.context == sites.NESTED:
            raise _Stop(LAMBDA_OR_LOCAL_CONTEXT)
        if site.context == sites.INITIALIZER or site.form != sites.METHOD or site.receiver in _OUTSIDE_FRAGMENT:
            raise _Stop(UNSUPPORTED_CALL_FORM)
        if site.receiver == sites.IMPLICIT:
            self._no_other_provider(site, java_file)
            return _Receiver(site.owner)
        if site.receiver == sites.THIS:
            return _Receiver(site.owner)
        if site.variable == sites.PATTERN:
            raise _Stop(RECEIVER_KIND_DEFERRED)
        if site.variable is not None:
            return self._variable_type(site, java_file)
        name = site.written.removeprefix('this.')
        own = next((item for item in self.sources.get(site.owner).java_type.fields if item.name == name), None)
        if own is None:
            if site.receiver == sites.NAME and (java_file.resolve(name, site.owner) or java_file.imported(name)):
                raise _Stop(UNSUPPORTED_CALL_FORM)
            raise _Stop(RECEIVER_TYPE_UNKNOWN)
        return self._field_type(site.owner, own, java_file)

    def _field_type(self, owner, own, java_file):
        if own.type_variable:
            raise _Stop(RECEIVER_TYPE_UNKNOWN)
        if own.qualified_type is None:
            raise _Stop(TARGET_TYPE_OUTSIDE_SNAPSHOT, receiver_type=external_name(java_file, own.written_type))
        if own.qualified_type in self.sources.duplicated:
            raise _Stop(RECEIVER_TYPE_AMBIGUOUS, receiver_type=own.qualified_type)
        return _Receiver(own.qualified_type, (premise('TYPED_AS', symbol(owner, own.name), symbol(own.qualified_type)),))

    def _variable_type(self, site, java_file):
        """Le type declare d'un parametre ou d'une variable locale : ses premisses sont la declaration de la variable
        par la methode et son type, faits ecrits pour l'occasion."""
        variable = site.declaration
        if not variable.named:
            raise _Stop(RECEIVER_TYPE_UNKNOWN)
        qualified = java_file.resolve(variable.written, site.owner) if '[' not in variable.written else None
        if qualified is None:
            raise _Stop(TARGET_TYPE_OUTSIDE_SNAPSHOT, receiver_type=external_name(java_file, variable.written))
        if qualified in self.sources.duplicated:
            raise _Stop(RECEIVER_TYPE_AMBIGUOUS, receiver_type=qualified)
        member = symbol(site.owner, site.member)
        named = f'{member}/{variable.name}'
        declarations = ((member, 'CONTAINS', named, variable.line),
                        (named, 'TYPED_AS', symbol(qualified), variable.line))
        premises = tuple(premise(relation, holder, target) for holder, relation, target, _ in declarations)
        return _Receiver(qualified, premises, declarations)

    def _no_other_provider(self, site, java_file):
        """`f()` sans receveur : aucun type englobant ne declare `f` de meme arite, aucun import statique ne peut le
        fournir. Sinon le type qui le fournit n'est pas etabli."""
        outer = site.owner.rpartition('.')[0]
        while outer in self.sources.types:
            if any(_matches(item, site) for item in accessors.callables(self.sources.get(outer).java_type)):
                raise _Stop(OVERLOAD_AMBIGUOUS)
            outer = outer.rpartition('.')[0]
        if any(static and name.rsplit('.', 1)[-1] in (site.name, '*') for name, static in java_file.imports):
            raise _Stop(OVERLOAD_AMBIGUOUS)

    def _target(self, site, receiver, java_file):
        hierarchy = self.sources.hierarchy(receiver.qualified)
        if hierarchy.unreadable:
            raise _Stop(PARSE_ERROR)
        if hierarchy.ambiguous:
            raise _Stop(RECEIVER_TYPE_AMBIGUOUS)
        found, others = [], []
        for depth, qualified, java_type, declaration in self._named(hierarchy, site.name):
            if declaration.varargs:
                raise _Stop(OVERLOAD_AMBIGUOUS, candidates=_candidates(found + [(depth, qualified, declaration)]))
            if len(declaration.parameters) != len(site.arguments):
                if not java_type.ambiguous(declaration.signature):
                    others.append(premise('CONTAINS', symbol(qualified), symbol(qualified, declaration.signature)))
            elif java_type.ambiguous(declaration.signature):
                raise _Stop(OVERLOAD_AMBIGUOUS, candidates=[symbol(qualified, declaration.signature)])
            else:
                found.append((depth, qualified, declaration))
        depth, qualified, declaration = _choose(site, found, hierarchy, java_file)
        chosen = symbol(qualified, declaration.signature)
        premises = receiver.premises + hierarchy.paths[qualified] + (
            premise('CONTAINS', symbol(qualified), chosen),)
        return chosen, premises, tuple(sorted(set(others)))

    def _named(self, hierarchy, name):
        """Les methodes nommees `name` de la hierarchie, niveau par niveau : (niveau, type, type lu, declaration)."""
        for depth, level in enumerate(hierarchy.levels):
            for qualified in level:
                java_type = self.sources.get(qualified).java_type
                for declaration in accessors.callables(java_type):
                    if not declaration.constructor and declaration.name == name:
                        yield depth, qualified, java_type, declaration


def _choose(site, found, hierarchy, java_file):
    """La seule declaration candidate, au niveau le plus proche ; sinon la raison de l'arret."""
    candidates = _candidates(found)
    external = sorted(hierarchy.external)
    if not found:
        if (site.name, len(site.arguments)) in OBJECT_METHODS:
            raise _Stop(OVERLOAD_AMBIGUOUS)
        if external:
            raise _Stop(TARGET_DECLARATION_OUTSIDE_SNAPSHOT, external_supertypes=external)
        raise _Stop(NO_MATCHING_DECLARATION)
    if external:
        raise _Stop(SUPER_TYPE_UNRESOLVED, external_supertypes=external, candidates=candidates)
    signatures = {declaration.signature for _, _, declaration in found}
    inherited = OBJECT_METHODS.get((site.name, len(site.arguments)))
    if len(signatures) > 1 or (inherited is not None and signatures != {inherited}):
        raise _Stop(OVERLOAD_AMBIGUOUS, candidates=candidates)
    nearest = min(depth for depth, _, _ in found)
    closest = [item for item in found if item[0] == nearest]
    if len(closest) > 1:
        raise _Stop(OVERLOAD_AMBIGUOUS, candidates=candidates)
    if not arguments.applicable(site.arguments, closest[0][2].parameters):
        raise _Stop(NO_MATCHING_DECLARATION, candidates=candidates)
    return closest[0]


def _candidates(found):
    return [symbol(qualified, declaration.signature) for _, qualified, declaration in found]


def _matches(declaration, site):
    return not declaration.constructor and declaration.name == site.name and (
        declaration.varargs or len(declaration.parameters) == len(site.arguments))


def _written(site):
    """Ce que le diagnostic dit du site tel qu'ecrit : la methode et le receveur, quand ils sont des noms."""
    details = {}
    if site.name is not None:
        details['method'] = site.name
    if site.written is not None:
        details['receiver'] = site.written
    return details
