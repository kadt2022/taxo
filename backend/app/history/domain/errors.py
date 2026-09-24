class HistoryError(Exception):
    """Refus de lecture de l'historique, avec un code stable pour l'API."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


NOT_A_GIT_REPOSITORY = 'NOT_A_GIT_REPOSITORY'
UNKNOWN_COMMIT = 'UNKNOWN_COMMIT'
UNKNOWN_PARENT = 'UNKNOWN_PARENT'
GIT_READ_ERROR = 'GIT_READ_ERROR'
