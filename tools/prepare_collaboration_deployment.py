"""Build a reviewed, secret-free VM package; optionally render deployment config."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
SOURCE_FILES = (
    "services/collaboration/__init__.py", "services/collaboration/exchange.py",
    "services/collaboration/server.py", "requirements-collaboration.txt",
)
TEMPLATES = ("install-vm.sh", "eidolon-collaboration.service", "environment.example", "Caddyfile.example")


def https_url(value):
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("URL HTTPS sans identifiants, query ou fragment requise")
    if any(ord(char) < 33 or char in '\\"' for char in value):
        raise ValueError("Caractère non autorisé dans une URL")
    return value


def render_config(domain, issuer, jwks, subject):
    if not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", domain) or "." not in domain or ".." in domain:
        raise ValueError("Nom DNS public requis, sans schéma, port ou chemin")
    if not re.fullmatch(r"[A-Za-z0-9_.|:@/+\-=]+", subject):
        raise ValueError("Identité OAuth requise, sans espace, virgule ou caractère de contrôle")
    https_url(issuer)
    https_url(jwks)
    template = (ROOT / "deployment/collaboration/environment.example").read_text()
    template = template.replace("https://collaboration.example.org/mcp", f"https://{domain}/mcp")
    template = template.replace("https://identity.example.org/.well-known/jwks.json", jwks)
    template = template.replace("https://identity.example.org/", issuer)
    template = template.replace("REPLACE_WITH_YOUR_OAUTH_SUBJECT", subject)
    caddy = (ROOT / "deployment/collaboration/Caddyfile.example").read_text().replace("collaboration.example.org", domain)
    return template, caddy


def build_package(destination: Path, config=None):
    if destination.exists():
        raise ValueError("La destination existe déjà ; choisir un nouveau dossier pour préserver le paquet")
    # Validate all configuration before creating anything.
    rendered = render_config(**config) if config else None
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    destination.mkdir(parents=True, mode=0o700)
    for name in SOURCE_FILES:
        target = destination / "app" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    for name in TEMPLATES:
        shutil.copyfile(ROOT / "deployment/collaboration" / name, destination / name)
    (destination / "install-vm.sh").chmod(0o700)
    if rendered:
        (destination / "environment").write_text(rendered[0])
        (destination / "Caddyfile").write_text(rendered[1])
        (destination / "environment").chmod(0o600)
    (destination / "NEXT-STEPS.md").write_text(NEXT_STEPS)
    hashes = {}
    for path in sorted(destination.rglob("*")):
        if path.is_file():
            hashes[path.relative_to(destination).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    metadata = {"base_commit": revision, "files_sha256": hashes, "configured": bool(config)}
    (destination / "manifest.json").write_text(json.dumps(metadata, indent=2) + "\n")
    hashes["manifest.json"] = hashlib.sha256((destination / "manifest.json").read_bytes()).hexdigest()
    (destination / "SHA256SUMS").write_text("".join(f"{digest}  {name}\n" for name, digest in hashes.items()))
    return metadata


NEXT_STEPS = """# Installation préparée — activation encore nécessaire

Ce paquet ne contient aucun secret. Le script installe le code et prépare une
clé privée dédiée uniquement sur la VM. Il ne démarre pas le MCP et ne modifie
pas une configuration Caddy existante. Les empreintes sont des contrôles locaux,
non une signature : examiner le paquet avant de l'exécuter comme administrateur.

1. Sur la VM Debian, vérifier les prérequis : python3-venv, git,
   openssh-client, util-linux, Caddy. Installation éventuelle depuis les dépôts
   Debian : `sudo apt-get install python3-venv git openssh-client util-linux caddy`.
   Examiner puis lancer `sudo bash ./install-vm.sh` depuis ce dossier.
2. Copier la clé PUBLIQUE affichée vers GitHub → ce dépôt → Settings → Deploy
   keys → Add deploy key, avec Allow write access. La clé privée reste sur VM.
3. Remplir environment.example avec le domaine /mcp, issuer OAuth, JWKS et
   identité sub autorisée. Le fournisseur doit émettre audience = URL /mcp et
   scope eidolon:exchange, RS256, Authorization Code + PKCE. Si environment est
   déjà fourni, l'utiliser après vérification. Installer le fichier validé dans
   /etc/eidolon-collaboration/environment (root, mode 0600).
4. Remplir credentials/known_hosts avec les clés GitHub vérifiées depuis la
   documentation officielle, puis le rendre lisible par le compte du service.
   Ne pas désactiver StrictHostKeyChecking et ne pas faire confiance à un
   ssh-keyscan sans comparaison des empreintes officielles.
5. Cloner la branche sous le compte eidolon-collaboration en utilisant la clé
   dédiée (GIT_SSH_COMMAND du fichier environment) :
   git clone --branch refactor/architecture-v1
   git@github.com:toytoy68/Eidolon-Memory-Engine.git
   /var/lib/eidolon-collaboration/repo
   Les trois arguments font partie de la même commande. Vérifier que le clone
   est propre ; ne jamais utiliser le checkout de développement pour ce service.
6. Configurer DNS public et accès 80/443, puis intégrer le bloc Caddyfile dans
   la configuration existante. Conserver le port 8765 local. Vérifier avec
   sudo caddy validate --config /etc/caddy/Caddyfile avant rechargement.
7. Après ces vérifications : sudo systemctl enable --now eidolon-collaboration
   puis sudo systemctl reload caddy. /mcp doit répondre 401 sans token ;
   /.well-known/oauth-protected-resource/mcp doit annoncer le bon issuer.
8. Dans Claude → Connecteurs, ajouter https://<domaine>/mcp, se connecter au
   compte autorisé et vérifier lecture GPT, réponse Claude et commit GitHub.

Contrat complet : docs/COLLABORATION-MCP.md du dépôt.
Clés/fingerprints GitHub :
https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/githubs-ssh-key-fingerprints
Aucun PAT GitHub à coller dans Claude. Le consentement OAuth dans Claude et
l'authentification administrateur doivent être réalisés par le propriétaire.
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    for field in ("domain", "issuer", "jwks", "subject"):
        parser.add_argument("--" + field)
    args = parser.parse_args()
    fields = {name: getattr(args, name) for name in ("domain", "issuer", "jwks", "subject")}
    if any(fields.values()) and not all(fields.values()):
        parser.error("Fournir ensemble domain, issuer, jwks et subject, ou aucun pour un paquet modèle")
    try:
        metadata = build_package(args.output, fields if all(fields.values()) else None)
    except ValueError as exc:
        parser.error(str(exc))
    print(f"Paquet préparé : {args.output.resolve()} (base {metadata['base_commit'][:7]})")
    print("Configuration renseignée." if metadata["configured"] else "Modèles prêts ; domaine et OAuth à renseigner.")


if __name__ == "__main__":
    main()
