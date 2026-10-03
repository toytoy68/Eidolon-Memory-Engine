"""Select a bounded verbatim message passage; never join conversation branches."""
import json
import re
from core.retrieval.ranking import terms


def select_passage(content, query):
    try:
        archive=json.loads(content)
        if not isinstance(archive,dict) or not isinstance(archive.get('messages'),list):
            return None
        wanted=set(terms(query));best=None
        for index,message in enumerate(archive['messages']):
            if not isinstance(message,dict) or message.get('role') not in {'user','assistant'}:
                continue
            text=message.get('content')
            if not isinstance(text,str):
                continue
            tokens=[(terms(m.group()),m.start()) for m in re.finditer(r'\w+',text)]
            matched=[(word[0],offset) for word,offset in tokens if word and word[0] in wanted]
            if not matched:
                continue
            score=len({word for word,_ in matched})
            # Stable tie-break: original archive order, without implied chronological branch merging.
            if best is None or score>best[0]:
                start=matched[0][1]
                reference=dict(conversation_id=archive.get('conversation_id'),
                    node_id=message.get('node_id'),message_id=message.get('message_id'),
                    parent=message.get('parent'),role=message['role'],created_at=message.get('created_at'),
                    start=start,end=len(text),policy='chatgpt-message-passage-v1')
                best=(score,text[start:],reference)
        return (best[1],best[2]) if best else None
    except (ValueError,TypeError):
        return None
