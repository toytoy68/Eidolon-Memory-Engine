from dataclasses import dataclass
from time import perf_counter
from pathlib import Path
import re
import unicodedata

from core.backend.filesystem import FilesystemBackend
from core.retrieval.contextual import ContextualRecall
from core.retrieval.ranking import terms

ROOT = Path.home() / "eidolon-corpus-factual-v2-test"

backend = FilesystemBackend(
    ROOT / "memory/persistent",
    ROOT / "memory/history",
)

recall = ContextualRecall(backend)

ADMIN = {"administration", "audit", "validation"}

TOPICS = {
    "hardware": {
        "gpu", "carte graphique", "tesla", "v100",
        "rtx", "materiel", "processeur", "serveur",
    },
    "infrastructure": {
        "vm", "machine virtuelle", "proxmox",
        "reseau", "adresse ip", "heberge",
    },
    "memory_engine": {
        "memoire", "memory engine", "souvenir",
        "rappel", "memory bridge",
    },
    "core": {
        "eidolon core", "eidolon-core",
        "mission", "orchestrateur",
    },
    "personality": {
        "soul", "personnalite", "voix",
    },
    "agents": {
        "agent", "agents", "outil", "outils",
    },
    "robotics": {
        "robot", "wall-e", "robotique",
    },
}

HISTORY = {
    "ancien", "ancienne", "anciens", "anciennes",
    "historique", "auparavant", "autrefois",
    "initialement", "premier", "premiere",
    "evolue", "evolution", "envisage",
}

PROCEDURE = {
    "comment", "procedure", "installer",
    "configurer", "importer", "diagnostiquer",
    "commande", "audit",
}

CURRENT = {
    "actuel", "actuelle", "actuellement",
    "aujourdhui", "installe", "utilise",
    "configuration", "quelle vm", "quel gpu",
}

@dataclass
class RoutedResult:
    mode: str
    topics: set
    items: list
    elapsed_ms: float


def normalize(text):
    text = unicodedata.normalize("NFKD", text.casefold())
    text = "".join(
        char for char in text
        if not unicodedata.combining(char)
    )
    return text.replace("'", "").replace("’", "")


def contains(text, expressions):
    return any(
        re.search(
            r"(?<!\w)" + re.escape(expression) + r"(?!\w)",
            text,
        )
        for expression in expressions
    )


def classify(query):
    q = normalize(query)

    if contains(q, HISTORY):
        return "historical"

    # Années passées explicites.
    if re.search(r"\b(?:19|20)\d{2}\b", q):
        return "historical"

    if contains(q, PROCEDURE):
        return "documentary"

    if contains(q, CURRENT):
        return "factual"

    return "general"


def detect_topics(query):
    q = normalize(query)

    found = set()

    for topic, expressions in TOPICS.items():
        if contains(q, expressions):
            found.add(topic)

    return found


def domain_of(memory):
    return (
        memory.metadata
        .get("reference", {})
        .get("domain", "UNKNOWN")
    )


def score_item(memory, lexical_score, mode, topics):
    score = float(lexical_score or 0)
    domain = domain_of(memory)
    kind = memory.metadata.get("type")

    # Correspondance thématique.
    if topics:
        if domain in topics:
            score += 0.22

        if domain == "hardware" and "infrastructure" in topics:
            score += 0.08

        if domain == "infrastructure" and "hardware" in topics:
            score += 0.08

    # Nature de la connaissance.
    if mode == "factual":
        if kind == "FACTUAL_REFERENCE":
            score += 0.10

        if domain in ADMIN:
            score -= 0.25

        if domain == "history":
            score -= 0.20

    elif mode == "historical":
        if domain == "history":
            score += 0.20

        if domain in ADMIN:
            score -= 0.20

    elif mode == "documentary":
        if domain in ADMIN:
            score += 0.15

    else:
        if domain in ADMIN:
            score -= 0.10

    return score


def search(query, max_items=5):
    start = perf_counter()

    mode = classify(query)
    topics = detect_topics(query)

    result = recall.recall(
        query,
        max_items=171,
        max_chars=150000,
        max_item_chars=800,
    )

    ranked = []

    for item in result.items:
        memory = backend.get(item.information_id)

        if memory is None:
            continue

        score = score_item(
            memory,
            item.score,
            mode,
            topics,
        )

        ranked.append((score, item))

    ranked.sort(
        key=lambda pair: (
            -pair[0],
            pair[1].information_id,
        )
    )

    return RoutedResult(
        mode=mode,
        topics=topics,
        items=[item for _, item in ranked[:max_items]],
        elapsed_ms=(perf_counter() - start) * 1000,
    )
