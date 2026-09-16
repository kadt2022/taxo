NOT_A_GIT_REPOSITORY = 'NOT_A_GIT_REPOSITORY'
UNKNOWN_COMMIT = 'UNKNOWN_COMMIT'
GIT_READ_ERROR = 'GIT_READ_ERROR'
UNSUPPORTED_GIT_ENTRY = 'UNSUPPORTED_GIT_ENTRY'
WORKING_TREE_READ_ERROR = 'WORKING_TREE_READ_ERROR'

class SnapshotError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
