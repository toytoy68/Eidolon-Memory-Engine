# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : core/storage_format.py
# Description : Lossless, versioned JSON documents embedded in human-readable Markdown.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================

"""Lossless, versioned JSON documents embedded in human-readable Markdown."""
import json
import math
import re


def encode_document(kind, payload):
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
    return f"# Eidolon {kind} Object\n\nVersion: 0.2\n\n```json\n{text}\n```\n"


def legacy_identity_fields(text, fields):
    """Read required v0.1 fields only from its Identity section.

    The free-text body may contain lines such as ``id: ...``; it must never
    supply identity metadata missing from the header.
    """
    match = re.search(r"(?m)^## Identity[ \t]*\r?\n", text)
    first_heading = re.search(r"(?m)^## [^\r\n]+\r?$", text)
    if match is None or first_heading is None or match.start() != first_heading.start():
        raise ValueError("missing legacy Identity section")
    end = re.search(r"(?m)^---[ \t]*\r?$", text[match.end():])
    if end is None:
        raise ValueError("unclosed legacy Identity section")
    section = text[match.end():match.end() + end.start()]
    if re.search(r"(?m)^## [^\r\n]+\r?$", section):
        raise ValueError("unclosed legacy Identity section")
    result = {}
    for field in fields:
        values = re.findall(rf"(?m)^{re.escape(field)}:[ \t]*([^\r\n]*)\r?$", section)
        if len(values) != 1:
            raise ValueError(f"missing or duplicate legacy {field}")
        result[field] = values[0]
    return result


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError(f"invalid JSON constant: {value}")


def parse_finite_json_float(value):
    """Reject valid JSON numeric syntax that overflows Python's float."""
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError("JSON number exceeds finite float range")
    return parsed


def decode_json_value(text):
    """Parse one JSON value without dropping duplicates or accepting NaN."""
    return json.loads(text, object_pairs_hook=_unique_object,
                      parse_constant=_invalid_constant,
                      parse_float=parse_finite_json_float)


def decode_document(text, kind):
    """Return None for legacy v0.1, reject unknown/corrupt versioned documents."""
    header = re.match(r"\A# Eidolon " + re.escape(kind) + r" Object\r?\n\r?\nVersion: ([^\r\n]+)", text)
    if header is None:
        raise ValueError("missing storage format header")
    version = header.group(1)
    if version == "0.1":
        return None
    if version != "0.2":
        raise ValueError(f"unsupported storage format version: {version}")
    body = text[header.end():].lstrip()
    if not body.startswith("```json\n") and not body.startswith("```json\r\n"):
        raise ValueError("missing JSON payload")
    body = body.split("\n", 1)[1].lstrip()
    payload, end = json.JSONDecoder(object_pairs_hook=_unique_object,
                                   parse_constant=_invalid_constant,
                                   parse_float=parse_finite_json_float).raw_decode(body)
    if body[end:].strip() != "```" or not isinstance(payload, dict):
        raise ValueError("invalid JSON document boundary")
    return payload
