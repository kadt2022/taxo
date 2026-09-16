from sqlalchemy import Column, String, select
from sqlalchemy.orm import Session
from app.platform.database.base import Base
from app.projects.domain.project import Project

class ProjectRow(Base):
    __tablename__ = 'projects'
    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    path = Column(String, nullable=False, unique=True)


def _project(row):
    return Project(row.id, row.name, row.path) if row is not None else None

class SqlAlchemyProjectRepository:
    def __init__(self, engine):
        self.engine = engine

    def list(self):
        with Session(self.engine) as db:
            return [_project(row) for row in db.scalars(select(ProjectRow).order_by(ProjectRow.name))]

    def get(self, project_id):
        with Session(self.engine) as db:
            return _project(db.get(ProjectRow, project_id))

    def find_path(self, path):
        with Session(self.engine) as db:
            return _project(db.scalar(select(ProjectRow).where(ProjectRow.path == path)))

    def add(self, project):
        with Session(self.engine) as db:
            row = ProjectRow(id=project.id, name=project.name, path=project.path)
            db.add(row)
            db.commit()
            return _project(row)
