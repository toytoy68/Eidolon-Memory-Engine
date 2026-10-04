#!/usr/bin/env bash
# Replace the manually started Eidolon dashboard by the systemd unit
# eidolon-dashboard, then verify it. Run as root:  sudo bash install-dashboard-service.sh
#
# - The token is copied from the running manual dashboard's environment into
#   /etc/eidolon-dashboard/environment (root:root 0600). It is never printed,
#   passed as an argument or written anywhere else (the rollback relaunch
#   transports the former environment as environment, never as argv).
# - Only the process listening on 192.168.1.110:8766 is stopped. MCP (8765),
#   cloudflared and Ollama are not touched; their state is compared at the end.
# - If the unit does not come up, it is disabled and the manual process is
#   relaunched with its exact former command line and environment.
set -euo pipefail
umask 077
export LC_ALL=C

UNIT=eidolon-dashboard
HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
SRC_UNIT=$HERE/$UNIT.service
ENV_DIR=/etc/eidolon-dashboard
ENV_FILE=$ENV_DIR/environment
ADDR=192.168.1.110
PORT=8766
URL=http://$ADDR:$PORT/
LOG=/home/toytoy/eidolon-dashboard.log

say() { printf '%s\n' "$*"; }
die() { say "ERREUR: $*"; exit 1; }
listener_pid() { ss -ltnpH "( sport = :$PORT )" 2>/dev/null | grep -F "$ADDR:$PORT" | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2; }
wait_listener() { local p; for _ in $(seq 1 75); do p=$(listener_pid || true); [ -n "$p" ] && { echo "$p"; return 0; }; sleep 0.2; done; return 1; }
wait_gone() { for _ in $(seq 1 75); do kill -0 "$1" 2>/dev/null || return 0; sleep 0.2; done; return 1; }
http_code() { curl -s -o /dev/null -m 10 -w '%{http_code}' "$@" "$URL"; }
auth_get() {  # $1 = output file; Authorization header given on stdin, never on the command line
  local auth
  auth=$(printf 'eidolon:%s' "$(sed -n 's/^EIDOLON_DASHBOARD_TOKEN=//p' "$ENV_FILE")" | base64 -w0)
  printf 'Authorization: Basic %s\n' "$auth" | curl -s -m 15 -o "$1" -w '%{http_code}' -H @- "$URL"
}
check_http() {  # label
  local body code n anon
  body=$(mktemp)
  anon=$(http_code || true)
  say "  [$1] sans authentification : HTTP $anon"
  code=$(auth_get "$body" || true); n=$(grep -o 'resource-text' "$body" | wc -l)
  say "  [$1] avec authentification : HTTP $code, $(wc -c < "$body") octets, resource-text x$n"
  rm -f "$body"
  [ "$anon" = 401 ] && [ "$code" = 200 ] && [ "$n" -gt 0 ]
}
others() { printf 'collab=%s cloudflared=%s ollama=%s mcp8765=%s' \
  "$(systemctl show -p MainPID --value eidolon-collaboration)" "$(systemctl show -p MainPID --value cloudflared)" \
  "$(systemctl is-active ollama 2>/dev/null || true)" "$(ss -ltnH '( sport = :8765 )' | grep -c . || true)"; }

[ "$(id -u)" = 0 ] || die "lancer avec sudo"
[ -f "$SRC_UNIT" ] || die "modèle $SRC_UNIT absent"
systemctl cat "$UNIT" >/dev/null 2>&1 && die "l'unité $UNIT existe déjà ; rien n'est modifié"
OTHERS_BEFORE=$(others)
say "Autres services avant : $OTHERS_BEFORE"

# 1. Identify the manual dashboard.
OLD=$(listener_pid) || true
[ -n "${OLD:-}" ] || die "aucun processus n'écoute sur $ADDR:$PORT"
[ "$(stat -c %U /proc/"$OLD")" = toytoy ] || die "PID $OLD n'appartient pas à toytoy"
grep -qa 'core.monitoring.dashboard' /proc/"$OLD"/cmdline || die "PID $OLD n'est pas le dashboard"
grep -q 'system.slice' /proc/"$OLD"/cgroup && die "PID $OLD est déjà géré par systemd"
mapfile -d '' OLD_ARGS < /proc/"$OLD"/cmdline
mapfile -d '' OLD_ENV < /proc/"$OLD"/environ
OLD_CWD=$(readlink /proc/"$OLD"/cwd)
say "Dashboard manuel : PID $OLD, $(tr '\0' ' ' < /proc/"$OLD"/cmdline)"
EXPECTED=$(sed -n 's/^ExecStart=//p' "$SRC_UNIT")
[ "$(printf '%s ' "${OLD_ARGS[@]}")" = "$EXPECTED " ] || die "arguments du processus différents du modèle ; rien n'est modifié"

# 2. Protected environment file (token only).
TOKEN_LINE=$(printf '%s\n' "${OLD_ENV[@]}" | grep '^EIDOLON_DASHBOARD_TOKEN=.' || true)
[ -n "$TOKEN_LINE" ] || die "token absent de l'environnement du processus"
# systemd EnvironmentFile interprets quotes, backslashes and '$': refuse rather than alter the value.
printf '%s' "${TOKEN_LINE#EIDOLON_DASHBOARD_TOKEN=}" | grep -Eq '^[A-Za-z0-9._~+/=:@%,-]+$' \
  || die "le token contient des caractères à échapper ; écrire $ENV_FILE à la main"
install -d -m 0700 -o root -g root "$ENV_DIR"
if [ -e "$ENV_FILE" ]; then
  say "Fichier $ENV_FILE déjà présent : conservé"
else
  tmp=$(mktemp "$ENV_DIR/.environment.XXXXXX")
  printf '%s\n' "$TOKEN_LINE" > "$tmp"
  chmod 0600 "$tmp"; chown root:root "$tmp"; mv "$tmp" "$ENV_FILE"
fi
unset TOKEN_LINE
say "Fichier d'environnement : $(stat -c '%U:%G %a' "$ENV_FILE"), $(wc -l < "$ENV_FILE") ligne"

# 3. Unit.
install -m 0644 -o root -g root "$SRC_UNIT" /etc/systemd/system/$UNIT.service
systemd-analyze verify /etc/systemd/system/$UNIT.service
systemctl daemon-reload
systemctl enable "$UNIT" >/dev/null

# 4. Replace the manual process.
kill -TERM "$OLD"
wait_gone "$OLD" || die "PID $OLD toujours actif après 15 s ; arrêt forcé non effectué (unité installée, non démarrée)"
say "Processus manuel $OLD arrêté"
relaunch_manual() {
  # The former environment holds the token: it is exported, never passed as
  # arguments (argv is world-readable in /proc). setpriv execs the dashboard
  # directly, so no parent process keeps the environment on its command line.
  local setsid_bin setpriv_bin
  setsid_bin=$(command -v setsid); setpriv_bin=$(command -v setpriv)
  (
    cd "$OLD_CWD" || exit 1
    while IFS= read -r name; do unset "$name" 2>/dev/null || true; done < <(compgen -e)
    for kv in "${OLD_ENV[@]}"; do export "$kv" 2>/dev/null || true; done
    exec "$setsid_bin" "$setpriv_bin" --reuid=toytoy --regid=toytoy --init-groups -- "${OLD_ARGS[@]}" >> "$LOG" 2>&1 < /dev/null
  ) &
}
rollback() {
  say "ÉCHEC du service : retour au processus manuel"
  systemctl disable --now "$UNIT" >/dev/null 2>&1 || true
  tail -n 20 "$LOG" | cut -c1-200
  relaunch_manual
  sleep 3; say "Processus manuel relancé : PID $(listener_pid || echo aucun)"
  exit 1
}
printf -- '--- %s systemd %s start\n' "$(date -Iseconds)" "$UNIT" >> "$LOG"
systemctl start "$UNIT" || rollback
NEW=$(wait_listener) || rollback
[ "$NEW" = "$(systemctl show -p MainPID --value "$UNIT")" ] || rollback
say "Service actif : PID $NEW, enabled=$(systemctl is-enabled "$UNIT"), user=$(stat -c %U /proc/"$NEW")"
cmp -s <(tr '\0' '\n' < /proc/"$NEW"/environ | grep '^EIDOLON_DASHBOARD_TOKEN=') "$ENV_FILE" \
  && say "  token vu par le service identique au fichier (comparaison sans affichage)" || rollback
check_http initial || rollback

# 5. Restart test (systemctl restart).
systemctl restart "$UNIT" || rollback
R=$(wait_listener) || rollback
[ "$R" != "$NEW" ] || rollback
say "systemctl restart : PID $NEW -> $R"
check_http restart || rollback

# 6. Crash test (SIGKILL -> Restart=on-failure).
kill -KILL "$R"
say "SIGKILL envoyé au PID $R ; attente de la reprise automatique (RestartSec=5)"
sleep 1
C=$(wait_listener) || { sleep 5; C=$(wait_listener) || rollback; }
[ "$C" != "$R" ] || rollback
say "Reprise après plantage : PID $R -> $C, NRestarts=$(systemctl show -p NRestarts --value "$UNIT")"
check_http plantage || rollback

OTHERS_AFTER=$(others)
say "Autres services après : $OTHERS_AFTER"
[ "$OTHERS_BEFORE" = "$OTHERS_AFTER" ] && say "MCP, cloudflared et Ollama inchangés" || say "ATTENTION: état des autres services différent"
systemctl --no-pager --lines=0 status "$UNIT" | head -6
say "TERMINÉ"
