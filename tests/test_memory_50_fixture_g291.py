import json
from pathlib import Path
from tools.evaluation.run_memory_50 import validate_fixture


def test_50_questions_have_distinct_ids_and_expected_sources():
    p=Path(__file__).parent/'evaluation/memory-50-questions-v1.json'
    rows=validate_fixture(json.loads(p.read_text()))
    assert len(rows)==50
    assert sum(c['expected_id'] is not None for c in rows)==30
    assert sum(c['expected_id'] is None for c in rows)==20
    assert {c['category'] for c in rows}=={'paraphrase','related','unknown'}
