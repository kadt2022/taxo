from enum import StrEnum


class EvaluationStatus(StrEnum):
    RUNNING = 'RUNNING'
    SUCCESS = 'SUCCESS'
    PARTIAL = 'PARTIAL'
    FAILED = 'FAILED'
    UNSUPPORTED = 'UNSUPPORTED'
