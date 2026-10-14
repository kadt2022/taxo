"""Journal de développement des échanges de Minia, dans la console du serveur (MINIA_TRACE).

Désactivé par défaut (`off`). Pour les essais :

- `summary` : chaque opération demandée à Taxo (arguments, issue, taille) et chaque tour du modèle (taille du message
  envoyé, début de sa réponse brute) ;
- `full` : en plus, la réponse complète de Taxo, le message complet envoyé au modèle et sa réponse complète.

Deux sortes de lignes :

- `TAXO` : la réponse de Taxo telle qu'il la sert, avec les valeurs d'origine (comme l'explorateur du portail) ; elle ne
  quitte pas la machine ;
- `LLM` : le message qui part réellement vers le fournisseur, **après** la protection de la demande (identités
  pseudonymisées, secrets masqués), et sa réponse brute, avant la restitution des valeurs d'origine.

Le journal n'écrit que sur la sortie d'erreur de la console : Taxo n'en conserve rien. Ne pas l'activer sur une
machine partagée : en mode `full`, le code lu (`get_source`, sous double consentement) y apparaît.
"""
import json
import logging
import sys

OFF, SUMMARY, FULL = 'off', 'summary', 'full'
MODES = (OFF, SUMMARY, FULL)
# Le début d'une réponse en mode `summary`.
PREVIEW = 300
LOGGER = logging.getLogger('taxo.minia.trace')
_state = {'mode': OFF}


def configure(mode, stream=None):
    """Choisit le niveau du journal ; un niveau inconnu est refusé au démarrage."""
    mode = (mode or OFF).strip().lower()
    if mode not in MODES:
        raise ValueError(f'MINIA_TRACE invalide : {mode} (off, summary ou full).')
    _state['mode'] = mode
    for handler in list(LOGGER.handlers):
        LOGGER.removeHandler(handler)
    LOGGER.propagate = False
    if mode != OFF:
        handler = logging.StreamHandler(stream or sys.stderr)
        handler.setFormatter(logging.Formatter('[minia-trace] %(message)s'))
        LOGGER.addHandler(handler)
        LOGGER.setLevel(logging.INFO)


def active():
    return _state['mode'] != OFF


def _full():
    return _state['mode'] == FULL


def _size(text):
    return len(text.encode('utf-8')) if isinstance(text, str) else 0


def _cut(text):
    return text if len(text) <= PREVIEW else f'{text[:PREVIEW]}… ({_size(text)} octets)'


def taxo(operation, arguments, response):
    """Une opération servie par Taxo, telle que Minia la reçoit."""
    if not active():
        return
    outcome = response.get('outcome')
    detail = response.get('error', {}).get('code', '') if outcome != 'OK' else ''
    LOGGER.info('TAXO %s %s -> %s%s, %s octets', operation, json.dumps(arguments, ensure_ascii=False), outcome,
                f' {detail}' if detail else '', response.get('bytes'))
    if _full():
        LOGGER.info('TAXO réponse : %s', json.dumps(response, ensure_ascii=False))


def note(message):
    """Un événement de Minia qui n'est ni une opération de Taxo ni un tour du modèle (la garde de conclusion)."""
    if active():
        LOGGER.info('MINIA %s', message)


def sent(model, system, user):
    """Un tour envoyé au modèle, après protection."""
    if not active():
        return
    LOGGER.info('LLM -> %s/%s : message %s octets (consignes %s octets)', getattr(model, 'provider', '?'),
                getattr(model, 'model_name', '?'), _size(user), _size(system))
    if _full():
        LOGGER.info('LLM consignes : %s', system)
        LOGGER.info('LLM message : %s', user)


def usage(model, call):
    """Ce que le fournisseur rapporte d'un appel (R0) : des compteurs, jamais de contenu."""
    if not active():
        return
    said = lambda key: 'non rapporté' if call.get(key) is None else call[key]
    LOGGER.info('LLM usage %s/%s : entrée %s · cache lu %s · cache écrit %s · sortie %s · raisonnement %s · '
                'envoyé %s octets%s', getattr(model, 'provider', '?'), getattr(model, 'model_name', '?'),
                said('input'), said('cache_read'), said('cache_write'), said('output'), said('reasoning'),
                call.get('system_bytes', 0) + call.get('message_bytes', 0), ' (appel échoué)' if call.get('failed') else '')


def received(model, reply, served=None):
    """La réponse brute du modèle, avant toute restitution des valeurs d'origine. `served` : le modèle qui a
    réellement répondu, quand le fournisseur le dit (un repli côté serveur, une version datée)."""
    if not active():
        return reply
    text = reply if isinstance(reply, str) else str(reply)
    name = served if isinstance(served, str) and served else getattr(model, 'model_name', '?')
    LOGGER.info('LLM <- %s/%s : %s octets : %s', getattr(model, 'provider', '?'), name, _size(text),
                text if _full() else _cut(text))
    return reply


def streamed(model, pieces):
    """Une réponse diffusée : transmise morceau par morceau, journalisée en entier à la fin. Ce que le flux rend en
    fin (le modèle qui a réellement répondu) est rendu tel quel ; fermer ce flux ferme celui du fournisseur."""
    if not active():
        return (yield from pieces)
    said, iterator = [], iter(pieces)
    try:
        while True:
            try:
                piece = next(iterator)
            except StopIteration as end:
                received(model, ''.join(said), end.value)
                return end.value
            said.append(piece if isinstance(piece, str) else str(piece))
            yield piece
    finally:
        close = getattr(iterator, 'close', None)
        if close is not None:
            close()
