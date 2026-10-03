"""Validate a reviewed AI detail using the coordinated Information writer."""
import base64
from hashlib import sha256
import hmac
import json

from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
from core.information.writes import FilesystemInformationWrites
from core.persistence import exclusive_write
from core.sources.store import SourceStore
from core.storage_format import decode_json_value


def seal(payload, secret):
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
    return base64.urlsafe_b64encode(raw).decode() + '.' + hmac.new(secret, raw, sha256).hexdigest()


def unseal(token, secret):
    if not isinstance(token, str) or len(token) > 32768:
        raise ValueError('invalid review token')
    try:
        encoded, signature = token.split('.')
        raw = base64.b64decode(encoded, altchars=b'-_', validate=True)
        if not hmac.compare_digest(hmac.new(secret, raw, sha256).hexdigest(), signature):
            raise ValueError('review signature differs')
        value = decode_json_value(raw.decode())
        if not isinstance(value, dict):
            raise ValueError('invalid review payload')
        return value
    except (ValueError, UnicodeError) as exc:
        raise ValueError('review form expired or changed') from exc


def accept_detail(root, review, *, detail, actor):
    if (not isinstance(detail, str) or not 1 <= len(detail.strip()) <= 1000 or '\x00' in detail
            or not isinstance(actor, str) or not actor.strip()):
        raise ValueError('reviewed detail and actor are required')
    if (not isinstance(review, dict) or not isinstance(review.get('quote'), str)
            or not review['quote'].strip() or len(review['quote']) > 2000):
        raise ValueError('a nonempty exact source quote is required')
    store = SourceStore(root)
    with exclusive_write(store.root / 'memory/persistent'):
        from core.operations.readiness import check_readiness
        if not check_readiness(store.root)['ready']:
            raise ValueError('readiness blocks detail validation')
        record, _ = store.read(review['source_id'])
        extraction = store.extraction(review['source_id'])
        paragraph = review['paragraph']
        if (record['sha256'] != review['source_sha256']
                or extraction['text_sha256'] != review['extraction_sha256']
                or extraction['extractor'] != review['extractor'] or type(paragraph) is not int
                or not 1 <= paragraph <= len(extraction['paragraphs'])
                or review['quote'] not in extraction['paragraphs'][paragraph-1]):
            raise ValueError('review source snapshot changed')
        provenance = dict(source_type='MODEL_GENERATED', source=record['source_id'],
            source_sha256=record['sha256'], source_title=record['title'], author=record['author'],
            extraction_sha256=extraction['text_sha256'], extractor=extraction['extractor'],
            paragraph=paragraph, quote=review['quote'], model=review['model'], model_digest=review['model_digest'],
            proposed_detail=review['detail'], validated_by=actor, review_form_issued_at=review['proposed_at'], human_accepted=True)
        key = sha256(json.dumps(dict(review=review, reviewed_detail=detail, actor=actor), sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        memory = Memory('source-detail-'+key, content=detail,
                        metadata={'type': 'INTERPRETATION', 'epistemic_status': 'UNVERIFIED'}, provenance=provenance)
        backend = FilesystemBackend(store.root / 'memory/persistent', store.root / 'memory/history')
        return FilesystemInformationWrites(backend).create(memory, operation_id='source-accept-'+key,
            event_id='source-event-'+key, actor=actor, timestamp=review['proposed_at'])
