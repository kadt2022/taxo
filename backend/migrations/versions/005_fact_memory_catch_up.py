"""Catch-up before Taxo reads the versioned memory (TAXO-01E).

An installation that ran 004 kept writing its new analyses into `analysis_facts` until the switch.
The migration of 004 is run again: analyses already migrated are skipped, the others are copied and
verified the same way. `analysis_facts` is still left untouched.
"""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from alembic import op

revision = '005'
down_revision = '004'


def _migration_004():
    # The frozen code of 004 is reused as is, never copied again.
    spec = spec_from_file_location('taxo_migration_004', Path(__file__).with_name('004_fact_memory.py'))
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def upgrade():
    migration = _migration_004()
    with op.get_context().autocommit_block():
        migration._fill(op.get_bind().engine)


def downgrade():
    """Nothing to undo: the rows copied here belong to the tables of 004."""
