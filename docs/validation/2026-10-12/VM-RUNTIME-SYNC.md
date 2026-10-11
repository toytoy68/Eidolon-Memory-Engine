# Runtime MCP installé — 12 octobre 2026

Base examinée : 4fe0b85aecca0680acb92e555c3ebdb56847cbc0.
Les sources installées sur VM Memory sont reportées dans services/collaboration :
client SSH à cibles fixes, passerelle, workspaces isolés, benchmark et baseline figée.
Aucun fichier de configuration privée, secret ou règle sudo n'est versionné.

vm_execute est explicitement autorisé sur core et memory, avec le scope vm_execute.
La passerelle Memory borne la commande à 6000 caractères, sa durée à 25 secondes,
et chaque flux retourné à 65536 octets. Elle conserve le protocole SSH forcé.
Les workspaces restent limités à Memory et utilisent leur contrôleur isolé.

Validation sur VM Debian : 30 tests ciblés réussis, 4 sous-tests.
Suite avant report : 2011 tests réussis, 4 sous-tests, 50,06 secondes.
Lecture/écriture root via MCP vérifiée sur les deux VM avec suppression des fichiers.
Les archives de sauvegarde existent sur les VM ; aucune restauration effectuée.

Limite : la sortie retournée est bornée mais les fichiers temporaires de capture
peuvent grossir pendant les 25 secondes. Cet accès opérateur est temporaire ;
il ne doit pas être confondu avec les outils autonomes des agents Eidolon.
