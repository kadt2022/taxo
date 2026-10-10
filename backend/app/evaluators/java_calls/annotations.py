"""Les annotations écrites sur les types et les méthodes des sources, en observations (récit TAXO-MIP-ADT-01, PR A2).

Une annotation est relevée telle qu'elle est écrite, sans aucune connaissance de son rôle : `@Service`, `@Toto` et
`@PreAuthorize` sont traitées de la même façon. Taxo ne sait pas si elle vient d'un cadre, si elle agit, ni ce qu'elle
protège ; il dit seulement qu'elle est là, avec ses arguments.

Le nom de l'annotation devient la référence `annotation:<nom>`, choisi par une règle mécanique dite dans le
qualificatif `resolution` :

- `SOURCE_TYPE` : un type des sources que le code écrit désigne sans ambiguïté ;
- `IMPORTED` : le nom qualifié d'un import explicite ;
- `AS_WRITTEN` : le nom tel qu'il est écrit, faute d'une désignation sûre (import `*`, `java.lang`, même paquetage
  hors des sources). Deux annotations de même nom écrit peuvent alors partager une référence : le qualificatif le dit.

Chaque argument est rendu dans sa forme écrite ; sa valeur n'est ajoutée que si le code l'écrit (chaîne, concaténation,
constante des sources), et `resolved` dit lequel des deux cas s'applique.
"""
from dataclasses import dataclass

SOURCE_TYPE, IMPORTED, AS_WRITTEN = 'SOURCE_TYPE', 'IMPORTED', 'AS_WRITTEN'


@dataclass(frozen=True)
class Annotated:
    """Une annotation relevée : la référence qu'elle reçoit, ses qualificatifs, et les lignes qui l'écrivent."""
    reference: str
    qualifiers: dict
    line_start: int
    line_end: int


def _name(java_file, written, owner):
    resolved = java_file.resolve(written, owner)
    if resolved is not None:
        return resolved, SOURCE_TYPE
    imported = java_file.imported(written) if '.' not in written else None
    if imported is not None:
        return imported, IMPORTED
    return written, AS_WRITTEN


def _arguments(annotation):
    return {name: [{'written': value.written, 'resolved': value.resolved,
                    **({'value': value.text} if value.resolved else {})} for value in values]
            for name, values in sorted(annotation.arguments.items())}


def read(java_file, annotation, owner):
    """L'annotation `annotation`, écrite dans le type `owner` du fichier `java_file`."""
    name, resolution = _name(java_file, annotation.name, owner)
    qualifiers = {'written_name': annotation.name, 'resolution': resolution}
    arguments = _arguments(annotation)
    if arguments:
        qualifiers['arguments'] = arguments
    return Annotated(f'annotation:{name}', qualifiers, annotation.line_start, annotation.line_end)
