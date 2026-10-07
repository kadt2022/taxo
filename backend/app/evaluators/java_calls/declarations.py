"""Les types Java des sources, par nom qualifie, et la hierarchie de chacun (TAXO-01K, ARCHITECTURE § 14).

Une hierarchie ne suit que les supertypes des sources ; un supertype ecrit qui n'y est pas est externe, nomme par
son import quand il en a un, sans jamais inventer sa declaration. `Object` n'est pas un supertype externe : ses
methodes sont connues du contrat (`OBJECT_METHODS`). Un enum ou un record a une superclasse implicite, externe.
"""
from dataclasses import dataclass, field

JAVA = 'symbol:java:'
OBJECT = frozenset({'Object', 'java.lang.Object'})
IMPLICIT_SUPERCLASS = {'enum': 'java.lang.Enum', 'record': 'java.lang.Record'}
# Les methodes d'`Object` (JLS 4.3.2), par nom et arite : leur signature dans `Object`.
OBJECT_METHODS = {('equals', 1): 'equals(Object)', ('hashCode', 0): 'hashCode()', ('toString', 0): 'toString()',
                  ('getClass', 0): 'getClass()', ('notify', 0): 'notify()', ('notifyAll', 0): 'notifyAll()',
                  ('wait', 0): 'wait()', ('wait', 1): 'wait(long)', ('wait', 2): 'wait(long,int)',
                  ('clone', 0): 'clone()', ('finalize', 0): 'finalize()'}
_CLASSES = ('class', 'enum', 'record')


def symbol(qualified, member=None):
    return f'{JAVA}{qualified}#{member}' if member is not None else f'{JAVA}{qualified}'


def premise(relation, subject, target):
    """Une premisse, ecrite comme celles des autres evaluateurs : `RELATION : sujet -> objet`."""
    return f'{relation} : {subject} -> {target}'


def supertype_relation(java_type, supertype):
    """`IMPLEMENTS` pour une interface qu'une classe implemente, `EXTENDS` pour tout autre supertype."""
    return 'IMPLEMENTS' if supertype.clause == 'interfaces' and java_type.kind in _CLASSES else 'EXTENDS'


@dataclass(frozen=True)
class Declared:
    java_file: object
    java_type: object


@dataclass
class Hierarchy:
    """Les types de la hierarchie, niveau par niveau a partir du type lui-meme ; pour chacun, les premisses qui le
    relient au type de depart. `external` nomme les supertypes hors des sources ; `unreadable` est vrai si un type
    vient d'un fichier lu en partie, `ambiguous` si un type est declare plusieurs fois dans les sources."""
    levels: list = field(default_factory=list)
    paths: dict = field(default_factory=dict)
    external: list = field(default_factory=list)
    unreadable: bool = False
    ambiguous: bool = False


class Sources:
    def __init__(self, parsed):
        self.types, self.duplicated = {}, set()
        for java_file in parsed:
            for java_type in java_file.types:
                if java_type.qualified_name in self.types:
                    self.duplicated.add(java_type.qualified_name)
                self.types[java_type.qualified_name] = Declared(java_file, java_type)

    def get(self, qualified):
        return self.types.get(qualified)

    def hierarchy(self, qualified):
        found = Hierarchy(levels=[[qualified]], paths={qualified: ()})
        level = [qualified]
        while level:
            following = []
            for name in level:
                following += self._supertypes(name, found)
            level = following
            if level:
                found.levels.append(level)
        return found

    def _supertypes(self, name, found):
        """Les supertypes des sources de `name` pas encore vus ; les externes sont notes dans `found`."""
        declared = self.types[name]
        found.unreadable = found.unreadable or declared.java_file.has_errors
        found.ambiguous = found.ambiguous or name in self.duplicated
        following = []
        for supertype in declared.java_type.clauses:
            if supertype.written in OBJECT:
                continue
            if supertype.qualified is None or supertype.qualified not in self.types:
                _note(found.external, external_name(declared.java_file, supertype.written))
            elif supertype.qualified not in found.paths:
                relation = supertype_relation(declared.java_type, supertype)
                found.paths[supertype.qualified] = found.paths[name] + (
                    premise(relation, symbol(name), symbol(supertype.qualified)),)
                following.append(supertype.qualified)
        implicit = IMPLICIT_SUPERCLASS.get(declared.java_type.kind)
        if implicit is not None:
            _note(found.external, implicit)
        return following


def external_name(java_file, written):
    """Le nom d'un type hors des sources : son import explicite s'il en a un, sinon tel qu'ecrit."""
    if '.' in written:
        return written
    return java_file.imported(written) or written


def _note(names, name):
    if name not in names:
        names.append(name)
