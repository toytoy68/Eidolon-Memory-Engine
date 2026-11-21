"""Behavioral tests using real isolated clones and a local bare remote."""
from concurrent.futures import ThreadPoolExecutor
import fcntl
import json
from pathlib import Path
import subprocess

import pytest

from services.collaboration.exchange import BRANCH, CLAUDE, GPT, Exchange, ExchangeError, MAX_MESSAGE_BYTES


def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args], stderr=subprocess.DEVNULL).decode().strip()


@pytest.fixture
def setup(tmp_path):
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
    seed = tmp_path / "seed"
    subprocess.run(["git", "clone", str(remote), str(seed)], check=True, capture_output=True)
    git(seed, "checkout", "-b", BRANCH)
    git(seed, "config", "user.name", "Fixture")
    git(seed, "config", "user.email", "fixture@example.invalid")
    (seed / "collaboration/archive").mkdir(parents=True)
    (seed / GPT).write_text("GPT demande é\n", encoding="utf-8")
    (seed / CLAUDE).write_bytes(b"Previous\r\n")
    (seed / "collaboration/archive/README.md").write_text("archive")
    git(seed, "add", ".")
    git(seed, "commit", "-m", "seed")
    git(seed, "push", "origin", BRANCH)
    repo = tmp_path / "worker"
    subprocess.run(["git", "clone", "--branch", BRANCH, str(remote), str(repo)], check=True, capture_output=True)
    return Exchange(repo, tmp_path / "state", str(remote)), seed, remote


def test_publish_preserves_previous_and_only_fixed_paths(setup):
    exchange, seed, remote = setup
    result = exchange.write_claude_message("Claude réponse 🙂\n")
    assert result["published"] is True
    assert git(remote, "rev-parse", f"refs/heads/{BRANCH}") == result["commit"]
    changed = git(exchange.repo, "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD").splitlines()
    assert set(changed) == {CLAUDE, f"collaboration/archive/claude-{result['request_id']}.md"}
    archive = exchange.repo / changed[1]
    assert archive.read_bytes() == b"Previous\r\n"
    assert (exchange.repo / CLAUDE).read_text() == "Claude réponse 🙂\n"
    assert not git(exchange.repo, "status", "--porcelain")
    events = [json.loads(line) for line in (exchange.state / "audit.jsonl").read_text().splitlines()]
    assert [item["event"] for item in events] == ["write_started", "committed", "published"]
    assert "réponse" not in json.dumps(events)


def test_reads_sync_remote_and_hashes(setup):
    exchange, seed, _ = setup
    (seed / GPT).write_text("Nouvelle demande")
    git(seed, "add", GPT)
    git(seed, "commit", "-m", "update")
    git(seed, "push", "origin", BRANCH)
    assert exchange.read_gpt_message()["message"] == "Nouvelle demande"
    assert exchange.get_exchange_status()["ready"]


@pytest.mark.parametrize("message", ["", "  ", "a\x00b", "\ud800", "é" * 16385, None])
def test_invalid_messages_do_not_modify_git(setup, message):
    exchange, _, _ = setup
    head = git(exchange.repo, "rev-parse", "HEAD")
    with pytest.raises(ExchangeError):
        exchange.write_claude_message(message)
    assert git(exchange.repo, "rev-parse", "HEAD") == head
    assert not git(exchange.repo, "status", "--porcelain")


def test_byte_limit_accepts_exact_boundary(setup):
    exchange, _, _ = setup
    exchange.write_claude_message("é" * (MAX_MESSAGE_BYTES // 2))
    assert (exchange.repo / CLAUDE).stat().st_size == MAX_MESSAGE_BYTES


@pytest.mark.parametrize("fault", ["dirty", "untracked", "wrong_branch", "ahead", "divergent", "origin", "push_origin", "symlink"])
def test_unsafe_git_states_refused(setup, fault):
    exchange, seed, remote = setup
    if fault == "dirty":
        (exchange.repo / GPT).write_text("local change")
    elif fault == "untracked":
        (exchange.repo / "unexpected").write_text("untracked")
    elif fault == "wrong_branch":
        git(exchange.repo, "checkout", "-b", "other")
    elif fault in ("ahead", "divergent"):
        git(exchange.repo, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "--allow-empty", "-m", "ahead")
        if fault == "divergent":
            git(seed, "commit", "--allow-empty", "-m", "remote divergence")
            git(seed, "push", "origin", BRANCH)
    elif fault == "origin":
        git(exchange.repo, "remote", "set-url", "origin", "https://example.invalid/other.git")
    elif fault == "push_origin":
        git(exchange.repo, "remote", "set-url", "--push", "origin", "https://example.invalid/other.git")
    elif fault == "symlink":
        target = exchange.repo / CLAUDE
        target.unlink()
        target.symlink_to(exchange.repo / GPT)
        git(exchange.repo, "add", CLAUDE)
        git(exchange.repo, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-m", "symlink")
        git(exchange.repo, "push", "origin", BRANCH)
    head = git(exchange.repo, "rev-parse", "HEAD")
    status = exchange.get_exchange_status()
    assert not status["ready"]
    with pytest.raises(ExchangeError):
        exchange.write_claude_message("Do not publish")
    assert git(exchange.repo, "rev-parse", "HEAD") == head


def test_lock_across_instances(setup):
    exchange, _, _ = setup
    second = Exchange(exchange.repo, exchange.state, exchange.expected_origin)
    with exchange.locked():
        with ThreadPoolExecutor() as pool:
            with pytest.raises(ExchangeError, match="busy"):
                pool.submit(second.write_claude_message, "concurrent").result()


def test_failed_push_preserves_commit_and_refuses_duplicate(setup):
    exchange, _, remote = setup
    hook = remote / "hooks/pre-receive"
    hook.write_text("#!/bin/sh\nexit 1\n")
    hook.chmod(0o755)
    with pytest.raises(ExchangeError, match="not confirmed"):
        exchange.write_claude_message("Durable reply")
    head = git(exchange.repo, "rev-parse", "HEAD")
    assert (exchange.repo / CLAUDE).read_text() == "Durable reply"
    assert not exchange.get_exchange_status()["ready"]
    with pytest.raises(ExchangeError):
        exchange.write_claude_message("duplicate")
    assert git(exchange.repo, "rev-parse", "HEAD") == head
    hook.unlink()
    git(exchange.repo, "push", "origin", BRANCH)
    assert exchange.get_exchange_status()["ready"]


def test_local_state_cannot_be_in_checkout(setup):
    exchange, _, _ = setup
    with pytest.raises(ValueError):
        Exchange(exchange.repo, exchange.repo / "state")


@pytest.mark.parametrize("contents", [b"\xff", b"x" * (MAX_MESSAGE_BYTES + 1)])
def test_invalid_active_remote_file_blocks_writes(setup, contents):
    exchange, seed, _ = setup
    (seed / GPT).write_bytes(contents)
    git(seed, "add", GPT)
    git(seed, "commit", "-m", "invalid active file")
    git(seed, "push", "origin", BRANCH)
    assert not exchange.get_exchange_status()["ready"]
    with pytest.raises(ExchangeError):
        exchange.write_claude_message("Must not be published")
    assert (exchange.repo / CLAUDE).read_bytes() == b"Previous\r\n"


def test_remote_advance_after_fetch_uses_pinned_snapshot(setup,monkeypatch):
    exchange,seed,_=setup
    original=exchange.git
    advanced=[]
    def racing(*args):
        result=original(*args)
        if args[0]=="fetch" and not advanced:
            advanced.append(True)
            (seed/GPT).write_text("remote advanced after fetch")
            git(seed,"add",GPT);git(seed,"commit","-m","race");git(seed,"push","origin",BRANCH)
        return result
    monkeypatch.setattr(exchange,"git",racing)
    before=git(exchange.repo,"rev-parse","HEAD")
    first=exchange.read_gpt_message()
    assert first["commit"]==before
    assert first["message"]=="GPT demande é\n"
    assert exchange.read_gpt_message()["message"]=="remote advanced after fetch"


def test_classified_git_failure_never_discloses_stderr(setup,monkeypatch):
    exchange,_,_=setup
    original=subprocess.run
    def failed(args,**kwargs):
        if "fetch" in args:
            raise subprocess.CalledProcessError(128,args,stderr=b"Permission denied (publickey). SECRET_SENTINEL token=PRIVATE")
        return original(args,**kwargs)
    monkeypatch.setattr(subprocess,"run",failed)
    status=exchange.get_exchange_status()
    assert status["ready"] is False
    assert status["diagnostic"]==dict(operation="fetch",code="AUTHENTICATION",returncode=128)
    assert "SECRET_SENTINEL" not in json.dumps(status)
    assert "PRIVATE" not in (exchange.state/"audit.jsonl").read_text()


@pytest.mark.parametrize("stderr,code",[
    (b"Host key verification failed. PRIVATE","SSH_HOST_KEY"),
    (b"fatal: detected dubious ownership in repository PRIVATE","UNSAFE_OWNERSHIP"),
    (b"Could not resolve host: PRIVATE","DNS"),
    (b"SSL certificate problem: PRIVATE","TLS_CERTIFICATE"),
    (b"Failed to connect: PRIVATE","NETWORK_CONNECT"),
    (b"Unable to create PRIVATE/index.lock: File exists.","INDEX_LOCKED"),
    (b"Permission denied PRIVATE","FILESYSTEM_PERMISSION"),
    (b"repository not found PRIVATE","REPOSITORY_UNAVAILABLE"),
    (b"rejected non-fast-forward PRIVATE","PUSH_REJECTED"),
    (b"unclassified PRIVATE","COMMAND_FAILED"),
])
def test_git_failure_categories_are_bounded(setup,monkeypatch,stderr,code):
    exchange,_,_=setup
    def failed(*a,**kw):raise subprocess.CalledProcessError(128,["git"],stderr=stderr)
    monkeypatch.setattr(subprocess,"run",failed)
    with pytest.raises(ExchangeError) as error:exchange.git("fetch","origin",BRANCH)
    assert error.value.diagnostic["code"]==code
    assert "PRIVATE" not in str(error.value)
    assert "PRIVATE" not in (exchange.state/"audit.jsonl").read_text()


def test_real_index_lock_is_reported_and_preserved(setup):
    exchange,seed,_=setup
    (seed/GPT).write_text("remote next");git(seed,"add",GPT);git(seed,"commit","-m","next");git(seed,"push","origin",BRANCH)
    head=git(exchange.repo,"rev-parse","HEAD")
    lock=exchange.repo/".git/index.lock";lock.write_text("SYNTHETIC_LOCK")
    status=exchange.get_exchange_status()
    assert status["diagnostic"]["code"]=="INDEX_LOCKED"
    assert status["diagnostic"]["operation"]=="merge"
    assert lock.read_text()=="SYNTHETIC_LOCK"
    assert git(exchange.repo,"rev-parse","HEAD")==head
    lock.unlink()  # Test owns this synthetic lock; application never removes it.
    assert exchange.get_exchange_status()["ready"]


def test_concurrent_remote_push_preserves_both_histories(setup,monkeypatch):
    exchange,seed,remote=setup
    original=exchange.git
    def racing(*args):
        if args[0]=="push":
            (seed/GPT).write_text("concurrent GPT edit");git(seed,"add",GPT)
            git(seed,"commit","-m","concurrent");git(seed,"push","origin",BRANCH)
        return original(*args)
    monkeypatch.setattr(exchange,"git",racing)
    with pytest.raises(ExchangeError,match="not confirmed"):
        exchange.write_claude_message("Preserve this local reply")
    assert (exchange.repo/CLAUDE).read_text()=="Preserve this local reply"
    assert git(remote,"show",f"refs/heads/{BRANCH}:{GPT}")=="concurrent GPT edit"
    assert not exchange.get_exchange_status()["ready"]
    assert "PUSH_REJECTED" in (exchange.state/"audit.jsonl").read_text()
