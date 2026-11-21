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


class GitFailure(ExchangeError):
    """Only fixed labels and an integer status leave the subprocess boundary."""
    def __init__(self, operation, code, returncode=None):
        self.diagnostic = dict(operation=operation, code=code, returncode=returncode)
        super().__init__(f"Git failed [{operation}/{code}]; operator intervention required")


def _git_failure(args, exc):
    operations = {"rev-parse", "symbolic-ref", "remote", "status", "ls-files", "fetch",
                  "rev-list", "merge", "diff", "add", "commit", "push", "ls-remote"}
    operation = next((arg for arg in args if arg in operations), "other")
    returncode = exc.returncode if isinstance(exc, subprocess.CalledProcessError) else None
    if isinstance(exc, subprocess.TimeoutExpired):
        code = "TIMEOUT"
    elif isinstance(exc, FileNotFoundError):
        code = "EXECUTABLE_OR_DIRECTORY_MISSING"
    elif isinstance(exc, PermissionError):
        code = "FILESYSTEM_PERMISSION"
    elif isinstance(exc, UnicodeError):
        code = "OUTPUT_ENCODING"
    else:
        raw = getattr(exc, "stderr", b"") or b""
        detail = (raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw).lower()
        categories = [
            ("SSH_HOST_KEY", ("host key verification failed", "remote host identification has changed")),
            ("AUTHENTICATION", ("permission denied (publickey", "authentication failed", "could not read username", "terminal prompts disabled")),
            ("UNSAFE_OWNERSHIP", ("dubious ownership", "unsafe repository")),
            ("DNS", ("could not resolve host", "could not resolve hostname")),
            ("TLS_CERTIFICATE", ("ssl certificate problem", "certificate verification failed")),
            ("NETWORK_CONNECT", ("connection refused", "connection timed out", "failed to connect", "network is unreachable")),
            ("FILESYSTEM_PERMISSION", ("permission denied", "read-only file system")),
            ("REPOSITORY_UNAVAILABLE", ("repository not found", "does not appear to be a git repository", "not a git repository")),
            ("PUSH_REJECTED", ("non-fast-forward", "pre-receive hook declined", "fetch first")),
        ]
        code = next((name for name, patterns in categories if any(p in detail for p in patterns)), "COMMAND_FAILED")
        if "index.lock" in detail and "file exists" in detail:
            code = "INDEX_LOCKED"
    return GitFailure(operation, code, returncode)


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
        env = dict(os.environ, GIT_TERMINAL_PROMPT="0", LC_ALL="C")
        try:
            result = subprocess.run(
                ["git", "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false", *args],
                cwd=self.repo, env=env, capture_output=True, timeout=45, check=True,
            )
            return result.stdout.decode("utf-8", errors="strict").strip()
        except (subprocess.SubprocessError, OSError, UnicodeError) as exc:
            failure = _git_failure(args, exc)
            try:
                self.audit("git_failed", **failure.diagnostic)
            except OSError:
                pass  # An unavailable audit must not replace the safe Git diagnostic.
            raise failure from exc

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
        self.git("merge", "--ff-only", "--no-edit", remote)
        self.check_local()
        self.snapshot()
        if self.git("rev-parse", "HEAD") != remote:
            # Only the fetched commit is integrated; a concurrent push is seen next time.
            raise ExchangeError("Local checkout changed during synchronization; inspect checkout")

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
                result = {"ready": False, "branch": BRANCH, "reason": str(exc)}
                if isinstance(exc, GitFailure):
                    result["diagnostic"] = exc.diagnostic
                return result

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
