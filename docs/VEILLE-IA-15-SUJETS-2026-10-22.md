# Veille IA et informatique — 15 technologies, vérification au 22 octobre 2026

Statut : dossier documentaire de Memory Engine. Les dates, affirmations constructeur et limites sont distinguées. **Aucun déploiement, changement de modèle ou modification de l'index canonique n'est autorisé par ces fiches.** La bêta Core/Memory reste prioritaire.

## 01 — NVIDIA Nemotron 3.5 Super VL / Bolt
**Confirmé, 15 octobre.** Super VL est multimodal 120B. Bolt 74B-A9B est un MoE hybride Mamba/Transformer, quantifié en 2 bits pour environ 24 Go; une déclinaison E4B 4 Go est annoncée pour le 23 octobre (future à la date du dossier). Les poids quantifiés restent à stocker même si peu de paramètres sont actifs par token. Les chiffres de débit sur RTX/DGX ne se transposent pas aux V100 sm_70. **Eidolon :** benchmark de qualité des outils, latence, mémoire et compatibilité CUDA 7.0 seulement après bêta. **P2.** Source : https://research.nvidia.com/labs/nemotron/Nemotron-3.5-Bolt-24GB/

## 02 — Liquid AI LFM2.5-24B-A2B
**Confirmé, 13 octobre.** 24B paramètres totaux, environ 2B actifs/token; MoE avec 64 experts, top-4, 40 couches et contexte annoncé de 131072 tokens. Poids ouverts et support déclaré de llama.cpp, vLLM, SGLang, ONNX et MLX. Les 184 tok/s sur M5 Max ne garantissent rien sur Volta. **Eidolon :** candidat agent local rapide; mesurer appels outils, débit et VRAM avant tout choix. **P2.** Source : https://www.liquid.ai/blog/lfm2-5-24b-a2b

## 03 — IBM Granite Switch 4.1
**Confirmé, 14 octobre.** Versions 8B et 30B combinant dialogue, adaptateurs aLoRA de décision et sécurité, et encodeur de transcription. Réutilisation possible du cache KV entre tâches. La transcription du modèle 8B est **en anglais**, donc ne remplace pas notre STT français. Licence Apache 2.0 pour la fiche 8B. **Eidolon :** étudier Decision Engine structuré, fiabilité et coût GPU, sans migration du vocal. **P2.** Source : https://huggingface.co/ibm-granite/granite-switch-4.1-8b

## 04 — Microsoft VibeVoice-ASR-Streaming
**Confirmé, mais publié le 3 septembre, pas dans la quinzaine.** Transcription progressive, séparation des locuteurs et hotwords personnalisables; 10 langues annoncées pour la variante streaming. **Eidolon :** comparer à Whisper sur français, hotwords « Eidolon » et « dis-moi », latence de premier résultat, erreurs et coût CPU/GPU; aucun changement avant bêta. **P1 différée.** Source : https://github.com/microsoft/VibeVoice

## 05 — llama.cpp et multi-GPU CUDA
**Projet confirmé; optimisations précises de la quinzaine non établies.** Releases fréquentes et artefacts CUDA 12/13. Il faut distinguer distribution des couches, parallélisme tensoriel et véritable utilisation des liens NVLink. **Eidolon :** après livraison et qualification des deux V100 32 Go, relever topologie P2P, mémoire, préfill/décodage, stabilité et puissance; conserver Ollama comme référence et rollback. **P2.** Source : https://github.com/ggml-org/llama.cpp/releases

## 06 — vLLM 0.32
**Confirmé, octobre 2026.** Nouveau traitement des décisions structurées et améliorations du moteur de service. Les wheels récents ciblent CUDA 12.9/13 : **support Volta non présumé**. **Eidolon :** étudier architecture des décisions et scheduling, puis compatibilité sm_70 avant installation sur environnement isolé. **P2.** Source : https://github.com/vllm-project/vllm/releases

## 07 — Hermes Agent 0.22.x
**Confirmé, 13–21 octobre.** 0.22 apporte onboarding, modèles locaux, plugins, connecteurs et gestion des versions; 0.22.2 corrige notamment le faux PID après redémarrage et les longues requêtes locales; 0.22.3 est publiée le 21 octobre. **Eidolon :** comparer supervision d'agents, reprise, versions atomiques, gestion de secrets, permissions et isolation. Ne pas remplacer Core. **P1 différée.** Source : https://github.com/NousResearch/hermes-agent/releases

## 08 — Mozilla.ai Otari
**Projet confirmé; annonce initiale antérieure à la quinzaine.** Passerelle LLM compatible OpenAI/Anthropic, clés révocables, routage, budgets, journalisation, failover et modes locaux/hybrides. **Eidolon :** comparer à Core et aux politiques existantes, sans multiplier les couches et secrets par défaut. **P3.** Source : https://github.com/mozilla-ai/otari

## 09 — Microsoft BitNet Embeddings
**Confirmé, publié le 20 juillet, pas en octobre.** Embeddings 0.6B et 270M à poids ternaires avec kernels CPU I2_S. Microsoft annonce un gain de préfill face au FP16, pas une amélioration prouvée du rappel Eidolon. **Eidolon :** test A/B contre Qwen3-embedding:0.6b sur corpus figé, pertinence top-k, latence et consommation. Utiliser collection Qdrant séparée et réindexer; ne pas mélanger les espaces vectoriels. **P2.** Source : https://github.com/microsoft/BitNet

## 10 — MLCommons MLPerf Agents
**Confirmé, 15 octobre; programme de benchmark annoncé, non suite finale prête à installer.** Mesure du succès de missions agentiques entières, latence, énergie, coût, outils, récupération et validation indépendante, plutôt que seuls tok/s. **Eidolon :** définir score de mission réussie, coût par résultat validé, reprises et preuves sourcées. **P1 méthodologie après bêta.** Source : https://mlcommons.org/2026/10/nsf-stride-ai-efficiency-challenge/

## 11 — NVIDIA DCGM Exporter et CVE-2026-47483
**Faille confirmée, publiée en juillet et non le 8 octobre.** Endpoint /debug/pprof vulnérable à saturation et divulgation limitée, score CVSS 8.2; versions affectées à vérifier dans le registre avant action. **Eidolon/DARME :** inventaire réel des versions et surfaces exposées, collecte CVE sourcée, aucune interface de métriques publique non protégée. Ne pas conclure que VM100 est affectée sans vérifier l'installation. **P1 sécurité différée.** Source : https://www.cve.org/CVERecord?id=CVE-2026-47483

## 12 — GitHub AI Scan pour pull requests
**Confirmé, 15 octobre.** Analyse complémentaire de CodeQL, notamment Bash, Dockerfiles, Terraform et PHP. Résultats consultatifs, ne bloquant pas automatiquement les fusions; tarification/crédits et disponibilité selon dépôt. **Eidolon :** comparer aux tests, revues humaines et ShellCheck; vérifier permissions et coûts avant activation. **P2.** Source : https://github.blog/changelog/2026-10-15-ai-scan-for-pull-requests-generally-available/

## 13 — Mojo 1.1 / travaux 1.2
**Confirmé : 1.1 stable le 17 septembre; nightly 1.2 en octobre.** Une page de staging mentionne 1.2 au 22 octobre, mais vérifier sa publication sur le site principal avant d'en faire une sortie stable confirmée. Langage de calcul et écosystème MAX; pas de garantie de kernels performants sur V100. **Eidolon :** uniquement si un goulot mesuré justifie une expérimentation, sans réécrire Core/Memory. **P3.** Source : https://mojolang.org/releases/

## 14 — GreenWAM et GroundingPI
**GreenWAM confirmé le 13 octobre; GroundingPI publié début octobre, hors fenêtre stricte.** GreenWAM apprend prédiction d'états du monde et actions sur diverses morphologies robotiques; GroundingPI 4B relie vision, pointage, OCR et repérage spatial. **Eidolon/Wall-E :** étudier en simulation la perception et la planification, sans remplacer cinématique, limites moteurs, collision et arrêt d'urgence déterministes. **P3.** Sources : https://huggingface.co/papers/2610.18774 et https://github.com/groundingpi/GroundingPI

## 15 — OpenStack 2026.2 Hibiscus et Kata Containers 4.2
**Projets et versions confirmés; calendrier exact à vérifier.** OpenStack évolue pour charges accélérées et infrastructure sécurisée; Kata 4.2 améliore isolation VM de conteneurs et scénarios GPU, avec changements de dépendances. **Eidolon :** étude des principes d'isolation du code d'agents non fiables, comparaison avec Proxmox et bubblewrap. Aucune migration de plateforme justifiée. **P3.** Sources : https://www.openstack.org/software/openstack-hibiscus/ et https://github.com/kata-containers/kata-containers/blob/main/docs/releases/4.2.0.md

## Critères de qualification
Pour chaque piste : vérifier dépôt, version, licence, reproductibilité, compatibilité Debian 13 / CUDA 12.4 / V100 sm_70, RAM/VRAM, coût énergétique, exposition réseau, politiques d'action, tests de refus et rollback. Les annonces fournisseurs ne constituent pas des mesures Eidolon. **Pas de nouveaux chantiers avant la bêta opérationnelle.**
