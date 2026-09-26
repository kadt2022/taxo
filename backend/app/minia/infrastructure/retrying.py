"""Appel a une API distante de Minia, avec reprise des erreurs passageres (surcharge, passerelle, reseau).

Rien n'a encore ete diffuse quand la reprise a lieu : reessayer ne change pas ce que voit l'utilisateur.
Un quota atteint (429) ou une erreur de la demande ne sont jamais reessayes.
"""
import httpx

from app.minia.domain.cancellation import check as stopped

# Erreurs passageres (surcharge, passerelle) : reessayees avant tout texte, avec une attente croissante.
TRANSIENT = frozenset({500, 502, 503, 504})
RETRIES = 2
BACKOFF_SECONDS = 1.5


def send(client, url, body, headers, stream, sleep, check, unreachable, cancel=None):
    """Reponse 200 de l'API ; `check(reponse)` dit l'erreur en clair, `unreachable()` la panne reseau. Une
    demande arretee n'envoie plus rien : ni nouvelle tentative, ni attente entre deux tentatives."""
    def pause(seconds):
        if cancel is None:
            sleep(seconds)
        else:
            cancel.wait(seconds)

    for attempt in range(RETRIES + 1):
        stopped(cancel)
        last_try = attempt == RETRIES
        try:
            response = client.send(client.build_request('POST', url, json=body, headers=headers), stream=stream)
        except httpx.HTTPError as exc:
            stopped(cancel)
            if last_try:
                raise unreachable() from exc
            pause(BACKOFF_SECONDS * 2 ** attempt)
            continue
        if response.status_code == 200:
            return response
        response.read()
        response.close()
        if response.status_code in TRANSIENT and not last_try:
            pause(BACKOFF_SECONDS * 2 ** attempt)
            continue
        check(response)
