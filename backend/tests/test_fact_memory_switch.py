"""Taxo on the versioned memory (TAXO-01E): a real analysis is written there and read back exactly.

The analysis runs through the application, with every delivered evaluator, on a small repository.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.bootstrap.database import Base
from app.main import create_app
from app.scans.domain.occurrence import same
from app.scans.infrastructure.sqlalchemy.fact_memory import (FactIdentityRow, FactOccurrenceRow,
                                                             ProducerExecutionRow, SqlAlchemyFactMemory)
from app.scans.infrastructure.sqlalchemy.fact_store import AnalysisFactRow

CONTROLLER = '''package com.example;
import org.springframework.web.bind.annotation.*;
@RestController
@RequestMapping("/api")
class OrdersController {
    @GetMapping("/orders") String list() { return ""; }
    @PostMapping("/orders") String create() { return ""; }
}
'''


@pytest.fixture(name='taxo')
def taxo_fixture(make_repo, tmp_path, monkeypatch):
    repo = make_repo({'build.gradle': "plugins { id 'org.springframework.boot' version '3.3.0' }\n",
                      'src/main/java/com/example/OrdersController.java': CONTROLLER,
                      'package.json': '{"dependencies": {"react": "19"}}'}, 'switch')
    submitted = {}
    add = SqlAlchemyFactMemory.add

    def recording(self, scan_id, evaluator_id, facts):
        facts = list(facts)
        submitted.setdefault(scan_id, {})[evaluator_id] = facts
        return add(self, scan_id, evaluator_id, facts)

    monkeypatch.setattr(SqlAlchemyFactMemory, 'add', recording)
    app = create_app(f'sqlite:///{tmp_path / "switch.db"}', [repo])
    Base.metadata.create_all(app.state.engine)
    with TestClient(app) as client:
        project = client.post('/api/projects', json={'name': 'Switch', 'path': str(repo)}).json()
        yield client, f'/api/projects/{project["id"]}', app.state.engine, submitted


def count(engine, row, **where):
    with Session(engine) as db:
        return db.scalar(select(func.count()).select_from(row).filter_by(**where))


def test_an_analysis_is_written_to_the_versioned_memory_and_read_back_exactly(taxo):
    client, base, engine, submitted = taxo
    scan = client.post(f'{base}/scans').json()
    memory = SqlAlchemyFactMemory(engine)
    assert set(submitted[scan['id']]) == {item['evaluator_id'] for item in scan['evaluations']}
    for evaluator, facts in submitted[scan['id']].items():
        assert facts, evaluator
        assert same(memory.query(scan['id'], evaluator_id=evaluator), facts)
    total = sum(len(facts) for facts in submitted[scan['id']].values())
    assert count(engine, FactOccurrenceRow, scan_id=scan['id']) == total
    assert count(engine, AnalysisFactRow) == 0, 'analysis_facts stays as a fallback and is no longer fed'
    listed = client.get(f'{base}/scans/{scan["id"]}/facts').json()
    assert len(listed) == total


def test_executions_are_recorded_as_the_summary_names_them(taxo):
    client, base, engine, _ = taxo
    scan = client.post(f'{base}/scans').json()
    with Session(engine) as db:
        recorded = {(row.execution_id, row.producer_id, row.producer_version) for row in db.scalars(
            select(ProducerExecutionRow).where(ProducerExecutionRow.scan_id == scan['id']))}
    assert recorded == {(item['execution_id'], item['evaluator_id'], item['producer_version'])
                        for item in scan['evaluations']}


def test_a_second_analysis_of_the_same_commit_shares_its_identities(taxo):
    client, base, engine, submitted = taxo
    first = client.post(f'{base}/scans').json()
    identities = count(engine, FactIdentityRow)
    second = client.post(f'{base}/scans').json()
    assert count(engine, FactIdentityRow) == identities
    assert count(engine, FactOccurrenceRow, scan_id=second['id']) == count(engine, FactOccurrenceRow,
                                                                           scan_id=first['id'])
    memory = SqlAlchemyFactMemory(engine)
    for evaluator, facts in submitted[second['id']].items():
        assert same(memory.query(second['id'], evaluator_id=evaluator), facts)


def test_a_complete_analysis_says_so(taxo):
    client, base, _, _ = taxo
    assert client.post(f'{base}/scans').json()['memory'] == 'COMPLETE'


def test_an_interrupted_consolidation_is_never_offered_as_an_analysis(taxo, monkeypatch):
    from sqlalchemy.exc import OperationalError
    from app.scans.infrastructure.sqlalchemy.scan_repository import ScanRow
    client, base, engine, submitted = taxo
    kept = client.post(f'{base}/scans').json()
    add = SqlAlchemyFactMemory.add

    def locked(self, scan_id, evaluator_id, facts):
        if evaluator_id != 'taxo.inventory':
            raise OperationalError('INSERT', {}, Exception('database is locked'))
        return add(self, scan_id, evaluator_id, facts)

    monkeypatch.setattr(SqlAlchemyFactMemory, 'add', locked)
    with pytest.raises(OperationalError):
        client.post(f'{base}/scans')
    [interrupted] = [scan_id for scan_id in submitted if scan_id != kept['id']]
    assert [scan['id'] for scan in client.get(f'{base}/scans').json()] == [kept['id']]
    assert client.get(f'{base}/scans/{interrupted}/facts').status_code == 404
    with Session(engine) as db:
        assert db.get(ScanRow, interrupted).result['memory'] == 'INCOMPLETE'
