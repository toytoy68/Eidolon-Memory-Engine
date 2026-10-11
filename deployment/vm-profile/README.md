# Profil VM Memory

Unité effectivement déployée sur VM Memory. Le corpus actif est le corpus de test factual-v2 (171 informations), pas un déploiement général sur les exports ChatGPT. Le cache du CrossEncoder et son environnement Python doivent exister. Le jeton est conservé hors Git dans le fichier privé EnvironmentFile.

Le service écoute exclusivement sur 127.0.0.1:18765. Core passe par un tunnel SSH authentifié. Les modèles sont chargés hors ligne ; aucun téléchargement au démarrage. Une erreur de modèle ou de mémoire est signalée, sans promotion des sources non vérifiées.
