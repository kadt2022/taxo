"""La regle `java.record.implicit-accessor/1` (TAXO-01L, ARCHITECTURE § 14) : un record declare l'accesseur de
chacun de ses composants que son corps n'ecrit pas (JLS 8.10.3).

Aucune ligne n'ecrit cet accesseur : c'est le langage qui le declare a partir du composant. Le `CONTAINS` du record
vers `x()` est donc deduit (`INFERRED`), sa premisse est le `CONTAINS` observe du champ du composant, et sa preuve
la ligne du composant. Un accesseur ecrit dans le corps est une methode ordinaire.
"""
from app.evaluators.java import syntax

from .declarations import premise, symbol

RULE = 'java.record.implicit-accessor/1'
KNOWN_GAPS = ()


def declarations(java_type):
    """Les accesseurs implicites du type, comme des declarations de methodes sans parametre."""
    return tuple(syntax.Method(item.name, item.line, item.line, name_line=item.line)
                 for item in java_type.implicit_accessors)


def callables(java_type):
    """Les methodes et constructeurs ecrits du type, puis ses accesseurs implicites."""
    return java_type.declarations + declarations(java_type)


def premises(qualified, accessor):
    """Le champ du composant, declare par le record : la seule premisse de son accesseur implicite."""
    return (premise('CONTAINS', symbol(qualified), symbol(qualified, accessor.name)),)
