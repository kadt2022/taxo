"""La regle `java.implements.same-signature/1` (TAXO-01K, ARCHITECTURE § 14) : une methode d'une classe implemente
la methode de meme signature d'une interface que cette classe declare implementer.

Aucune ligne ne l'ecrit : c'est une deduction (`INFERRED`), dont les premisses sont l'`IMPLEMENTS` ecrit entre les
deux types et les deux `CONTAINS` des methodes. Seule une interface des sources nommee dans la clause `implements`
est suivie, sans supertype entre les deux. Une methode `static` ou `private` de l'interface, une methode `static`
de la classe et une signature ambigue ne sont jamais reliees. Le lien ne dit jamais quel corps s'execute.
"""
from dataclasses import dataclass

from .declarations import CLASSES, premise, symbol

RULE = 'java.implements.same-signature/1'
KNOWN_GAPS = ("seules les méthodes que la classe déclare sont reliées : une implémentation héritée d'une "
              "superclasse ne l'est pas",)
_NOT_IMPLEMENTED = frozenset({'static', 'private'})


@dataclass(frozen=True)
class Implementation:
    """Une methode `subject` qui implemente `target`, prouvee par la ligne du nom de `subject`."""
    subject: str
    target: str
    path: str
    line: int
    premises: tuple


def of(sources):
    """Les implementations de methodes etablies dans les sources, dans l'ordre des noms de types."""
    for qualified in sorted(sources.types):
        declared = sources.get(qualified)
        if not _readable(sources, qualified, declared) or declared.java_type.kind not in CLASSES:
            continue
        for supertype in declared.java_type.clauses:
            interface = sources.get(supertype.qualified or '')
            if supertype.clause == 'interfaces' and _readable(sources, supertype.qualified, interface) \
                    and interface.java_type.kind == 'interface':
                yield from _pairs(declared, interface)


def _pairs(declared, interface):
    implementing, implemented = declared.java_type, interface.java_type
    relation = premise('IMPLEMENTS', symbol(implementing.qualified_name), symbol(implemented.qualified_name))
    targets = {method.signature: method for method in implemented.declarations
               if not method.constructor and not method.modifiers & _NOT_IMPLEMENTED
               and not implemented.ambiguous(method.signature)}
    for method in implementing.declarations:
        target = targets.get(method.signature)
        if target is None or method.constructor or 'static' in method.modifiers \
                or implementing.ambiguous(method.signature):
            continue
        subject = symbol(implementing.qualified_name, method.signature)
        objective = symbol(implemented.qualified_name, target.signature)
        yield Implementation(subject, objective, declared.java_file.path, method.name_line, (
            relation, premise('CONTAINS', symbol(implementing.qualified_name), subject),
            premise('CONTAINS', symbol(implemented.qualified_name), objective)))


def _readable(sources, qualified, declared):
    """Un type dont les declarations sont des faits : declare une seule fois, dans un fichier lu en entier."""
    return declared is not None and qualified not in sources.duplicated and not declared.java_file.has_errors
