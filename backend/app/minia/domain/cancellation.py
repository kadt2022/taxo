"""Arreter une demande a Minia (TAXO-UX-03) : un jeton par demande, partage par Taxo et le fournisseur.

Taxo le consulte avant chaque operation, avant chaque tour du modele et pendant l'attente du modele ; le
fournisseur y inscrit de quoi couper son appel en cours (fermer la connexion), pour que l'arret ne se
contente pas de masquer un resultat : le travail s'arrete vraiment. Une demande arretee ne produit aucune
reponse finale, et rien n'en est conserve.
"""
import threading

from .errors import CANCELLED, MiniaError

STOPPED = 'Analyse arrêtée par l’utilisateur.'


class Cancellation:
    def __init__(self):
        self._event = threading.Event()
        self._lock = threading.Lock()
        self._callbacks = []

    @property
    def cancelled(self):
        return self._event.is_set()

    def cancel(self):
        """Arrete la demande : les appels en cours inscrits sont coupes, une seule fois."""
        with self._lock:
            if self._event.is_set():
                return
            self._event.set()
            callbacks, self._callbacks = self._callbacks, []
        for callback in callbacks:
            try:
                callback()
            except Exception:  # noqa: BLE001 - couper un appel deja fini ou deja ferme n'est pas une erreur
                pass

    def on_cancel(self, callback):
        """Inscrit `callback` (couper un appel en cours) ; rend de quoi le desinscrire quand l'appel finit."""
        with self._lock:
            if not self._event.is_set():
                self._callbacks.append(callback)
                return lambda: self._forget(callback)
        callback()
        return lambda: None

    def _forget(self, callback):
        with self._lock:
            if callback in self._callbacks:
                self._callbacks.remove(callback)

    def check(self):
        """Leve MiniaError(CANCELLED) si la demande a ete arretee."""
        if self._event.is_set():
            raise MiniaError(CANCELLED, STOPPED)


def check(cancel):
    if cancel is not None:
        cancel.check()
