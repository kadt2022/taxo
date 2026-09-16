import os
from pathlib import Path

def database_url(value=None):
    return value or os.getenv('DATABASE_URL', 'postgresql+psycopg://taxo:taxo@localhost:5432/taxo')

def allowed_roots(value=None):
    return [Path(p).resolve() for p in (value or os.getenv('TAXO_ALLOWED_ROOTS', str(Path.cwd())).split(os.pathsep))]
