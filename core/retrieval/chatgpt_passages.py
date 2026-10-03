"""Select a bounded verbatim message passage; never join conversation branches."""
from collections import Counter
import json
import re
from core.retrieval.ranking import terms


def select_passage(content, query, max_chars):
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
            matched=[]
            for match in re.finditer(r'\w+',text):
                word=terms(match.group())
                if word and word[0] in wanted:
                    matched.append((word[0],match.start(),match.end()))
            counts=Counter();right=0
            for left,(_,start,_) in enumerate(matched):
                while right<len(matched) and matched[right][2]<=start+max_chars:
                    counts[matched[right][0]]+=1
                    right+=1
                if right>left:
                    # Prefer coverage inside the actual window, then a compact span.
                    score=(len(counts),-(matched[right-1][2]-start))
                    if best is None or score>best[0]:
                        reference=dict(conversation_id=archive.get('conversation_id'),
                            node_id=message.get('node_id'),message_id=message.get('message_id'),
                            parent=message.get('parent'),role=message['role'],created_at=message.get('created_at'),
                            start=start,end=len(text),policy='chatgpt-message-passage-v2')
                        best=(score,text[start:],reference)
                if right>left:
                    word=matched[left][0]
                    counts[word]-=1
                    if not counts[word]:
                        del counts[word]
                else:
                    right=left+1
        return (best[1],best[2]) if best else None
    except (ValueError,TypeError):
        return None
