"""Le contrat du port de memoire, applique au stockage de test en memoire (recit TAXO-MINIA-ENQUETE-01, lot A)."""
import pytest

from app.minia.domain.investigation.store import ParcoursMemoryStore

from investigation_scenarios import InMemoryStore
from investigation_store_contract import StoreContract


class TestInMemoryStore(StoreContract):
    @pytest.fixture
    def store(self):
        return InMemoryStore()


def test_the_test_store_offers_every_method_of_the_port():
    port = {name for name in vars(ParcoursMemoryStore) if not name.startswith('_')}
    assert port == {'create', 'load', 'commit', 'mark_status', 'expire'}
    assert port <= set(dir(InMemoryStore))
