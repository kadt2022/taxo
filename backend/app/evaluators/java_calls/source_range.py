"""Les lignes qu'occupe la déclaration d'un symbole Java dans son fichier (TAXO-MIP-ADT-01, PR B).

Le protocole lit le code d'un symbole (`get_source`) sans rien savoir de Java : l'évaluateur qui a déclaré le
symbole dit où sa déclaration commence et finit, avec le même lecteur syntaxique et la même identité
(`java-symbol-syntactic/1`) que ses faits. Une surcharge se distingue par sa signature ; une signature portée par
deux déclarations du même type n'a pas d'identité, et rien n'est rendu.

Les lignes vont de la première annotation ou du premier modificateur jusqu'à l'accolade fermante : la déclaration,
ses annotations et son corps. La Javadoc qui précède n'en fait pas partie. Un champ n'a pas de plage propre : seuls
les types, les méthodes et les constructeurs sont lus.
"""
from dataclasses import dataclass

from app.evaluators.java.syntax import parse

from .declarations import JAVA

_MEMBER = '#'


@dataclass(frozen=True)
class DeclarationLines:
    """La plage d'une déclaration, bornes comprises, et la ligne de son nom (celle de la preuve)."""
    line_start: int
    line_end: int
    name_line: int


def _split(reference):
    if not reference.startswith(JAVA):
        return None, None
    qualified, _, member = reference[len(JAVA):].partition(_MEMBER)
    return qualified, member or None


def declaration_lines(path, source: bytes, reference):
    """Les lignes de la déclaration de `reference` dans le fichier `path`, ou None si ce fichier ne la déclare pas
    une seule fois : type absent, membre qui n'est pas une méthode ou un constructeur, signature ambiguë."""
    qualified, member = _split(reference)
    if qualified is None:
        return None
    java_type = next((item for item in parse(path, source).types if item.qualified_name == qualified), None)
    if java_type is None:
        return None
    if member is None:
        return DeclarationLines(java_type.line_start, java_type.line_end, java_type.name_line)
    found = [item for item in java_type.declarations if item.signature == member]
    if len(found) != 1:
        return None
    return DeclarationLines(found[0].line_start, found[0].line_end, found[0].name_line)
