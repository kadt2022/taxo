"""Un appel a un fournisseur que l'arret de la demande coupe a tout moment (TAXO-UX-03).

Fermer la reponse ne suffit pas : pendant l'ouverture de la connexion ou l'attente des en-tetes, il n'y a pas
encore de reponse. Un appel arretable a donc son propre client, que l'arret ferme, ce qui interrompt aussi
une requete en attente. Sans jeton d'arret, le client partage de l'adaptateur sert, comme avant.
"""
from contextlib import contextmanager


@contextmanager
def client_for(shared, make, cancel):
    if cancel is None:
        yield shared
        return
    client = make()
    forget = cancel.on_cancel(client.close)
    try:
        yield client
    finally:
        forget()
        client.close()
