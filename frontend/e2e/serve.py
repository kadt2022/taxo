"""Le serveur Taxo du parcours de bout en bout (TAXO-01J) : un dossier neuf, le dépôt scénarisé commité, une base
SQLite migrée, puis l'API. Usage : python e2e/serve.py <dossier> <port>. Le dossier est effacé au départ."""
import os
import shutil
import subprocess
import sys
from pathlib import Path

from repository import BACKEND, write

root, port = Path(sys.argv[1]), sys.argv[2]
shutil.rmtree(root, ignore_errors=True)
write(root / 'shop')
env = {**os.environ, 'DATABASE_URL': f'sqlite:///{root / "taxo.db"}', 'TAXO_ALLOWED_ROOTS': str(root)}
subprocess.run([sys.executable, '-m', 'alembic', 'upgrade', 'head'], cwd=BACKEND, env=env, check=True)
os.chdir(BACKEND)
os.execvpe(sys.executable, [sys.executable, '-m', 'uvicorn', 'app.main:create_app', '--factory', '--host', '127.0.0.1',
                            '--port', port], env)
