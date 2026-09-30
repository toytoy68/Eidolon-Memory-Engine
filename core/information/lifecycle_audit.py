"""Read-only retention and applicability counts; never infer deletion rights."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path

from core.backend.errors import InvalidMemory
from core.backend.filesystem import FilesystemBackend
from core.indexing import build_manifest
from core.information.models import EpistemicStatus, Retention
from core.persistence import has_symlink_component


def _aware_timestamp(value: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError("timestamp must be timezone-aware ISO text")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp must include a timezone")
    return parsed


def audit_lifecycle(persistent_root: Path, *, as_of: str) -> dict:
    """Count declared retention and validity on a stopped copy, without mutation."""
    instant = _aware_timestamp(as_of)
    root = Path(persistent_root)
    if has_symlink_component(root):
        raise ValueError("lifecycle source contains a symlinked directory")
    manifest = build_manifest(root)
    retention_counts: Counter[str] = Counter()
    applicability_counts: Counter[str] = Counter()
    joint_counts: Counter[tuple[str, str]] = Counter()
    epistemic_joint_counts: Counter[tuple[str, str]] = Counter()
    content_counts: Counter[str] = Counter()
    allowed_retention = {member.value for member in Retention}
    allowed_epistemic = {member.value for member in EpistemicStatus}
    for entry in manifest.entries:
        path = root / f"{entry.information_id}.md"
        if path.is_symlink():
            raise InvalidMemory("lifecycle source contains a symlinked file")
        raw = path.read_bytes()
        if sha256(raw).hexdigest() != entry.file_sha256:
            raise InvalidMemory("lifecycle source changed during audit")
        memory = FilesystemBackend._deserialize(raw.decode("utf-8"))
        if isinstance(memory.content, str) and memory.content:
            content_counts[sha256(memory.content.encode("utf-8")).hexdigest()] += 1
        retention = memory.metadata.get("retention")
        if retention is None:
            retention_key = "missing"
        elif type(retention) is str and retention in allowed_retention:
            retention_key = retention
        else:
            retention_key = "invalid"
        retention_counts[retention_key] += 1

        bounds = []
        invalid_bound = False
        for key in ("valid_from", "valid_until"):
            value = memory.temporal.get(key)
            if value is None or value == "":
                bounds.append(None)
            elif not isinstance(value, str):
                invalid_bound = True
                bounds.append(None)
            else:
                try:
                    bounds.append(_aware_timestamp(value))
                except ValueError:
                    invalid_bound = True
                    bounds.append(None)
        valid_from, valid_until = bounds
        if invalid_bound or (valid_from and valid_until and valid_from > valid_until):
            applicability = "invalid"
        elif valid_until and valid_until < instant:
            applicability = "ended"
        elif valid_from and valid_from > instant:
            applicability = "not_started"
        elif valid_from or valid_until:
            applicability = "within_known_bounds"
        else:
            applicability = "unknown"
        applicability_counts[applicability] += 1
        joint_counts[(retention_key, applicability)] += 1
        epistemic = memory.metadata.get("epistemic_status")
        if epistemic is None:
            epistemic_key = "missing"
        elif type(epistemic) is str and epistemic in allowed_epistemic:
            epistemic_key = epistemic
        else:
            epistemic_key = "invalid"
        epistemic_joint_counts[(epistemic_key, applicability)] += 1
    return {
        "count": len(manifest.entries), "source_digest": manifest.digest,
        "as_of": instant.isoformat(),
        "retention": dict(sorted(retention_counts.items())),
        "applicability": dict(sorted(applicability_counts.items())),
        "retention_by_applicability": {
            retention: dict(sorted((applicability, count)
                                   for (policy, applicability), count in joint_counts.items()
                                   if policy == retention))
            for retention in sorted(retention_counts)
        },
        "epistemic_by_applicability": {
            status: dict(sorted((applicability, count)
                                for (label, applicability), count in epistemic_joint_counts.items()
                                if label == status))
            for status in sorted({label for label, _ in epistemic_joint_counts})
        },
        "exact_content_duplicates": {
            "groups": sum(count > 1 for count in content_counts.values()),
            "documents_in_groups": sum(count for count in content_counts.values()
                                       if count > 1),
        },
        "policy": "read_only_no_deletion_inferred",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only memory lifecycle audit")
    parser.add_argument("--root", type=Path, required=True,
                        help="Stopped engine copy containing memory/persistent")
    parser.add_argument("--at", required=True, help="Explicit timezone-aware ISO timestamp")
    args = parser.parse_args(argv)
    try:
        report = audit_lifecycle(args.root / "memory/persistent", as_of=args.at)
    except (OSError, UnicodeError, ValueError, InvalidMemory) as exc:
        parser.error(str(exc))
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
