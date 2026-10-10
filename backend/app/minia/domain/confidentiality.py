"""Ce qu'un fournisseur de modele recoit : une representation controlee, jamais les valeurs d'origine
(recit TAXO-MINIA-SEC-01, E3 ; ARCHITECTURE § 12.6).

Taxo garde localement les valeurs d'origine ; le modele ne voit que leur version protegee :

- une **personne** (auteur Git, courriel) devient un pseudonyme propre a la demande (`personne-1`) : deux
  mentions d'une meme personne gardent le meme pseudonyme, la relation entre identites reste lisible ;
- un **secret** (mot de passe, jeton, cle privee, identifiants dans une URL) devient `******`. Seule la valeur
  est masquee : `password = "******"` montre encore qu'un mot de passe est ecrit en dur ;
- les **trailers** d'un message de commit (`Co-Authored-By`, `Signed-off-by`...) sont retires.

Le message est lu comme du JSON, valeur par valeur : une forme inattendue est refusee, jamais envoyee telle
quelle. Apres protection, un dernier controle cherche encore un courriel, un secret de forme connue ou une
identite connue ; s'il en trouve, la transmission est refusee. Une demande a sa propre `Disclosure` : les
pseudonymes ne survivent pas a la demande, et rien de ce qu'elle protege n'est journalise.
"""
import json
import re

from .errors import CONFIDENTIALITY_REFUSED, MiniaError

MASK = '******'
PSEUDONYM = 'personne-{}'
_PERSON = 'person:'
# Une partie de nom plus courte n'est pas remplacee seule : trop de mots du code lui ressembleraient.
MIN_NAME_PART = 3

# Le domaine peut n'avoir qu'un label (`root@localhost`) : une adresse locale reste une adresse.
_EMAIL = re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*')
_PSEUDONYM = re.compile(r'personne-[1-9]\d*')
# Une reference de Taxo (`file:src/A.java`, `class:com.x.A`) : ses noms ne sont pas des personnes.
_REFERENCE = re.compile(r'(?!person:)[a-z][a-z_-]*:\S+')
_TRAILER_LINE = r'[ \t]*(?:[A-Za-z][\w-]*-by|Co-authored|Cc|Change-Id|Claude-Session)[ \t]*:[^\r\n]*'
# Les trailers d'un message de commit forment son dernier paragraphe : une ligne de meme forme ailleurs (`order-by:`
# dans un fichier) n'en est pas un et reste transmise.
_TRAILERS = re.compile(rf'(?:\A|(?<=\n)[ \t]*\r?\n)(?P<block>{_TRAILER_LINE}(?:\r?\n{_TRAILER_LINE})*)\s*\Z',
                       re.IGNORECASE)
# Secrets de forme connue : remplaces en entier.
_TOKENS = re.compile('|'.join((
    r'-----BEGIN[A-Z ]*PRIVATE KEY-----[\s\S]*?(?:-----END[A-Z ]*PRIVATE KEY-----|$)',
    r'\b(?:AKIA|ASIA)[0-9A-Z]{16}\b',
    r'\bgh[pousr]_[A-Za-z0-9]{20,}\b',
    r'\bgithub_pat_[A-Za-z0-9_]{20,}\b',
    r'\bxox[abposr]-[A-Za-z0-9-]{10,}\b',
    r'\bsk-[A-Za-z0-9_-]{16,}\b',
    r'\bAIza[0-9A-Za-z_-]{35}\b',
    r'\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b',
)))
# Identifiants dans une URL : `scheme://utilisateur:motdepasse@hote`.
_URL_CREDENTIALS = re.compile(r'(\b[a-z][a-z0-9+.-]*://)[^\s/:@]+:[^\s/@]+@', re.IGNORECASE)
_SECRET_NAME = r'[\w.-]*(?:password|passwd|pwd|secret|token|api[_-]?key|apikey|access[_-]?key|private[_-]?key|credentials?)[\w.-]*'
# Une valeur affectee a un nom de secret : `password = "x"`, `password: x`, `.password("x")`, `"token": "x"`, ou un
# bloc YAML (`password: |` puis des lignes indentees), masque en entier. Une chaine citee peut echapper ses guillemets.
_BLOCK = r'[|>][-+]?[ \t]*\r?\n(?:(?:[ \t]*\r?\n)*[ \t]+\S[^\r\n]*(?:\r?\n|$))+'
_ASSIGNED = re.compile(
    rf'(?P<name>\b{_SECRET_NAME}["\']?)(?P<sep>\s*(?:[:=]|=>)\s*|\(\s*)'
    rf'(?P<value>{_BLOCK}|"(?:[^"\\\n]|\\.)*"|\'(?:[^\'\\\n]|\\.)*\'|[^\s"\',;(){{}}\[\]]+(?![\w(.{{]))',
    re.IGNORECASE)
# Valeurs qui ne sont pas des secrets : vides, litteraux, ou renvoi a une variable d'environnement.
_NOT_A_SECRET = re.compile(r'["\']?(?:|null|none|true|false|\$\{[^}]*\}|\*+)["\']?', re.IGNORECASE)


def _strip_trailers(text):
    """Le texte sans le paragraphe final de trailers, et le nombre de trailers retires."""
    match = _TRAILERS.search(text)
    if match is None:
        return text, 0
    return text[:match.start()].rstrip('\r\n'), len(match['block'].splitlines())


def _identity_parts(value, words=True):
    """Les formes sous lesquelles une identite peut reapparaitre : entiere, courriel, nom complet ; et, si `words`,
    la partie locale du courriel et chaque mot du nom."""
    value = value.strip()
    parts = {value} if value else set()
    for email in _EMAIL.findall(value):
        parts.add(email)
        local = email.split('@', 1)[0]
        if words and len(local) >= MIN_NAME_PART:
            parts.add(local)
    name = _EMAIL.sub(' ', value).replace('<', ' ').replace('>', ' ')
    names = [word for word in re.split(r'[\s,;]+', name) if word]
    if names:
        parts.add(' '.join(names))
    if words:
        parts.update(word for word in names if len(word) >= MIN_NAME_PART)
        return parts
    # Sans les mots : un nom d'un seul mot (`taxo`, `ci`) ressemble autant a un mot du code qu'un mot isole.
    return {part for part in parts if ' ' in part or _EMAIL.fullmatch(part)}


class Disclosure:
    """La representation controlee d'une demande : protege ce qui part vers le modele, restaure localement."""

    def __init__(self, known=()):
        """`known` : les identites connues du projet (auteurs Git), protegees meme quand le message les nomme
        sans fait qui les designe. Elles ne le sont que par un nom de plusieurs mots ou un courriel : un mot
        isole, ou un nom d'un seul mot, ressemble trop souvent a un mot du code."""
        self._pseudonyms = {}   # forme d'une identite -> pseudonyme
        self._displays = {}     # pseudonyme -> nom affiche localement
        self._references = {}   # pseudonyme -> reference `person:` d'origine
        self._protected = {}    # reference envoyee (courriel remplace) -> reference d'origine
        self._anchored = set()  # pseudonymes lies a un courriel ou a une reference `person:`
        self._withheld = {'identities': set(), 'secrets': 0, 'trailers': 0}
        for identity in known:
            self._identity(identity, words=False)

    # Protection -------------------------------------------------------------------------------------------

    def protect(self, message):
        """Le message, protege. Refuse (MiniaError) ce qui n'est pas un objet JSON, ou ce qui fuirait encore."""
        try:
            payload = json.loads(message)
        except (TypeError, ValueError) as exc:
            raise MiniaError(CONFIDENTIALITY_REFUSED, 'Message de forme inattendue : Taxo ne peut pas garantir '
                             'sa confidentialité, il n’est pas transmis au modèle.') from exc
        # D'abord les faits AUTHORED_BY, qui lient un nom a son courriel ; puis toutes les autres mentions.
        self._collect(payload, authored_only=True)
        self._collect(payload)
        protected = json.dumps(self._value(payload), ensure_ascii=False, separators=(',', ':'))
        self._check(protected)
        return protected

    def _collect(self, value, author_field=False, authored_only=False):
        """Repere les identites avant toute ecriture : une personne citee plus loin est masquee partout."""
        if isinstance(value, dict):
            authored = value.get('relation') == 'AUTHORED_BY'
            for key, item in value.items():
                self._collect(item, author_field=key == 'author', authored_only=authored_only)
            if authored:
                names = [(value.get('qualifiers') or {}).get('name')]
                references = [item for item in value.values() if isinstance(item, str) and item.startswith(_PERSON)]
                self._identity(*references, *[name for name in names if isinstance(name, str)])
        elif isinstance(value, list):
            for item in value:
                self._collect(item, authored_only=authored_only)
        elif isinstance(value, str) and not authored_only:
            if _REFERENCE.fullmatch(value) is None:
                # Une identite citee seulement dans un trailer n'est pas transmise : rien a lui attribuer.
                value, _ = _strip_trailers(value)
            if author_field:
                self._identity(value)
            if value.startswith(_PERSON):
                self._identity(value)
            for email in _EMAIL.findall(value):
                self._identity(email)

    def _identity(self, *forms, words=True):
        """Une personne, sous une ou plusieurs formes (reference, nom, courriel) : un seul pseudonyme."""
        forms = [form.strip() for form in forms if form and form.strip()]
        if not forms:
            return
        plain = [form.removeprefix(_PERSON) for form in forms]
        parts = set().union(*(_identity_parts(form, words) for form in plain))
        if not parts:
            return
        # Deux mentions ne sont liees que par une forme entiere ou un courriel, jamais par un mot du nom :
        # deux personnes qui partagent un prenom gardent deux pseudonymes. Une identite qui a un courriel ou
        # une reference n'est liee que par eux : deux auteurs homonymes aux courriels differents restent deux.
        emails = {email for form in plain for email in _EMAIL.findall(form)}
        identified = emails | {form.removeprefix(_PERSON) for form in forms if form.startswith(_PERSON)}
        known = next((self._pseudonyms[form] for form in sorted(identified) if form in self._pseudonyms), None)
        if known is None:
            # Un nom deja vu sans courriel (un auteur cite seulement par son nom) se lie a son courriel ; un nom deja
            # lie a un autre courriel, non.
            named = (self._pseudonyms.get(form) for form in sorted(plain))
            known = next((item for item in named if item and not (identified and item in self._anchored)), None)
        pseudonym = known or PSEUDONYM.format(len(self._displays) + 1)
        if identified:
            self._anchored.add(pseudonym)
        self._displays.setdefault(pseudonym, next((form for form in plain if not _EMAIL.fullmatch(form)), plain[0]))
        for form in forms:
            if form.startswith(_PERSON):
                self._references.setdefault(pseudonym, form)
        for part in parts:
            self._pseudonyms.setdefault(part, pseudonym)

    def _value(self, value):
        if isinstance(value, dict):
            return {key: self._value(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._value(item) for item in value]
        if isinstance(value, str):
            return self._text(value)
        return value

    def _text(self, text):
        if text.startswith(_PERSON):
            pseudonym = self._pseudonyms.get(text.removeprefix(_PERSON).strip())
            if pseudonym:
                self._withheld['identities'].add(pseudonym)
                return _PERSON + pseudonym
        reference = _REFERENCE.fullmatch(text) is not None
        if not reference:
            text, removed = _strip_trailers(text)
            self._withheld['trailers'] += removed
        protected = self._people(self._secrets(text), names=not reference)
        if reference and protected != text:
            self._protected[protected] = text
        return protected

    def _secrets(self, text):
        text, found = _TOKENS.subn(MASK, text)
        text, credentials = _URL_CREDENTIALS.subn(rf'\g<1>{MASK}:{MASK}@', text)
        self._withheld['secrets'] += found + credentials

        def assigned(match):
            value = match['value']
            quote = value[0] if value[0] in '"\'' and value[-1] == value[0] and len(value) > 1 else ''
            # Un argument non cite (`.password(encoder)`) est une variable du code, pas une valeur ecrite.
            if _NOT_A_SECRET.fullmatch(value) or (match['sep'].startswith('(') and not quote):
                return match[0]
            self._withheld['secrets'] += 1
            # Un bloc masque garde sa fin de ligne : la ligne suivante reste a sa place.
            end = value[len(value.rstrip('\r\n')):] if value[0] in '|>' else ''
            return f"{match['name']}{match['sep']}{quote}{MASK}{quote}{end}"
        return _ASSIGNED.sub(assigned, text)

    def _people(self, text, names=True):
        """Remplace chaque forme connue d'une identite par son pseudonyme (la plus longue d'abord)."""
        forms = [form for form in self._pseudonyms if names or _EMAIL.fullmatch(form)]
        if not forms:
            return text
        # Une identite reecrite dans une autre casse (`ADA LOVELACE`) reste la meme personne.
        folded = {}
        for form in forms:
            folded.setdefault(form.casefold(), self._pseudonyms[form])
        alternation = '|'.join(re.escape(form) for form in sorted(forms, key=len, reverse=True))
        pattern = re.compile(rf'(?<![\w.@-])(?:{alternation})(?![\w@-])', re.IGNORECASE)

        def pseudonym(match):
            found = folded[match[0].casefold()]
            self._withheld['identities'].add(found)
            return found
        text = pattern.sub(pseudonym, text)
        # Un courriel inconnu (dans un diff, un message) est masque lui aussi.
        return _EMAIL.sub(lambda match: self._unknown_email(match[0]), text)

    def _unknown_email(self, email):
        self._identity(email)
        pseudonym = self._pseudonyms[email]
        self._withheld['identities'].add(pseudonym)
        return pseudonym

    def _check(self, protected):
        """Dernier controle avant l'envoi : rien de ce qui doit etre protege ne subsiste."""
        whole = [form for form in self._pseudonyms if ' ' in form or _EMAIL.fullmatch(form)]
        leaked = (_EMAIL.search(protected) or _TOKENS.search(protected)
                  or any(re.search(rf'(?<![\w.@-]){re.escape(form)}(?![\w@-])', protected, re.IGNORECASE)
                         for form in whole))
        if leaked:
            raise MiniaError(CONFIDENTIALITY_REFUSED, 'Une donnée confidentielle subsiste après protection : '
                             'le message n’est pas transmis au modèle.')

    # Restitution locale -----------------------------------------------------------------------------------

    def restore(self, value):
        """Ce que le modele a rendu, avec les identites d'origine : pour Taxo et pour l'affichage local.

        Une reference `person:personne-N` redevient la reference d'origine ; un pseudonyme seul, le nom.
        Un secret masque ne se restaure pas : le modele ne l'a jamais eu.
        """
        if isinstance(value, dict):
            return {key: self.restore(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self.restore(item) for item in value]
        if isinstance(value, tuple):
            return tuple(self.restore(item) for item in value)
        if not isinstance(value, str) or not self._displays:
            return value
        if value.startswith(_PERSON) and value.removeprefix(_PERSON) in self._references:
            return self._references[value.removeprefix(_PERSON)]
        if value in self._protected:
            return self._protected[value]
        if _REFERENCE.fullmatch(value) is not None:
            # Une autre reference (`file:personne-1.md`) n'a jamais porte de pseudonyme : elle reste telle quelle.
            return value
        return _PSEUDONYM.sub(lambda match: self._displays.get(match[0], match[0]), value)

    def report(self):
        """Ce qui a ete retenu, compte, sans aucune valeur : pour la transparence de la reponse (E4)."""
        return {'identities': len(self._withheld['identities']), 'secrets': self._withheld['secrets'],
                'trailers': self._withheld['trailers']}
