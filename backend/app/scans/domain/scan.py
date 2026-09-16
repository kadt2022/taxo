from dataclasses import dataclass
from datetime import datetime

@dataclass(frozen=True)
class Scan:
    id: str
    project_id: str
    created_at: datetime
    result: dict

class ScanError(ValueError):
    pass
