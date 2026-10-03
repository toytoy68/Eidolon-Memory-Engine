# Édition explicite des notes humaines — T-044

Les notes d’un dossier projet sont le texte avant et après l’unique zone
MEMORY-ENGINE GENERATED. Elles ne sont pas des Informations canoniques et
ne sont pas ingérées implicitement. `ProjectDossiers.read_notes(thread_id)`
renvoie ces deux sections telles quelles, le SHA256 du document complet,
son chemin et canonical_ingestion=false. Cette lecture ne crée aucun répertoire
ni verrou et n’affirme pas la fraîcheur du résumé.

`replace_notes(thread_id, before=..., after=..., expected_document_sha256=...)`
remplace uniquement les sections humaines d’un dossier existant. Le document
entier doit correspondre à l’empreinte lue, sous verrous Persistent, Thread s’il
existe, puis dossier. Readiness bloque une écriture sur moteur non résolu.
Une zone générée ambiguë/absente, un digest invalide ou des marqueurs de zone
introduits dans les notes sont refusés. Le texte fourni doit être UTF-8 ; les
CRLF et Unicode sont préservés sur cette VM Linux.

```sh
python -m core.dossiers.cli --root RACINE notes project
python -m core.dossiers.cli --root RACINE edit-notes project \
  --notes notes.json --expected-document-sha256 SHA256_LU
```

notes.json contient exactement `{"before":"Notes avant\n","after":"\nNotes après"}`.
Les autres clés sont refusées. La publication utilise le remplacement atomique
et durable existant. Un contenu identique sous l’empreinte actuelle retourne
UNCHANGED ; une édition retourne UPDATED avec la nouvelle empreinte. Ni
Information, Thread, Event, lien ni journal métier n’est créé/modifié.

Deux clients partant du même snapshot ne peuvent pas écraser leurs changements :
un seul publie, l’autre doit relire et résoudre le conflit explicitement. Une
reconstruction du résumé invalide aussi l’empreinte entière. Une édition de notes
ne reconstruit pas une vue STALE ; elle conserve la zone générée octet pour octet,
et une reconstruction explicite ultérieure conserve les nouvelles notes.
Les notes d’une vue orpheline restent éditables sans recréer le Thread supprimé.

Il n’existe pas de journal/versionnement de ces éditions humaines ni de merge
texte automatique. Après perte de réponse, le client relit les notes et leur
empreinte : une écriture publiée reste complète ; l’ancienne empreinte est refusée,
et un acquittement sous la nouvelle empreinte peut retourner UNCHANGED. Les
éditeurs externes qui ignorent les verrous restent hors garantie. Le SHA256 est
un contrôle de concurrence, pas une signature d’authenticité ou un droit d’accès.
Aucune ingestion automatique ni effacement de notes par règle de rétention.

Preuves du 03/10 : 25 nouveaux tests, 21 rouges sur le squelette ; deux processus
éditeurs, arrêt réel après publication, faute avant publication, stale après
rebuild, vue périmée/orpheline, CRLF, notes/payload CLI et garde readiness.
Neutraliser en mémoire le CAS ou la conservation de la zone générée produit
un échec comportemental chacun. Corpus synthétiques isolés, aucun service ou
corpus réel modifié. [Suite VM](VM-TESTS-2026-10-02.md).
