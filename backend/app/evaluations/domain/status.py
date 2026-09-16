from enum import StrEnum


class EvaluationStatus(StrEnum):
    SUCCESS = 'SUCCESS'
    PARTIAL = 'PARTIAL'
    FAILED = 'FAILED'
    UNSUPPORTED = 'UNSUPPORTED'
