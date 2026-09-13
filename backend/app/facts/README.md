# Taxo Fact Contract v1

Contrat de TAXO-01A, derive de l'ADR 0002. Ce module ne depend ni du scanner,
ni de la base, ni d'un analyseur de langage.

## Utilisation

Depuis `backend`, apres installation de `requirements.txt` :

```sh
python -m app.facts --conformance
python -m app.facts --fact app/facts/conformance/v1/valid-takibo-t19.json
python -m pytest -q
```

La commande renvoie un document JSON et un code de sortie 0 (valide) ou 1 (refuse).
`--stored` autorise les etats de validite reserves a la memoire.

```python
from app.facts import FactValidationError, validate_fact

try:
    validate_fact(fact)
except FactValidationError as error:
    for issue in error.issues:
        print(issue.code, issue.path, issue.message)
```

`validate_fact` ne modifie pas le fait. Chaque erreur porte un code, un chemin
JSON Pointer et une raison. Les valeurs rejetees ne sont pas recopiees dans les
messages. La racine est notee `/`. Les champs JSON dupliques sont refuses par
l'entree CLI ; les objets Python doivent contenir uniquement des valeurs JSON
finies (ni NaN, ni tuple, ni cle numerique).

## Frontiere de validation

`contract-v1.schema.json` utilise JSON Schema Draft 2020-12. Toutes les structures
du contrat sont fermees. Seul `qualifiers` est un dictionnaire de valeurs JSON
extensible pour les valeurs d'annotations et autres qualificatifs. Un champ dont
le nom contient `confidence` ou `confiance`, sans distinction de casse, y est
interdit, y compris dans les objets imbriques. Cela ne detecte pas les secrets
ou les scores dissimules sous un autre nom : le producteur reste responsable.

Le schema valide les structures, les champs conditionnels, les enumerations et
les formats. Le moteur doit activer la verification de `format: date-time`.
La dependance Python `jsonschema[format-nongpl]` installe ces verifications.

Le validateur semantique ajoute :

- la matrice producteur/statut ;
- les types source/cible et statuts du vocabulaire des relations ;
- l'egalite du depot et du commit entre preuve et instantane ;
- l'ordre des bornes de lignes et la syntaxe des chemins de references ;
- l'interdiction de soumettre une validite autre que `VALID`.

Le schema seul ne constitue donc pas un validateur Taxo complet.

## Decisions de representation

- `contract_version` est le nombre entier `1`. Les versions de producteur et de
  catalogue sont des chaines non vides, par exemple `"1"` et `"1.0.0"`.
- Le fait est plat : ses champs d'identite sont distincts conceptuellement de
  ceux d'occurrence. `identity_fields` en extrait une copie, sans normalisation
  ni calcul d'empreinte. Pour COVERAGE, cette copie inclut `producer_id`.
- `derivation.rule` est le nom normatif de l'ADR 0002. Le terme
  `derivation_rule` du paragraphe T13 du recit ne constitue pas un alias.
- Les premisses sont des identifiants opaques non vides en attendant TAXO-01B.
  `counter_examples_checked` et `known_gaps` sont des listes de textes,
  obligatoires mais pouvant etre vides. Les motifs ont un type et une valeur
  textuels ; le catalogue du producteur definit la semantique de leurs types.
- Les commits sont des identifiants Git complets hexadecimaux minuscules
  (40 ou 64 caracteres). Les empreintes sont `sha256:` puis 64 caracteres
  hexadecimaux minuscules. `snapshot.repository` et `evidence.repository`
  contiennent la cle du depot, pas une reference prefixee `repository:`.
- Une reference est `type:cle`. Les cles des fichiers et repertoires sont des
  chemins relatifs avec `/`, sans segment `.` ou `..`, ni `/` final.
  Le tri, la deduplication et la normalisation des references restent en 01B.
- Les lignes d'une preuve sont optionnelles mais doivent etre presentes ensemble,
  entieres, positives, et ordonnees. Une preuve sans lignes cite le fichier entier.
- `PERMITS_ALL` interdit `object`, y compris `null`. `AUTHORIZED_BY` accepte
  une reference `symbol:` ou une expression litterale textuelle, sans l'interpreter.
- La validite des occurrences conservees peut etre `STALE` ou
  `REVALIDATION_REQUIRED` ; `validate_fact(..., submission=False)` ne calcule
  aucune invalidation et n'autorise pas un producteur a soumettre ces etats.

## Empreintes

`content_hash(source_bytes, line_start=None, line_end=None)` decode en UTF-8
strict, retire les CR, selectionne les lignes LF (bornes inclusives a partir de 1),
les joint sans separateur final puis applique SHA-256. Un terminateur de fichier
n'est pas une ligne supplementaire ; une vraie ligne vide finale est conservee.
Ainsi `a\n` devient `a`, et `a\n\n` devient `a\n`. Une plage inexistante est refusee.
LF et CRLF produisent la meme empreinte. Aucun acces disque ni texte conserve.

## Conformite interlangage

`conformance/v1/manifest.json` liste des fichiers JSON autonomes, le mode de
validation, l'acceptation attendue, et pour chaque refus un code, un chemin et une
raison. `t16` rattache un cas a l'une des 18 categories du recit. Plusieurs erreurs
peuvent etre emises ; le couple attendu doit etre present. Les raisons exactes
peuvent etre traduites. Un producteur JVM peut lire ces fichiers sans Python,
appliquer le schema et les regles semantiques ci-dessus, puis comparer les resultats.
Les codes `SCHEMA_*` correspondent aux contraintes JSON Schema ; `SCHEMA_None`
designe une propriete explicitement interdite par un schema `false`.

`hash-vectors.json` fournit egalement huit vecteurs UTF-8 et leurs empreintes
attendues, dont les variantes LF/CRLF et les plages de lignes. Ces textes
synthetiques servent uniquement de donnees de test et ne sont pas des faits.

La fixture T19 reprend les references et empreintes publiees dans le recit.
Elle est un exemple de contrat, pas une analyse executee par Taxo. Les autres
empreintes et identifiants de fixtures sont synthetiques. La suite ne verifie pas
la presence du code TAKIBO sur la machine.

## Limites de TAXO-01A

Valider un fait ne prouve pas sa veracite. Le module n'ouvre aucun depot et ne
verifie ni l'existence des premisses dans l'instantane, ni les octets cites par
les preuves, ni le rattachement a une execution reelle. Ces controles necessitent
les instantanes, executions et la memoire des recits suivants. Aucun stockage,
appel LLM, calcul d'identite stable ou analyse Java/Spring n'est introduit ici.
