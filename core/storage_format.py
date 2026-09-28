"""Lossless, versioned JSON documents embedded in human-readable Markdown."""
import json
import re


def encode_document(kind, payload):
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
    return f"# Eidolon {kind} Object\n\nVersion: 0.2\n\n```json\n{text}\n```\n"


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
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result
    def invalid_constant(value):
        raise ValueError(f"invalid JSON constant: {value}")
    payload, end = json.JSONDecoder(object_pairs_hook=unique_object,
                                   parse_constant=invalid_constant).raw_decode(body)
    if body[end:].strip() != "```" or not isinstance(payload, dict):
        raise ValueError("invalid JSON document boundary")
    return payload
