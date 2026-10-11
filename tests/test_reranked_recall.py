# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/test_reranked_recall.py
# Description : Canonical safety and output bounds through optional reranking.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
import tempfile
import unittest
from pathlib import Path
from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
from core.retrieval.contextual import ContextualRecall
from core.retrieval.reranked import RerankedRecall

class RerankTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.backend = FilesystemBackend(root/"memory/persistent", root/"memory/history")
        for identity, status, temporal in (
            ("safe", "UNVERIFIED", {}),
            ("refuted", "REFUTED", {}),
            ("expired", "CONFIRMED", {"valid_until":"2020-01-01T00:00:00Z"}),
            ("future", "CONFIRMED", {"valid_from":"2030-01-01T00:00:00Z"})):
            self.backend.store(Memory(identity, content="Eidolon mémoire "+identity,
                metadata={"epistemic_status":status}, temporal=temporal,
                provenance={"source":identity+".md"}))
        self.base = ContextualRecall(self.backend)
    def test_policy_and_provenance_survive(self):
        seen = []
        def score(query, texts):
            seen.extend(texts)
            return [10.0]*len(texts)
        result = RerankedRecall(self.base, score).recall(
            "Eidolon mémoire", at="2026-10-12T00:00:00Z")
        self.assertEqual([x.information_id for x in result.items],["safe"])
        self.assertEqual(len(seen),1)
        item=result.items[0]
        self.assertEqual(item.epistemic_status,"UNVERIFIED")
        self.assertTrue(item.needs_review)
        self.assertEqual(item.provenance,{"source":"safe.md"})
    def test_budgets_remain_strict(self):
        result=RerankedRecall(self.base,lambda q,t:[0.0]*len(t)).recall(
            "Eidolon", at="2026-10-12T00:00:00Z",max_chars=4,max_item_chars=3)
        self.assertEqual(result.used_chars,3)
        self.assertEqual(len(result.items[0].content),3)
        self.assertTrue(result.items[0].truncated)
    def test_invalid_scores_refused(self):
        for scorer in (lambda q,t:[],lambda q,t:[float("nan")]*len(t),
                       lambda q,t:[True]*len(t)):
            with self.subTest(scorer=scorer),self.assertRaises(ValueError):
                RerankedRecall(self.base,scorer).recall(
                    "Eidolon",at="2026-10-12T00:00:00Z")
