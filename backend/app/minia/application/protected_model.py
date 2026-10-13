"""Le seul passage vers un fournisseur de modele : chaque message y est protege avant l'appel (recit
TAXO-MINIA-SEC-01, E3).

Minia ne parle jamais directement a un fournisseur : chaque demande enveloppe le modele choisi dans un
`ProtectedModel`, qui fait passer le message de chaque tour par la `Disclosure` de la demande. La protection
ne depend donc ni des consignes du modele, ni de l'endroit ou le message a ete construit. Les consignes
(`system`) sont des textes fixes de Taxo, sans donnee du projet : elles passent telles quelles.
"""
import inspect

from app.minia.application import trace


def _accepts(method, name):
    try:
        return name in inspect.signature(method).parameters
    except (TypeError, ValueError):
        return False


class ProtectedModel:
    """Un modele de Minia (port `MiniaModel`) dont tout message est protege ; le reste est celui du modele."""

    def __init__(self, model, disclosure):
        self._model, self.disclosure = model, disclosure
        if callable(getattr(model, 'stream', None)):
            # Un fournisseur sans diffusion reste sans diffusion : Minia le reconnait a l'absence de `stream`.
            self.stream = self._stream

    def __getattr__(self, name):
        # Fournisseur, modele, place disponible, capacite d'exploration : ceux du modele enveloppe.
        if name == 'stream':
            raise AttributeError(name)
        return getattr(self._model, name)

    def _options(self, method, schema, cancel):
        options = {} if schema is None else {'schema': schema}
        if cancel is not None and _accepts(method, 'cancel'):
            options['cancel'] = cancel
        return options

    def complete(self, system, user, schema=None, cancel=None):
        protected = self.disclosure.protect(user)
        trace.sent(self._model, system, protected)
        reply = self._model.complete(system, protected, **self._options(self._model.complete, schema, cancel))
        return trace.received(self._model, reply)

    def _stream(self, system, user, schema=None, cancel=None):
        protected = self.disclosure.protect(user)
        trace.sent(self._model, system, protected)
        return trace.streamed(self._model, self._model.stream(system, protected,
                                                             **self._options(self._model.stream, schema, cancel)))
