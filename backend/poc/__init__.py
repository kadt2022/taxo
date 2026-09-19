"""Code jetable du POC TAXO-POC-01. N'appartient pas au moteur.

Ce paquet vit hors de `app/` pour une raison : il a le droit de regarder quelques
constructions d'un framework et d'un projet de banc, ce que le moteur n'a jamais.
Rien dans `app/` ne doit l'importer, et il n'est cable dans aucun bootstrap.

Condition de suppression : le jour ou TAXO-05 produit les memes faits F1 a F5 sur
le meme commit, ce paquet disparait. Le test qui le compare a la verite de
reference, lui, survit et change simplement de producteur.
"""
