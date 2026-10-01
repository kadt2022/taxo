from dataclasses import dataclass
from datetime import datetime

# Etat de la memoire d'une analyse (TAXO-01F) : une analyse n'existe comme telle qu'une fois son instantane,
# ses executions et tous ses faits enregistres. Une consolidation interrompue reste INCOMPLETE.
MEMORY = 'memory'
INCOMPLETE, COMPLETE = 'INCOMPLETE', 'COMPLETE'


def is_complete(result):
    """Les analyses anterieures a cet etat sont qualifiees par la migration 006."""
    return result.get(MEMORY, COMPLETE) == COMPLETE


@dataclass(frozen=True)
class Scan:
    id: str
    project_id: str
    created_at: datetime
    result: dict

class ScanError(ValueError):
    pass
