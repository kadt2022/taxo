"""Load ORM mappings for migrations without creating an application or engine."""
from app.platform.database.base import Base
from app.projects.infrastructure.sqlalchemy.project_repository import ProjectRow
from app.scans.infrastructure.sqlalchemy.scan_repository import ScanRow

metadata = Base.metadata
