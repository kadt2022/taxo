"""Qui est l'auteur ? Taxo repond lui-meme, d'apres Git, sans appeler de modele (recit TAXO-MINIA-SEC-01, E3).

L'identite d'un auteur ne quitte jamais Taxo pour ce genre de question : la reponse est une fonction
deterministe des faits Git (`AUTHORED_BY`, nom de l'auteur du commit), affichee comme ce que Git dit.
La reconnaissance de la question est volontairement etroite : une question qui ne parle pas d'auteur suit
le chemin habituel de Minia, ou l'identite est masquee avant l'envoi.
"""
import re

AUTHORED_BY = 'AUTHORED_BY'
_COMMIT_OBJECT = r"(?:ce|cet|ces|le|les|la|l['’]\s*|this|these|that|the)\s*(?:[\w-]+\s+){0,3}commits?\b"
# Seule une demande explicite d'auteur est reconnue : « qui est l'auteur », « l'auteur du commit », « qui a
# écrit ce commit ». « Qui a fait échouer les tests ? » ou « who did this change affect? » restent a Minia.
_ASKS = re.compile(
    r"\b(?:qui|quel(?:le)?s?)\s+(?:est|sont|était|etait|étaient|etaient)\s+(?:l['’]\s*|les?\s+|la\s+)?(?:auteur|autrice)s?\b"
    r"|\b(?:auteur|autrice)s?\s+(?:du|des|de\s+(?:ce|cet|ces|la|l['’]))\s*(?:[\w-]+\s+){0,3}commits?\b"
    r"|\bqui\s+(?:l['’]\s*)?a\s+(?:écrit|ecrit|fait|commité|commite|créé|cree|poussé|pousse|signé|signe|réalisé|realise)\s+" + _COMMIT_OBJECT +
    r"|\bwho\s+(?:is|are|was|were)\s+the\s+authors?\b"
    r"|\bwho\s+(?:wrote|authored|committed|made)\s+" + _COMMIT_OBJECT +
    r"|\bauthors?\s+of\s+" + _COMMIT_OBJECT,
    re.IGNORECASE)


# Ce qui peut entourer la demande d'auteur sans rien demander d'autre : le commit vise, sa position, sa reference.
_SCOPE_WORDS = frozenset({
    'du', 'des', 'de', 'd', 'ce', 'cet', 'ces', 'cette', 'le', 'les', 'la', 'l', 'un', 'une', 'commit', 'commits',
    'dernier', 'derniers', 'dernière', 'dernières', 'derniere', 'dernieres', 'récent', 'récents', 'recent',
    'of', 'this', 'these', 'that', 'the', 'last', 'latest', 'recent', 'a', 'an', 'please', 'stp', 'svp'})
_WORD = re.compile(r"\b[0-9a-f]{7,40}\b|[^\W\d_]+|\d+", re.IGNORECASE)


def asks_author(question):
    """La question ne demande-t-elle que l'auteur d'un ou plusieurs commits ? Une question qui demande autre chose
    en plus (« qui l'a écrit et quel est son impact ? ») reste a Minia : la reponse directe en perdrait une partie."""
    question = question or ''
    match = _ASKS.search(question)
    if match is None:
        return False
    rest = question[:match.start()] + ' ' + question[match.end():]
    return all(word.lower() in _SCOPE_WORDS or word.isdigit() or re.fullmatch(r'[0-9a-f]{7,40}', word, re.I)
               for word in _WORD.findall(rest))


def commit_answer(commit):
    """La reponse pour un commit : son auteur selon Git, ou l'absence d'auteur."""
    short = commit.sha[:12]
    if not (commit.author or '').strip():
        return f'Git n’indique aucun auteur pour le commit {short}.'
    return f'Selon Git, l’auteur du commit {short} est {commit.author.strip()}.'


def _author(fact):
    name = (fact.get('qualifiers') or {}).get('name')
    return name.strip() if isinstance(name, str) and name.strip() else str(fact.get('object', '')).removeprefix('person:')


def selection_answer(facts):
    """La reponse pour une selection de commits : l'auteur de chacun, et les faits AUTHORED_BY qui l'appuient.

    Rend (texte, faits cites) ; un commit sans fait AUTHORED_BY n'est pas suppose avoir un auteur.
    """
    authored = [fact for fact in facts if fact.get('relation') == AUTHORED_BY]
    if not authored:
        return 'Taxo ne connaît aucun auteur pour cette sélection de commits.', []
    lines = [f"{fact['subject'].removeprefix('commit:')[:12]} : {_author(fact)}" for fact in authored]
    return 'Selon Git : ' + ' ; '.join(lines) + '.', authored
