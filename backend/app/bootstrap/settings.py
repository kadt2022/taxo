import os
from pathlib import Path

def database_url(value=None):
    return value or os.getenv('DATABASE_URL', 'postgresql+psycopg://taxo:taxo@localhost:5432/taxo')

def allowed_roots(value=None):
    return [Path(p).resolve() for p in (value or os.getenv('TAXO_ALLOWED_ROOTS', str(Path.cwd())).split(os.pathsep))]

def hypotheses_models(value=None):
    """Modeles a preparer au demarrage : TAXO_HYPOTHESES vide = mode documentaire, rien n'est telecharge."""
    raw = value if value is not None else os.getenv('TAXO_HYPOTHESES', '')
    return [name.strip() for name in raw.split(',') if name.strip()]
