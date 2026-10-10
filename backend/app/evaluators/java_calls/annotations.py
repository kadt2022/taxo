"""Les annotations écrites sur les types et les méthodes des sources, en observations (récit TAXO-MIP-ADT-01, PR A2).

Une annotation est relevée telle qu'elle est écrite, sans aucune connaissance de son rôle : `@Service`, `@Toto` et
`@PreAuthorize` sont traitées de la même façon. Taxo ne sait pas si elle vient d'un cadre, si elle agit, ni ce qu'elle
protège ; il dit seulement qu'elle est là, avec ses arguments.

Le nom de l'annotation devient la référence `annotation:<nom>`, choisi par une règle mécanique dite dans le
qualificatif `resolution` :

- `SOURCE_TYPE` : un type des sources que le code écrit désigne sans ambiguïté ;
- `IMPORTED` : le nom qualifié d'un import explicite (simple ou statique, d'un type membre aussi) ;
- `AS_WRITTEN` : le nom tel qu'il est écrit, faute d'une désignation sûre (import `*`, même vers un type des
  sources, `java.lang`, même paquetage hors des sources). Deux annotations de même nom écrit peuvent alors partager
  une référence : le qualificatif le dit.

Les arguments forment une liste ordonnée par nom (`name`, `values`). Chaque valeur est rendue dans sa forme écrite ;
son texte n'est ajouté que si le code l'écrit (chaîne, concaténation, constante des sources), et `resolved` dit
lequel des deux cas s'applique.
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


def _imported(java_file, written):
    """Le nom qualifié que désigne un import explicite du premier segment écrit (`import p.H;` pour `@H.A`, ou
    `import static p.H.A;` pour `@A`, un type membre) ; None sans un tel import. Un import `*` ne désigne rien."""
    head, _, rest = written.partition('.')
    name = next((name for name, _ in java_file.imports if name.rsplit('.', 1)[-1] == head), None)
    return None if name is None else f'{name}.{rest}' if rest else name


def _name(java_file, written, owner):
    resolved = java_file.resolve(written, owner, on_demand=False)
    if resolved is not None:
        return resolved, SOURCE_TYPE
    imported = _imported(java_file, written)
    if imported is not None:
        # Un type membre des sources importé statiquement reste un type des sources.
        source = java_file.resolve(imported, owner, on_demand=False)
        return (source, SOURCE_TYPE) if source is not None else (imported, IMPORTED)
    return written, AS_WRITTEN


def _arguments(annotation):
    """Les arguments dans l'ordre de leur nom. Le nom est une valeur, jamais une clé : un nom d'élément écrit
    (`confidence`, par exemple) ne peut pas devenir une clé de qualificatif que le contrat des faits refuse."""
    return [{'name': name, 'values': [{'written': value.written, 'resolved': value.resolved,
                                       **({'value': value.text} if value.resolved else {})} for value in values]}
            for name, values in sorted(annotation.arguments.items())]


def read(java_file, annotation, owner):
    """L'annotation `annotation`, écrite dans le type `owner` du fichier `java_file`."""
    name, resolution = _name(java_file, annotation.name, owner)
    qualifiers = {'written_name': annotation.name, 'resolution': resolution}
    arguments = _arguments(annotation)
    if arguments:
        qualifiers['arguments'] = arguments
    return Annotated(f'annotation:{name}', qualifiers, annotation.line_start, annotation.line_end)
