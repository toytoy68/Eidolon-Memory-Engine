#!/usr/bin/env bash
# Install the prepared package without opening the endpoint or starting the MCP.
set -euo pipefail
umask 077

bundle_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
app_root=/opt/eidolon-collaboration
service_state=/var/lib/eidolon-collaboration
service_account=eidolon-collaboration

if [[ "$EUID" -ne 0 ]]; then
    echo "Relancer ce script avec sudo dans le terminal de la VM." >&2
    exit 1
fi
if systemctl is-active --quiet eidolon-collaboration; then
    echo "Le service est actif. Arrêter et examiner la mise à jour avant installation." >&2
    exit 1
fi
for executable in python3 git ssh-keygen useradd runuser systemctl systemd-analyze sha256sum; do
    command -v "$executable" >/dev/null || { echo "Prérequis manquant : $executable" >&2; exit 1; }
done
(cd "$bundle_dir" && sha256sum --check SHA256SUMS)
# A disposable copy prevents changes to the supplied bundle during installation.
staging_dir="$(mktemp -d /tmp/eidolon-collaboration-install.XXXXXXXX)"
trap 'rm -rf -- "$staging_dir"' EXIT
cp -a "$bundle_dir/app" "$staging_dir/app"

if ! id "$service_account" >/dev/null 2>&1; then
    useradd --system --user-group --home-dir "$service_state" --shell /usr/sbin/nologin "$service_account"
fi
install -d -o root -g root -m 0755 "$app_root"
install -d -o "$service_account" -g "$service_account" -m 0700 "$service_state" "$service_state/state" "$service_state/credentials"
install -d -o root -g root -m 0700 /etc/eidolon-collaboration

# Keep prior installations intact; select the new release only after dependencies work.
release_dir="$(mktemp -d "$app_root/release.XXXXXXXX")"
cp -a "$staging_dir/app/." "$release_dir/"
chown -R root:root "$release_dir"
chmod -R u=rwX,go=rX "$release_dir"
if [[ ! -x "$app_root/venv/bin/python" ]]; then
    python3 -m venv "$app_root/venv"
fi
"$app_root/venv/bin/python" -m pip install -r "$release_dir/requirements-collaboration.txt"
"$app_root/venv/bin/python" -m pip check
if [[ -e "$app_root/app" && ! -L "$app_root/app" ]]; then
    echo "$app_root/app existe et n'est pas un lien de release ; examiner manuellement." >&2
    exit 1
fi
ln -s "$release_dir" "$app_root/app.next"
mv -Tf "$app_root/app.next" "$app_root/app"

install -o root -g root -m 0644 "$bundle_dir/eidolon-collaboration.service" /etc/systemd/system/eidolon-collaboration.service
install -o root -g root -m 0600 "$bundle_dir/environment.example" /etc/eidolon-collaboration/environment.example
install -o root -g root -m 0600 "$bundle_dir/Caddyfile.example" /etc/eidolon-collaboration/Caddyfile.example

if [[ ! -e "$service_state/credentials/github_ed25519" ]]; then
    runuser -u "$service_account" -- ssh-keygen -q -t ed25519 -N '' \
        -C 'Eidolon Collaboration dedicated deploy key' -f "$service_state/credentials/github_ed25519"
fi
systemd-analyze verify /etc/systemd/system/eidolon-collaboration.service
systemctl daemon-reload

echo "Installation préparée. Service MCP non démarré."
echo "Ajouter cette clé PUBLIQUE comme Deploy key GitHub de ce dépôt, avec droit d'écriture :"
cat "$service_state/credentials/github_ed25519.pub"
echo "Puis suivre NEXT-STEPS.md pour OAuth, clone dédié, HTTPS et activation."
