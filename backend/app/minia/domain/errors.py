class MiniaError(Exception):
    """Minia ne peut pas repondre, avec un code stable pour l'API."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


NOT_CONFIGURED = 'MINIA_NOT_CONFIGURED'
UNAVAILABLE = 'MINIA_UNAVAILABLE'
INVALID_ANSWER = 'MINIA_INVALID_ANSWER'
INVALID_QUESTION = 'MINIA_INVALID_QUESTION'
CONTEXT_TOO_LARGE = 'MINIA_CONTEXT_TOO_LARGE'
UNKNOWN_PROVIDER = 'MINIA_UNKNOWN_PROVIDER'
