"""Public boundary for the Taxo fact contract."""

__all__ = ['FactValidationError', 'content_hash', 'fact_identity', 'identity_fields',
           'is_path', 'is_reference', 'validate_fact']


def __getattr__(name):
    # Importing a domain module must not load the JSON Schema adapter.
    if name in __all__:
        from . import contract
        return getattr(contract, name)
    raise AttributeError(f'module {__name__!r} has no attribute {name!r}')
