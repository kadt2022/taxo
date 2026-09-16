from dataclasses import dataclass

@dataclass(frozen=True)
class Project:
    id: str
    name: str
    path: str

class ProjectError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
