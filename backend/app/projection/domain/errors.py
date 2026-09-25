class QueryError(Exception):
    """Une requete que Taxo ne peut pas servir, avec un code stable pour l'API."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


INVALID_REQUEST = 'INVALID_REQUEST'
NO_ANALYSIS = 'NO_ANALYSIS'
