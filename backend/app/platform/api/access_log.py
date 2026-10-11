"""Le journal des requetes ne garde jamais la valeur d'un parametre d'adresse (recit TAXO-MINIA-SEC-01, E4).

La question posee a Taxo voyage dans l'adresse (`/query?q=…`, `/elements?q=…`) : elle peut nommer un auteur ou
recopier un secret. Le journal d'acces d'uvicorn la recopierait telle quelle ; ce filtre ne lui laisse que le nom
de chaque parametre. Le chemin, la methode et le statut restent, pour le diagnostic.
"""
import logging
from urllib.parse import parse_qsl, urlsplit

from app.minia.domain.confidentiality import MASK

ACCESS_LOGGER = 'uvicorn.access'
# Position du chemin dans les arguments d'un message du journal d'acces d'uvicorn :
# (client, methode, chemin, version HTTP, statut).
_PATH = 2


def redacted(path):
    """Le chemin sans la valeur de ses parametres : `/a?q=secret&n=2` devient `/a?q=******&n=******`."""
    parts = urlsplit(path)
    if not parts.query:
        return path
    names = [name for name, _ in parse_qsl(parts.query, keep_blank_values=True)]
    query = '&'.join(f'{name}={MASK}' for name in names) if names else MASK
    return f'{parts.path}?{query}'


class RedactedQueries(logging.Filter):
    """Masque les valeurs des parametres d'adresse dans chaque message du journal d'acces."""

    def filter(self, record):
        args = record.args
        if isinstance(args, tuple) and len(args) > _PATH and isinstance(args[_PATH], str):
            record.args = (*args[:_PATH], redacted(args[_PATH]), *args[_PATH + 1:])
        return True


def redact_access_log(logger=None):
    """Installe le filtre sur le journal d'acces ; sans effet s'il y est deja."""
    logger = logger or logging.getLogger(ACCESS_LOGGER)
    if not any(isinstance(item, RedactedQueries) for item in logger.filters):
        logger.addFilter(RedactedQueries())
    return logger
