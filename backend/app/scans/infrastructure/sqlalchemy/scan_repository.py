from sqlalchemy import JSON, Column, DateTime, ForeignKey, String, select
from sqlalchemy.orm import Session
from app.platform.database.base import Base
from app.scans.domain.scan import COMPLETE, MEMORY, Scan, is_complete

class ScanRow(Base):
    __tablename__ = 'scans'
    id = Column(String, primary_key=True)
    project_id = Column(String, ForeignKey('projects.id'), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False)
    result = Column(JSON, nullable=False)


def _scan(row):
    return Scan(row.id, row.project_id, row.created_at, row.result)

class SqlAlchemyScanRepository:
    def __init__(self, engine):
        self.engine = engine

    def list(self, project_id):
        """Analyses complètes seulement : une consolidation interrompue n'est pas une analyse."""
        with Session(self.engine) as db:
            return [_scan(row) for row in db.scalars(select(ScanRow).where(
                ScanRow.project_id == project_id).order_by(ScanRow.created_at.desc())) if is_complete(row.result)]

    def get(self, project_id, scan_id):
        with Session(self.engine) as db:
            row = db.get(ScanRow, scan_id)
            found = row is not None and row.project_id == project_id and is_complete(row.result)
            return _scan(row) if found else None

    def complete(self, scan_id):
        """La mémoire de l'analyse est entière : elle devient visible et comparable."""
        with Session(self.engine) as db:
            row = db.get(ScanRow, scan_id)
            row.result = {**row.result, MEMORY: COMPLETE}
            db.commit()
            return _scan(row)

    def add(self, scan):
        with Session(self.engine) as db:
            row = ScanRow(id=scan.id, project_id=scan.project_id, created_at=scan.created_at, result=scan.result)
            db.add(row)
            db.commit()
            return _scan(row)
