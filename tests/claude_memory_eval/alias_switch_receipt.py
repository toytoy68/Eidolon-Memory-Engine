# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/claude_memory_eval/alias_switch_receipt.py
# Description : Reçu pur EXPÉRIMENTAL de bascule d'alias Qdrant (Claude, G256-3)
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
"""EXPERIMENTAL, test-only. No Qdrant client, no file, no clock read, no production journal.

A receipt binds one alias switch: previous and new generation, the alias, the new generation's
descriptor and manifest digests, and a unique switch id. The host would write it AFTER reading the alias
back. retirement_facts() derives, from a verified chain only, the (retired_at, audit_reference) pair that
generation_retention.classify() requires. Proposal: Core docs/proposals/2026-10-15-alias-switch-receipt.md."""
from hashlib import sha256
import json
import math
import re

SCHEMA = "eidolon-alias-switch-receipt/1"
_BODY = ("schema", "switch_id", "alias", "previous_generation", "new_generation",
         "new_descriptor_sha256", "manifest_sha256", "switched_at", "observed_before", "observed_after")
_HEX64 = re.compile(r"[0-9a-f]{64}")


class ReceiptRefused(ValueError):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def _digest(body):
    canonical = json.dumps({k: body[k] for k in _BODY}, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=True, allow_nan=False)
    return sha256(canonical.encode("ascii")).hexdigest()


def _check_body(body):
    if type(body) is not dict:
        raise ReceiptRefused("RECEIPT_INVALID")
    keys = set(body) - {"receipt_sha256"}
    if not set(_BODY) <= keys:
        raise ReceiptRefused("RECEIPT_INCOMPLETE")
    if keys != set(_BODY):
        raise ReceiptRefused("RECEIPT_UNEXPECTED_FIELD")
    if body["schema"] != SCHEMA:
        raise ReceiptRefused("RECEIPT_SCHEMA")
    alias = body["alias"]
    if type(alias) is not str or not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", alias):
        raise ReceiptRefused("RECEIPT_INVALID")
    generation = re.compile(re.escape(alias) + r"__[0-9a-f]{32}")
    for key in ("previous_generation", "new_generation", "observed_before", "observed_after"):
        if type(body[key]) is not str or not generation.fullmatch(body[key]):
            raise ReceiptRefused("RECEIPT_INVALID")
    if body["previous_generation"] == body["new_generation"]:
        raise ReceiptRefused("RECEIPT_NOT_A_SWITCH")
    if body["observed_before"] != body["previous_generation"] or body["observed_after"] != body["new_generation"]:
        raise ReceiptRefused("SWITCH_NOT_OBSERVED")
    for key in ("new_descriptor_sha256", "manifest_sha256"):
        if type(body[key]) is not str or not _HEX64.fullmatch(body[key]):
            raise ReceiptRefused("RECEIPT_INVALID")
    if type(body["switch_id"]) is not str or not re.fullmatch(r"[0-9a-f]{32}", body["switch_id"]):
        raise ReceiptRefused("RECEIPT_INVALID")
    try:
        if type(body["switched_at"]) not in (int, float) or not math.isfinite(body["switched_at"]) \
                or body["switched_at"] < 0:
            raise ReceiptRefused("RECEIPT_INVALID")
    except OverflowError:
        # Match epoch_window: unrepresentable integers use the public refusal.
        raise ReceiptRefused("RECEIPT_INVALID") from None


def make_receipt(**fields):
    body = dict(schema=SCHEMA, **fields)
    _check_body(body)
    return dict(body, receipt_sha256=_digest(body))


def verify_receipt(receipt, *, seen_switch_ids=frozenset()):
    """Return the receipt's switch id; refuse incomplete, altered, unobserved or replayed receipts."""
    return _verify(receipt, _seen(seen_switch_ids))


def _verify(receipt, seen_switch_ids):
    _check_body(receipt)
    if "receipt_sha256" not in receipt:
        raise ReceiptRefused("RECEIPT_INCOMPLETE")
    if receipt["receipt_sha256"] != _digest(receipt):
        raise ReceiptRefused("RECEIPT_DIGEST_MISMATCH")
    if receipt["switch_id"] in seen_switch_ids:
        raise ReceiptRefused("RECEIPT_REPLAYED")
    return receipt["switch_id"]


def _anchor(alias, generation):
    if (type(alias) is not str or not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", alias) or type(generation) is not str
            or not re.fullmatch(r"[a-z][a-z0-9_]{0,62}__[0-9a-f]{32}", generation)):
        raise ReceiptRefused("RECEIPT_INVALID")
    if generation[:-34] != alias:
        raise ReceiptRefused("RECEIPT_OTHER_ALIAS")


def _window(epoch_window):
    if epoch_window is None:
        return None
    try:
        if (type(epoch_window) is not tuple or len(epoch_window) != 2
                or any(type(x) not in (int, float) or not math.isfinite(x) for x in epoch_window)
                or not 0 <= epoch_window[0] < epoch_window[1]):
            raise ReceiptRefused("RECEIPT_INVALID")
    except OverflowError:                 # math.isfinite(10**400): an integer too large for a float
        raise ReceiptRefused("RECEIPT_INVALID") from None
    return epoch_window


def _seen(value):
    """G262-9: the host's consumed ids must be a real, re-readable collection of valid ids. A string would
    otherwise become a set of characters and silently disable replay detection."""
    if type(value) not in (set, frozenset, list, tuple):
        raise ReceiptRefused("RECEIPT_INVALID_SEEN")
    if any(type(item) is not str or not re.fullmatch(r"[0-9a-f]{32}", item) for item in value):
        raise ReceiptRefused("RECEIPT_INVALID_SEEN")
    return frozenset(value)


def verify_chain(receipts, *, alias, initial_generation, seen_switch_ids=frozenset(), epoch_window=None):
    """Every switch of one alias, in order: each starts where the previous ended, time never goes back.

    seen_switch_ids: ids already consumed by an earlier verification (the host's own durable set), so a
    receipt cannot be replayed into another chain. epoch_window: the SAME plausibility window the host
    passes to generation_retention.classify; an epoch-0 or millisecond receipt then proves nothing."""
    _anchor(alias, initial_generation)
    window = _window(epoch_window)
    seen, current, last_at = set(_seen(seen_switch_ids)), initial_generation, None
    for receipt in receipts:
        seen.add(_verify(receipt, seen))
        if receipt["alias"] != alias:
            raise ReceiptRefused("RECEIPT_OTHER_ALIAS")
        if window is not None and not window[0] <= receipt["switched_at"] <= window[1]:
            raise ReceiptRefused("RECEIPT_TIME_IMPLAUSIBLE")
        if receipt["previous_generation"] != current:
            raise ReceiptRefused("CHAIN_BROKEN")
        if last_at is not None and receipt["switched_at"] < last_at:
            raise ReceiptRefused("CHAIN_TIME_REGRESSED")
        current, last_at = receipt["new_generation"], receipt["switched_at"]
    return current


def retirement_facts(receipts, *, alias, initial_generation, observed_target, seen_switch_ids=frozenset(),
                     epoch_window=None):
    """{generation: (retired_at, switch_id)} for generations retired and never reactivated since.

    The chain must end on the alias target read now; otherwise nothing is proven (empty result)."""
    receipts = tuple(receipts)
    _anchor(alias, observed_target)
    if verify_chain(receipts, alias=alias, initial_generation=initial_generation,
                    seen_switch_ids=seen_switch_ids, epoch_window=epoch_window) != observed_target:
        return {}
    retired = {}
    for receipt in receipts:
        # A generation retired twice keeps its latest retirement only.
        retired[receipt["previous_generation"]] = (receipt["switched_at"], receipt["switch_id"])
    retired.pop(observed_target, None)  # reactivated: its older retirement no longer counts
    return retired

