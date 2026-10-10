"""Qui est l'auteur ? Taxo repond lui-meme, d'apres Git, sans appeler de modele (recit TAXO-MINIA-SEC-01, E3).

L'identite d'un auteur ne quitte jamais Taxo pour ce genre de question : la reponse est une fonction
deterministe des faits Git (`AUTHORED_BY`, nom de l'auteur du commit), affichee comme ce que Git dit.
La reconnaissance de la question est volontairement etroite : une question qui ne parle pas d'auteur suit
le chemin habituel de Minia, ou l'identite est masquee avant l'envoi.
"""
import re

AUTHORED_BY = 'AUTHORED_BY'
_ASKS = re.compile(
    r"\b(?:auteur|autrice|author)s?\b"
    r"|\bqui\s+(?:l['’]\s*)?a\s+(?:écrit|ecrit|fait|commité|commite|créé|cree|poussé|pousse|signé|signe|réalisé|realise)\b"
    r"|\bpar\s+qui\b"
    r"|\bwho\s+(?:wrote|made|committed|authored|did)\b",
    re.IGNORECASE)


def asks_author(question):
    """La question demande-t-elle l'auteur d'un ou plusieurs commits ?"""
    return bool(_ASKS.search(question or ''))


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
