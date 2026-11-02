# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tools/evaluation/run_long_corpus.py
# Description : Isolated lexical retrieval benchmark; never reads an answer oracle
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
"""Compare reference/experimental FTS5 projections, not LLM answers or embeddings.

Run with python -m tools.evaluation.run_long_corpus. The work directory must not
exist. Inputs are the synthetic FR100 manifest/documents and question-only JSONL.
Evaluation of returned identities belongs to a separate offline process.
"""
import argparse
from dataclasses import asdict
import hashlib
import json
import math
import os
from pathlib import Path
import resource
import subprocess
import tarfile
import time

from core.backend.errors import MemoryAlreadyExists
from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
from core.indexing.manifest import build_manifest
from core.indexing.memory_index import InMemoryIndex
from core.indexing.fts5_verified_experimental import VerifiedSqliteFts5Index


def lines(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def percentile(values, p):
    return sorted(values)[max(0, math.ceil(len(values) * p) - 1)]


def inputs(corpus, questions):
    entries = lines(corpus / "manifest.jsonl")
    queries = lines(questions)
    if len(entries) != 100 or len(queries) != 1000:
        raise ValueError("FR100 requires 100 documents and 1000 questions")
    documents = []
    for number, entry in enumerate(entries, 1):
        path = corpus / entry["file"]
        if (entry["id"] != f"DOC-{number:03d}" or path.is_symlink()
                or path.resolve().parent != (corpus / "documents").resolve()
                or path.suffix != ".txt" or path.stat().st_size > 1024 * 1024):
            raise ValueError("unexpected document identity/path/size")
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != entry["sha256"]:
            raise ValueError("source hash mismatch")
        documents.append(Memory(entry["id"], content=raw.decode("utf-8")))
    for number, query in enumerate(queries, 1):
        if (set(query) != {"id", "type", "question"} or query["id"] != f"Q-{number:04d}"
                or not isinstance(query["question"], str)):
            raise ValueError("question-only schema required; no answer/evidence fields")
    return documents, queries


def run(corpus, questions, work):
    documents, queries = inputs(corpus, questions)
    work.mkdir(mode=0o700, parents=False, exist_ok=False)
    report = {"schema": "eidolon-fr100-retrieval/1", "results": [],
              "scope": "whole-document lexical retrieval; no LLM, vector model or abstention policy",
              "question_sha256": hashlib.sha256(questions.read_bytes()).hexdigest(),
              "manifest_sha256": hashlib.sha256((corpus / "manifest.jsonl").read_bytes()).hexdigest(),
              "git_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()}
    start = time.perf_counter()
    for size in (10, 50, 100):
        batch = work / str(size)
        batch.mkdir(mode=0o700)
        canon = batch / "persistent"
        backend = FilesystemBackend(canon, batch / "history")
        began = time.perf_counter()
        for memory in documents[:size]:
            backend.store(memory)
        ingestion = time.perf_counter() - began
        manifest = build_manifest(canon)
        if len(manifest.entries) != size:
            raise AssertionError("canonical count")
        for memory in documents[:size]:
            try:
                backend.store(memory)
            except MemoryAlreadyExists:
                pass
            else:
                raise AssertionError("duplicate identity was accepted")
        if build_manifest(canon) != manifest:
            raise AssertionError("duplicate import modified canonical files")
        archive = batch / "canonical.tar"
        with tarfile.open(archive, "x") as tar:
            for path in sorted(canon.glob("*.md")):
                tar.add(path, arcname=path.name, recursive=False)
        restored = batch / "restored"
        restored.mkdir(mode=0o700)
        with tarfile.open(archive) as tar:
            tar.extractall(restored, filter="data")
        if build_manifest(restored) != manifest:
            raise AssertionError("restoration hash mismatch")
        for name in ("reference", "fts5_verified"):
            index = (InMemoryIndex() if name == "reference" else
                     VerifiedSqliteFts5Index(batch / "fts5.sqlite3", alias="eidolon_fr100"))
            began = time.perf_counter()
            index.rebuild(canon)
            rebuild = time.perf_counter() - began
            if index.status().documents != size or index.status().source_digest != manifest.digest:
                raise AssertionError("index count/digest mismatch")
            latencies, checks = [], []
            with (batch / f"{name}-retrieval.jsonl").open("x", encoding="utf-8") as output:
                for query in queries[:size * 10]:
                    began = time.perf_counter()
                    hits = index.query(query["question"], limit=5)
                    elapsed = (time.perf_counter() - began) * 1000
                    latencies.append(elapsed)
                    identities = [hit.information_id for hit in hits]
                    if len(checks) < 10:
                        checks.append((query["question"], identities))
                    output.write(json.dumps({"id": query["id"], "type": query["type"],
                        "hits": [{"id": hit.information_id, "score": hit.score} for hit in hits],
                        "elapsed_ms": elapsed}, ensure_ascii=False) + "\n")
                    output.flush()
            index.rebuild(restored)
            for question, expected in checks:
                if [h.information_id for h in index.query(question, limit=5)] != expected:
                    raise AssertionError("retrieval changed after restoration/rebuild")
            if build_manifest(canon) != manifest:
                raise AssertionError("queries changed canonical files")
            result = {"documents": size, "adapter": name, "queries": len(latencies),
                      "ingestion_s": ingestion, "rebuild_s": rebuild,
                      "query_p50_ms": percentile(latencies, .50),
                      "query_p95_ms": percentile(latencies, .95),
                      "query_total_s": sum(latencies) / 1000,
                      "duplicate_identity_rejections": size, "restore_sha_equal": True,
                      "restore_retrieval_checks": len(checks), "canonical_unchanged": True,
                      "index_status": asdict(index.status())}
            if name != "reference":
                result["index_bytes"] = (batch / "fts5.sqlite3").stat().st_size
            report["results"].append(result)
            (work / "progress.json").write_text(json.dumps(report, indent=2))
            print(json.dumps(result), flush=True)
    report["elapsed_s"] = time.perf_counter() - start
    report["process_peak_rss_kib"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    report["completed"] = True
    (work / "summary.json").write_text(json.dumps(report, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus-root", required=True, type=Path)
    parser.add_argument("--questions", required=True, type=Path)
    parser.add_argument("--work", required=True, type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    run(args.corpus_root.resolve(), args.questions.resolve(), args.work.absolute())
