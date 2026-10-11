# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : services/collaboration/experimental_router.py
# Description : Audited classification and transparent experimental reranking.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
"""No corpus initialization or writes at import. Experimental, not production."""
from datetime import date
import re
import unicodedata

TOPICS = {
 'hardware': ('gpu', 'carte graphique', 'tesla', 'v100', 'rtx', 'materiel', 'processeur', 'serveur'),
 'infrastructure': ('vm', 'machine virtuelle', 'proxmox', 'reseau', 'adresse ip', 'heberge'),
 'memory_engine': ('memoire', 'memory engine', 'souvenir', 'rappel', 'memory bridge'),
 'core': ('eidolon core', 'eidolon-core', 'mission', 'orchestrateur'),
 'personality': ('soul', 'personnalite', 'voix'),
 'agents': ('agent', 'agents', 'outil', 'outils'),
 'robotics': ('robot', 'wall-e', 'robotique'),
}
ADMIN = {'administration', 'audit', 'validation'}


def normalize(text):
    return ''.join(c for c in unicodedata.normalize('NFKD', text.casefold())
                   if not unicodedata.combining(c)).replace("'", '').replace('’', '')


def contains(text, expressions):
    return any(re.search(r'(?<!\w)' + re.escape(e) + r'(?!\w)', text) for e in expressions)


def classify(query, as_of=None):
    q = normalize(query)
    year = (as_of or date.today()).year
    past = ('ancien', 'ancienne', 'anciens', 'anciennes', 'historique', 'auparavant',
            'autrefois', 'initialement', 'initial', 'initiale', 'evolution', 'evolue',
            'etait', 'etaient', 'avions', 'utilisions', 'avant')
    if contains(q, past):
        return 'historical'
    # Ordinals describe history only when linked to a historical predicate.
    years = [int(x) for x in re.findall(r'\b(?:19|20)\d{2}\b', q)]
    if years and max(years) < year:
        return 'historical'
    if re.match(r'^(comment|quelle procedure|quelle commande)\b', q) or contains(q, ('procedure', 'diagnostiquer')):
        return 'documentary'
    if contains(q, ('prevu', 'prevus', 'prevue', 'prevues', 'projet', 'projets', 'sera', 'seront', 'encore a installer')):
        return 'general'
    if years and max(years) > year:
        return 'general'
    if contains(q, ('actuel', 'actuelle', 'actuellement', 'aujourdhui', 'installe',
                    'utilise', 'configuration', 'quelle vm', 'quel gpu', 'equipe')):
        return 'factual'
    return 'general'


def detect_topics(query):
    q = normalize(query)
    return {name for name, expressions in TOPICS.items() if contains(q, expressions)}


def rerank(query, candidates, memories, as_of=None):
    mode = classify(query, as_of)
    topics = detect_topics(query)
    output = []
    for identity, lexical in candidates:
        memory = memories[identity]
        domain = memory.metadata.get('reference', {}).get('domain', 'UNKNOWN')
        score = float(lexical)
        if domain in topics:
            score += .22
        if domain == 'hardware' and 'infrastructure' in topics or domain == 'infrastructure' and 'hardware' in topics:
            score += .08
        if mode == 'factual':
            score += .10 if memory.metadata.get('type') == 'FACTUAL_REFERENCE' else 0
            score -= .25 if domain in ADMIN else .20 if domain == 'history' else 0
        elif mode == 'historical':
            score += .20 if domain == 'history' else -.20 if domain in ADMIN else 0
        elif mode == 'documentary':
            score += .15 if domain in ADMIN else 0
        elif domain in ADMIN:
            score -= .10
        output.append({'id': identity, 'score': score, 'original_score': float(lexical), 'domain': domain})
    return sorted(output, key=lambda x: (-x['score'], x['id']))
