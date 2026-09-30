import pytest

from core.indexing.memory_index import InMemoryIndex
from tests.contracts.index_port_contract import IndexPortContract


class TestReferenceIndex(IndexPortContract):
    @pytest.fixture
    def index(self):
        return InMemoryIndex()
