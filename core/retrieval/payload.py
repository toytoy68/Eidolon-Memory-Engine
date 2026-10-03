"""Bound complete recall JSON and supplied client framing without hiding metadata."""
from dataclasses import asdict, dataclass, replace
import json


@dataclass(frozen=True)
class RecallPayload:
    text: str
    payload_chars: int
    payload_tokens: int | None
    included_ids: tuple[str, ...]
    omitted_ids: tuple[str, ...]
    format_version: str = 'recall-payload/1'


def validate_limits(*, max_payload_chars, max_payload_tokens=None,
                    payload_token_counter=None, prefix='', suffix=''):
    if type(max_payload_chars) is not int or max_payload_chars < 1:
        raise ValueError('payload character budget must be a positive integer')
    if max_payload_tokens is not None and (type(max_payload_tokens) is not int or max_payload_tokens < 1):
        raise ValueError('payload token budget must be a positive integer')
    if (max_payload_tokens is not None and not callable(payload_token_counter)
            or payload_token_counter is not None and not callable(payload_token_counter)):
        raise ValueError('payload tokens require an explicit callable counter')
    if not isinstance(prefix, str) or not isinstance(suffix, str):
        raise ValueError('payload framing must be text')


def render(bundle, *, max_payload_chars, max_payload_tokens=None,
           payload_token_counter=None, prefix='', suffix=''):
    """Greedily retain complete items in recall order; never trim their evidence.

    Budgets apply to ``text`` exactly. The Python result wrapper is not included.
    This adapter considers the already bounded bundle, not further search pages.
    Token counts are evaluated on each complete rendering, not added per field.
    """
    validate_limits(max_payload_chars=max_payload_chars, max_payload_tokens=max_payload_tokens,
                    payload_token_counter=payload_token_counter, prefix=prefix, suffix=suffix)
    if bundle.used_tokens is not None and any(type(item.token_count) is not int or item.token_count < 0
                                               for item in bundle.items):
        raise ValueError('counted excerpt bundle needs valid item token counts')

    def encode(items):
        omitted = len(bundle.items) - len(items)
        excluded = dict(bundle.excluded_counts)
        if omitted:
            excluded['PAYLOAD_BUDGET'] = excluded.get('PAYLOAD_BUDGET', 0) + omitted
        value = replace(bundle, items=tuple(items), used_chars=sum(len(item.content) for item in items),
                        used_tokens=sum(item.token_count for item in items) if bundle.used_tokens is not None else None,
                        excluded_counts=excluded)
        text = prefix + json.dumps(asdict(value), ensure_ascii=False, sort_keys=True,
                                   separators=(',', ':'), allow_nan=False) + suffix
        tokens = None
        if payload_token_counter is not None:
            tokens = payload_token_counter(text)
            if type(tokens) is not int or tokens < 0:
                raise ValueError('payload token counter must return a nonnegative integer')
        return text, tokens

    def fits(encoded):
        text, tokens = encoded
        return len(text) <= max_payload_chars and (max_payload_tokens is None or tokens <= max_payload_tokens)

    chosen = list(bundle.items)
    encoded = encode(chosen)
    if not fits(encoded):
        chosen = []
        encoded = encode(chosen)
        for item in bundle.items:
            candidate = encode([*chosen, item])
            if fits(candidate):
                chosen.append(item)
                encoded = candidate
        if not fits(encoded):
            raise ValueError('complete recall header and framing exceed the payload budget')
    included = tuple(item.information_id for item in chosen)
    omitted = tuple(item.information_id for item in bundle.items if item.information_id not in included)
    text, tokens = encoded
    return RecallPayload(text, len(text), tokens, included, omitted)
