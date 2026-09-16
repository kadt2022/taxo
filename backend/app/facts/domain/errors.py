from dataclasses import dataclass

@dataclass(frozen=True)
class ValidationIssue:
    code: str
    path: str
    message: str


class FactValidationError(ValueError):
    def __init__(self, issues):
        self.issues = tuple(issues)
        super().__init__('; '.join(f'{i.path}: {i.message}' for i in self.issues))


def _pointer(parts):
    return '/' + '/'.join(str(p).replace('~', '~0').replace('/', '~1') for p in parts)
