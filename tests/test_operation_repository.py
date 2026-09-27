from core.operations.models import OperationRecord
from core.operations.repository import OperationRepository


def test_operation_repository_defines_required_methods():
    required_methods = {
        "create",
        "get",
        "update",
        "list_incomplete",
    }

    assert required_methods.issubset(OperationRepository.__abstractmethods__)
