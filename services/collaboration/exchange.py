# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : services/collaboration/exchange.py
# Description : Fixed-path Git exchange. The service owns a dedicated checkout on Linux.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================

"""Fixed-path Git exchange. The service owns a dedicated checkout on Linux."""
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import uuid

BRANCH = "refactor/architecture-v1"
ORIGIN = "https://github.com/toytoy68/Eidolon-Memory-Engine.git"
GPT = "collaboration/GPT-TO-CLAUDE.md"
CLAUDE = "collaboration/CLAUDE-TO-GPT.md"
MAX_MESSAGE_BYTES = 32768


class ExchangeError(RuntimeError):
    """Public error contains no Git output or credentials."""


class Exchange:
    def __init__(self, repo: Path, state: Path, expected_origin: str = ORIGIN):
        self.repo = repo.resolve(strict=True)
        self.state = state.resolve()
        if self.state == self.repo or self.repo in self.state.parents:
            raise ValueError("State directory must be outside the checkout")
        self.state.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.expected_origin = expected_origin
        self.allowed_origins = {expected_origin}
        if expected_origin == ORIGIN:
            self.allowed_origins.add("git@github.com:toytoy68/Eidolon-Memory-Engine.git")

    def git(self, *args: str) -> str:
        env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
        try:
            result = subprocess.run(
                ["git", "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false", *args],
                cwd=self.repo, env=env, capture_output=True, timeout=45, check=True,
            )
        except (subprocess.SubprocessError, OSError) as exc:
            raise ExchangeError("Git operation failed; operator intervention required") from exc
        return result.stdout.decode("utf-8", errors="strict").strip()

    @contextmanager
    def locked(self):
        with (self.state / "exchange.lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise ExchangeError("Exchange busy; retry later") from exc
            try:
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def audit(self, event: str, **fields):
        record = {"time": datetime.now(timezone.utc).isoformat(), "event": event, **fields}
        with (self.state / "audit.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())

    def path(self, relative: str) -> Path:
        target = self.repo / relative
        for part in [target, *target.parents]:
            if part == self.repo:
                break
            if part.is_symlink():
                raise ExchangeError("Exchange paths must not be symbolic links")
        return target

    def check_local(self):
        if self.git("rev-parse", "--show-toplevel") != str(self.repo):
            raise ExchangeError("A standalone checkout is required")
        if self.git("symbolic-ref", "--short", "HEAD") != BRANCH:
            raise ExchangeError("Wrong branch")
        if self.git("remote", "get-url", "origin") not in self.allowed_origins:
            raise ExchangeError("Wrong origin")
        if self.git("remote", "get-url", "--push", "origin") not in self.allowed_origins:
            raise ExchangeError("Wrong push origin")
        if self.git("status", "--porcelain", "--untracked-files=all"):
            raise ExchangeError("Dirty checkout; operator intervention required")
        for name in (GPT, CLAUDE):
            target = self.path(name)
            if not target.is_file() or not self.git("ls-files", "--", name):
                raise ExchangeError("Missing tracked exchange file")
        archive = self.path("collaboration/archive")
        if not archive.is_dir():
            raise ExchangeError("Missing archive directory")

    def sync(self):
        self.check_local()
        self.git("fetch", "origin", BRANCH)
        remote = self.git("rev-parse", "FETCH_HEAD")
        local_only = self.git("rev-list", "--count", f"{remote}..HEAD")
        if local_only != "0":
            raise ExchangeError("Local commits unpublished or divergent; operator intervention required")
        self.git("pull", "--ff-only", "origin", BRANCH)
        self.check_local()
        self.snapshot()
        if self.git("rev-parse", "HEAD") != remote:
            # Remote changed between fetch and pull; never publish against a stale snapshot.
            raise ExchangeError("Remote changed during synchronization; retry")

    def snapshot(self):
        values = {}
        for label, name in (("gpt", GPT), ("claude", CLAUDE)):
            data = self.path(name).read_bytes()
            if len(data) > MAX_MESSAGE_BYTES:
                raise ExchangeError("Active exchange file exceeds limit")
            try:
                data.decode("utf-8", errors="strict")
            except UnicodeError as exc:
                raise ExchangeError("Active exchange file is not UTF-8") from exc
            values[label + "_sha256"] = hashlib.sha256(data).hexdigest()
        return {"branch": BRANCH, "commit": self.git("rev-parse", "HEAD"), **values}

    def read_gpt_message(self):
        with self.locked():
            self.sync()
            result = {**self.snapshot(), "message": self.path(GPT).read_text(encoding="utf-8")}
            self.audit("read", commit=result["commit"])
            return result

    def get_exchange_status(self):
        with self.locked():
            try:
                self.sync()
                return {"ready": True, **self.snapshot()}
            except ExchangeError as exc:
                return {"ready": False, "branch": BRANCH, "reason": str(exc)}

    def write_claude_message(self, message: str):
        try:
            if not isinstance(message, str) or not message.strip() or "\x00" in message:
                raise ValueError
            data = message.encode("utf-8", errors="strict")
            if len(data) > MAX_MESSAGE_BYTES:
                raise ValueError
        except (ValueError, UnicodeError) as exc:
            raise ExchangeError("Message must be nonempty UTF-8, without NUL, at most 32768 bytes") from exc
        with self.locked():
            request_id = uuid.uuid4().hex
            commit = None
            try:
                self.sync()
                digest = hashlib.sha256(data).hexdigest()
                self.audit("write_started", request_id=request_id, sha256=digest, bytes=len(data))
                current = self.path(CLAUDE)
                archive_name = f"collaboration/archive/claude-{request_id}.md"
                archive = self.path(archive_name)
                with archive.open("xb") as stream:
                    stream.write(current.read_bytes())
                    stream.flush()
                    os.fsync(stream.fileno())
                temporary = current.with_suffix(".tmp")
                with temporary.open("xb") as stream:
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, current)
                self.git("add", "--", CLAUDE, archive_name)
                staged = set(self.git("diff", "--cached", "--name-only").splitlines())
                if staged != {CLAUDE, archive_name} and staged != {archive_name}:
                    raise ExchangeError("Unexpected staged paths")
                self.git("-c", "user.name=Eidolon Collaboration", "-c", "user.email=eidolon-collaboration@users.noreply.github.com",
                         "commit", "-m", f"collaboration: Claude reply {request_id}")
                commit = self.git("rev-parse", "HEAD")
                self.audit("committed", request_id=request_id, commit=commit, sha256=digest)
                self.git("push", "origin", f"HEAD:refs/heads/{BRANCH}")
                published = self.git("ls-remote", "origin", f"refs/heads/{BRANCH}").split()[0]
                if published != commit:
                    raise ExchangeError("Publication needs verification by operator")
                self.audit("published", request_id=request_id, commit=commit, sha256=digest)
                return {"published": True, "commit": commit, "sha256": digest, "request_id": request_id}
            except (ExchangeError, OSError, UnicodeError) as exc:
                self.audit("write_failed", request_id=request_id, commit=commit)
                raise ExchangeError("Reply not confirmed published; inspect audit and checkout before retry") from exc
