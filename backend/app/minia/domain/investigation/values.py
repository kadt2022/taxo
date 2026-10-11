"""Les enregistrements du carnet en valeurs simples (chaines, nombres, listes, objets) : pour le journal et pour
l'etat serialise. Une date devient sa forme ISO, une enumeration sa valeur."""
from dataclasses import asdict, is_dataclass
from datetime import datetime
from enum import Enum


def plain(record) -> dict:
    return {key: simple(item) for key, item in asdict(record).items()}


def simple(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return plain(value)
    if isinstance(value, (tuple, list)):
        return [simple(item) for item in value]
    if isinstance(value, dict):
        return {str(key): simple(item) for key, item in value.items()}
    return value
