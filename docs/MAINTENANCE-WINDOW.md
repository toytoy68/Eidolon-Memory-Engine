# Prévisualisation du créneau d'entretien

Première préparation de T-046 : une fonction pure et une CLI examinent un
instant courant, une dernière activité fournie explicitement, un créneau local,
un fuseau IANA et une durée minimale d'inactivité. Aucun job n'est installé,
aucun service lancé, aucune racine mémoire lue ou écrite.

```bash
.venv/bin/python -m tools.preview_maintenance_window \
  --at 2026-10-04T04:00:00+02:00 \
  --last-activity 2026-10-04T03:30:00+02:00 \
  --start 04:00 --end 08:00 --timezone Europe/Paris \
  --minimum-idle-minutes 30
```

Cet exemple donne ELIGIBLE avec execution_performed=false. Les paramètres sont
obligatoires : l'exemple ne fixe pas une politique déployée. DEFERRED expose
OUTSIDE_WINDOW et/ou ACTIVITY_RECENT ; BLOCKED indique des données invalides.
ELIGIBLE n'affirme ni readiness ni absence d'écrivain : une éventuelle exécution
doit encore utiliser le service d'entretien et sa garde --if-idle.

Le début est inclus, la fin exclue. Un créneau traversant minuit est accepté ;
un début égal à la fin est refusé pour éviter l'ambiguïté vide/24 heures.
Les dates exigent un fuseau et une activité future est refusée. Le créneau est
évalué en heure locale, l'inactivité en temps UTC écoulé : un changement d'heure
ne raccourcit ou n'allonge pas artificiellement cette durée.

Validation locale : 21 cas du module, 43 tests ciblés avec la passe d'entretien.
Bornes horaires, inactivité, créneau nocturne, deux transitions DST, refus des
entrées invalides et absence d'écriture CLI vérifiés. Aucun test VM revendiqué.

Restant avant automatisation : définir ce qui compte comme activité (écriture,
interaction ou charge), son observation durable et fraîche, le report en cas de
charge, la reprise au boot et son interaction avec le créneau, le contexte réel
d'exécution, la gestion des erreurs et la fréquence. La règle --if-idle existante
ne mesure que certains verrous canoniques, pas l'inactivité de la machine.
Le preview n'observe pas CPU/SSH et ne simule pas ces critères.


## Horaires locaux aux changements d'heure — revue Claude

Un créneau 02:00–03:00 en Europe/Paris n'existe pas la nuit du passage à
l'heure d'été ; au passage à l'heure d'hiver, il s'ouvre deux fois (120 minutes
écoulées). C'est le comportement du créneau en heure locale, distinct de la
durée d'inactivité calculée en UTC. Préférer un créneau évitant cette heure
ambiguë ; l'exemple 04:00–08:00 n'est pas affecté par ce problème.
Les paramètres syntaxiquement invalides (par exemple --minimum-idle-minutes abc)
relèvent d'argparse : erreur d'usage sur stderr, code 2. Les valeurs parsées mais
invalides pour la politique donnent BLOCKED/code 1. Ce sont deux catégories
d'erreur distinctes ; aucun JSON n'est garanti pour une erreur de syntaxe CLI.
