"""Un argument litteral contredit-il le parametre ecrit ? (TAXO-01K, ARCHITECTURE § 14)

Le premier fragment ne type pas les expressions : il suppose un code qui compile. Seul un litteral dont le type
contredit un parametre de type connu ecarte une declaration (`f(String)` ne recoit pas `42`). Un parametre d'un
autre type (classe des sources, interface, variable de type) n'est jamais juge : rien n'est devine.
"""
_PRIMITIVES = {'boolean', 'byte', 'short', 'char', 'int', 'long', 'float', 'double'}
_BOXES = {'Boolean', 'Byte', 'Short', 'Character', 'Integer', 'Long', 'Float', 'Double'}
# Les types de parametre que cette regle sait juger ; tout autre parametre accepte tout litteral.
KNOWN = _PRIMITIVES | _BOXES | {'Number', 'String', 'CharSequence', 'Object'}
# Ce que chaque litteral peut recevoir parmi KNOWN, par conversion d'appel de methode (JLS 5.3) : elargissement,
# mise en boite puis elargissement de reference ; jamais de retrecissement.
_ACCEPTS = {
    'int': {'int', 'long', 'float', 'double', 'Integer', 'Number', 'Object'},
    'long': {'long', 'float', 'double', 'Long', 'Number', 'Object'},
    'float': {'float', 'double', 'Float', 'Number', 'Object'},
    'double': {'double', 'Double', 'Number', 'Object'},
    'char': {'char', 'int', 'long', 'float', 'double', 'Character', 'Object'},
    'boolean': {'boolean', 'Boolean', 'Object'},
    'String': {'String', 'CharSequence', 'Object'},
    'null': KNOWN - _PRIMITIVES,
}


def contradicts(literal, parameter):
    """Vrai si l'argument litteral `literal` (ou None, une expression) ne peut pas etre passe au parametre ecrit."""
    if literal is None:
        return False
    if parameter.endswith('[]'):
        return literal != 'null'
    written = parameter.removeprefix('java.lang.')
    return written in KNOWN and written not in _ACCEPTS[literal]


def applicable(literals, parameters):
    """Faux si l'un des arguments litteraux contredit le parametre de meme rang."""
    return not any(contradicts(literal, parameter) for literal, parameter in zip(literals, parameters))
