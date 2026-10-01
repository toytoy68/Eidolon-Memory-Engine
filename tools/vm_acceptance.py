"""Read-only VM acceptance against a stopped copy; all output stays in --workdir."""

from __future__ import annotations

import sys
sys.dont_write_bytecode = True

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
from time import monotonic

from core.information.deletion_audit import audit_deletions
from core.information.write_audit import audit_information_writes
from core.information.lifecycle_audit import audit_lifecycle
from core.information.relation_audit import audit_relations
from core.migration.inventory import inventory
from core.operations.readiness import check_readiness
from core.persistence import has_symlink_component
from tools.writer_inventory import discover_writers


def hashes(root: Path) -> dict[str, str]:
    """Hash every file and record symlink targets without following them."""
    result = {}
    for base, directories, files in os.walk(root, followlinks=False):
        folder = Path(base)
        for name in list(directories):
            link = folder / name
            if link.is_symlink():
                result[link.relative_to(root).as_posix()] = "link:" + os.readlink(link)
                directories.remove(name)
        for name in files:
            path = folder / name
            key = path.relative_to(root).as_posix()
            result[key] = ("link:" + os.readlink(path) if path.is_symlink()
                           else sha256(path.read_bytes()).hexdigest())
    return result


def active_writers(root: Path) -> list[dict]:
    """Find open writable descriptors; idle services cannot be detected this way."""
    found = []
    proc = Path("/proc")
    if not proc.is_dir():
        return found
    for process in proc.iterdir():
        if not process.name.isdigit():
            continue
        for descriptor in (process / "fd").glob("*"):
            try:
                target = Path(os.readlink(descriptor))
                if root not in (target, *target.parents):
                    continue
                flags = int((process / "fdinfo" / descriptor.name).read_text().split("flags:\t", 1)[1].splitlines()[0], 8)
                if flags & os.O_ACCMODE:
                    found.append({"pid": int(process.name), "path": str(target)})
            except (OSError, ValueError, IndexError):
                continue
    return found


def code_version() -> dict[str, str]:
    """Identify the code running acceptance, independent of the data copy."""
    checkout = Path(__file__).resolve().parents[1]
    try:
        process = subprocess.Popen(
            ["git", "rev-parse", "HEAD", "--abbrev-ref", "HEAD"], cwd=checkout,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
        )
        try:
            output, _ = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate()
            return {"engine_commit": "unknown", "engine_branch": "unknown"}
        if process.returncode == 0:
            commit, branch, *_ = output.splitlines()
            return {"engine_commit": commit, "engine_branch": branch}
    except (OSError, ValueError):
        pass
    return {"engine_commit": "unknown", "engine_branch": "unknown"}


def run(source: Path, workdir: Path, *, at: str) -> dict:
    source, workdir = Path(source).absolute(), Path(workdir).absolute()
    if (not source.is_dir() or has_symlink_component(source)
            or has_symlink_component(workdir)):
        raise ValueError("source and workdir must be real directories without symlink ancestors")
    if source in workdir.parents or workdir in source.parents or source == workdir:
        raise ValueError("source and workdir must be separate non-overlapping trees")
    if workdir.exists() and any(workdir.iterdir()):
        raise ValueError("workdir must be empty")
    workdir.mkdir(parents=True, exist_ok=True)
    report = {"source": str(source), "workdir": str(workdir),
              "versions": {"python": platform.python_version(),
                           "pytest": importlib.metadata.version("pytest"),
                           "platform": f"{platform.system()} {platform.release()}",
                           **code_version()},
              "steps": []}

    def step(name, action, failures=None):
        start = monotonic()
        try:
            details = action()
            found = failures(details) if failures is not None else []
            entry = {"name": name, "status": "KO" if found else "OK",
                     "duration_seconds": round(monotonic() - start, 3),
                     "details": details}
            if found:
                entry["error"] = ", ".join(found)
        except Exception as exc:
            entry = {"name": name, "status": "KO", "duration_seconds": round(monotonic() - start, 3),
                     "error": f"{type(exc).__name__}: {exc}"}
        report["steps"].append(entry)

    def writers():
        found = active_writers(source)
        return {"open_writable_descriptors": found,
                "system_writers": discover_writers(),
                "limitation": "known command markers are heuristic; inspect services and jobs manually"}

    def formats():
        return inventory(source)

    step("writers", writers, lambda result: (
        [f"{len(result['open_writable_descriptors'])} writable descriptors on source"]
        if result["open_writable_descriptors"] else []
    ) + (
        [f"{len(result['system_writers']['running'])} possible running writers"]
        if result["system_writers"]["running"] else []
    ))
    step("formats", formats, lambda result: [
        f"{len(result['needs_review'])} formats or paths need review"
    ] if result["needs_review"] else [])

    def backup_restore():
        original = hashes(source)
        shutil.copytree(source, workdir / "backup", symlinks=True)
        shutil.copytree(workdir / "backup", workdir / "restored", symlinks=True)
        if hashes(workdir / "backup") != original or hashes(workdir / "restored") != original:
            raise ValueError("backup or restored file hashes differ from source")
        if hashes(source) != original:
            raise ValueError("source changed during backup")
        return {"files_verified": len(original), "source_sha256": sha256(
            json.dumps(original, sort_keys=True).encode()).hexdigest()}

    step("backup_restore", backup_restore)

    def concurrency():
        sandbox = workdir / "pytest"
        sandbox.mkdir()
        temporary = workdir / "tmp"
        temporary.mkdir()
        isolated = workdir / "test-engine"
        isolated.mkdir()
        env = dict(os.environ, TMPDIR=str(temporary), TMP=str(temporary), TEMP=str(temporary),
                   HOME=str(workdir), MEMORY_ENGINE_ROOT=str(isolated), PYTHONDONTWRITEBYTECODE="1",
                   PYTEST_DISABLE_PLUGIN_AUTOLOAD="1")
        command = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                   "--basetemp", str(sandbox), "-k",
                   "concurrent_processes_allow_exactly_one_writer or concurrent_retries_commit_exactly_once",
                   "tests/test_audit_regressions.py", "tests/test_thread_recovery.py"]
        result = subprocess.run(command, cwd=Path(__file__).resolve().parents[1],
                                env=env, capture_output=True, text=True, timeout=180)
        (workdir / "concurrency.log").write_text(result.stdout + result.stderr, encoding="utf-8")
        if result.returncode or "5 passed" not in result.stdout:
            raise RuntimeError("five concurrency tests did not pass; see concurrency.log")
        return {"tests_passed": 5, "log": "concurrency.log"}

    step("concurrency", concurrency)

    restored = workdir / "restored"
    persistent = restored / "memory/persistent"
    step("audit_relations",
         lambda: audit_relations(persistent, history_root=restored / "memory/history"),
         lambda result: [f"{name}: {result['relations'].get(name, 0)}"
                         for name in ("invalid", "ambiguous") if result["relations"].get(name, 0)])
    step("audit_lifecycle", lambda: audit_lifecycle(persistent, as_of=at),
         lambda result: [f"{name}: {count}" for name, count in (
             ("invalid retention", result["retention"].get("invalid", 0)),
             ("invalid applicability", result["applicability"].get("invalid", 0)),
             ("invalid epistemic status", sum(result["epistemic_by_applicability"].get("invalid", {}).values())),
         ) if count])
    step("audit_deletions", lambda: audit_deletions(restored),
         lambda result: [f"{len(result['issues'])} deletion issues"] if result["issues"] else [])
    step("audit_information_writes", lambda: audit_information_writes(restored),
         lambda result: [f"{len(result['issues'])} Information journal issues"] if result["issues"] else [])
    step("startup_readiness", lambda: check_readiness(restored),
         lambda result: [f"{len(result['issues'])} unresolved startup issues"] if not result["ready"] else [])
    if report["steps"][2]["status"] == "OK":
        verified = report["steps"][2]["details"]["source_sha256"]
        current = sha256(json.dumps(hashes(source), sort_keys=True).encode()).hexdigest()
        if current != verified:
            report["steps"].append({"name": "source_unchanged", "status": "KO",
                                    "duration_seconds": 0.0, "error": "source changed during acceptance"})
    report["status"] = "OK" if all(item["status"] == "OK" for item in report["steps"]) else "KO"
    (workdir / "vm-acceptance-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="Stopped copy of the engine root")
    parser.add_argument("--workdir", type=Path, required=True, help="Empty and separate output directory")
    parser.add_argument("--at", default=datetime.now(timezone.utc).isoformat(),
                        help="Timezone-aware instant for lifecycle audit")
    args = parser.parse_args(argv)
    try:
        report = run(args.source, args.workdir, at=args.at)
    except ValueError as exc:
        parser.error(str(exc))
    for item in report["steps"]:
        print(f"{item['status']:2} {item['name']:18} {item['duration_seconds']:>7.3f} s"
              + (f" — {item['error']}" if "error" in item else ""))
    print(f"{report['status']} — rapport : {args.workdir.absolute() / 'vm-acceptance-report.json'}")
    return int(report["status"] != "OK")


if __name__ == "__main__":
    raise SystemExit(main())
