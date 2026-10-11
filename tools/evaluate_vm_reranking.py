# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tools/evaluate_vm_reranking.py
# Description : Compare fixed card relevance on an independent corpus copy.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
from pathlib import Path
import json, hashlib, statistics, time, shutil
from core.backend.filesystem import FilesystemBackend
from core.retrieval.contextual import ContextualRecall
from core.retrieval.reranked import RerankedRecall
from services.collaboration.independent_benchmark import CASES
from sentence_transformers import CrossEncoder
import torch

torch.set_num_threads(2)
stage=Path("/home/toytoy/eidolon-validation/rerank-20261012")
stage.mkdir(parents=True,exist_ok=False)
source=Path("/home/toytoy/eidolon-corpus-factual-v2-test")
shutil.copytree(source,stage/"corpus",symlinks=True)
def hashes():
 return {str(p.relative_to(stage/"corpus")):hashlib.sha256(p.read_bytes()).hexdigest()
         for p in (stage/"corpus").rglob("*") if p.is_file() and not p.name.startswith(".")}
before=hashes()
root=stage/"corpus"
backend=FilesystemBackend(root/"memory/persistent",root/"memory/history")
base=ContextualRecall(backend)
encoder=CrossEncoder("cross-encoder/mmarco-mMiniLMv2-L12-H384-v1",
 device="cpu",cache_folder="/home/toytoy/eidolon-hybrid-lab/models",
 max_length=512,local_files_only=True)
def score(q,texts):
 return encoder.predict([(q,t) for t in texts],batch_size=8,show_progress_bar=False).tolist() if texts else []
reranked=RerankedRecall(base,score)
holdout=[
 ("Quel environnement est consacré au développement Core ?","01-vm-services"),
 ("Où réside le moteur qui conserve les souvenirs ?","01-vm-services"),
 ("Le dialogue doit-il s'arrêter si le rappel distant tombe ?","02-vm-communications"),
 ("Par quel canal sécurisé passe la consultation des souvenirs ?","02-vm-communications"),
 ("Quel format physique a la Tesla testée ?","03-gpu-active"),
 ("La correction d'erreurs mémoire était-elle utilisée pendant les essais ?","03-gpu-active"),
 ("Quelle RTX est en réserve avec 12 Go de mémoire ?","04-gpu-available"),
 ("Disponible veut-il dire affectée à une machine virtuelle ?","04-gpu-available"),
 ("La somme des mémoires des futures Tesla représente combien ?","05-gpu-planned"),
 ("Le lien entre les deux GPU garantit-il un espace mémoire unique ?","05-gpu-planned"),
 ("Combien de RAM DDR4 a la configuration déclarée ?","06-hardware-decisions"),
 ("Le changement de carte mère est-il déjà validé comme installation ?","06-hardware-decisions"),
 ("Quelles séries de RTX étaient envisagées au début ?","07-gpu-history"),
 ("Les hypothèses du début décrivent-elles le matériel de maintenant ?","07-gpu-history")]
cases=[dict(c,split="existing") for c in CASES if c["judged"]]
cases += [{"question":q,"expected":["eidolon-factual-v2-"+i],"split":"holdout"} for q,i in holdout]
rows=[]
for case in cases:
 row=dict(case,methods={})
 for name,reader in [("lexical",base),("canonical_cross_encoder",reranked)]:
  start=time.perf_counter()
  b=reader.recall(case["question"],at="2026-10-11T00:00:00Z",max_items=5,max_chars=4000,max_item_chars=800)
  ids=[i.information_id for i in b.items]
  rank=next((n for n,i in enumerate(ids,1) if i in case["expected"]),None)
  row["methods"][name]={"ids":ids,"recall_at_5":int(rank is not None),
    "mrr":1/rank if rank else 0,"ms":(time.perf_counter()-start)*1000}
 rows.append(row)
summary={}
for split in ("existing","holdout"):
 summary[split]={}
 for name in ("lexical","canonical_cross_encoder"):
  rs=[r["methods"][name] for r in rows if r["split"]==split]
  summary[split][name]={"questions":len(rs),"recall_at_5":statistics.mean(r["recall_at_5"] for r in rs),
    "mrr":statistics.mean(r["mrr"] for r in rs),"mean_ms":statistics.mean(r["ms"] for r in rs)}
payload={"summary":summary,"rows":rows,"canonical_copy_unchanged":before==hashes(),
 "limitations":["Reference relevance only; no generated answer or truth score.",
 "Holdout authored from the seven existing cards, not broad independent coverage.",
 "No answer abstention guarantee. Original corpus not modified."]}
(stage/"result.json").write_text(json.dumps(payload,ensure_ascii=False,indent=2))
print(json.dumps({"summary":summary,"canonical_copy_unchanged":payload["canonical_copy_unchanged"]}))
