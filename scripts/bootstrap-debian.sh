#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "Eidolon Memory Engine - Debian bootstrap"
echo "Project root: ${PROJECT_ROOT}"

if [[ ! -f /etc/os-release ]]; then
    echo "ERROR: /etc/os-release introuvable."
    exit 1
fi

. /etc/os-release

if [[ "${ID:-}" != "debian" ]]; then
    echo "ERROR: Debian requis. OS détecté: ${ID:-unknown}"
    exit 1
fi

case "${VERSION_ID:-}" in
    12|13)
        echo "Debian ${VERSION_ID} (${VERSION_CODENAME:-unknown}) détecté."
        ;;
    *)
        echo "ERROR: Debian 12 ou 13 requis. Version détectée: ${VERSION_ID:-unknown}"
        exit 1
        ;;
esac

if ! command -v sudo >/dev/null 2>&1; then
    echo "ERROR: sudo est requis."
    exit 1
fi

if ! sudo -n true 2>/dev/null; then
    echo "Sudo nécessite une authentification."
    sudo -v
fi

echo "Prérequis de base: OK"

REQUIRED_PACKAGES=(
    git
    python3
    python3-venv
    python3-pip
    curl
    ca-certificates
    build-essential
    pkg-config
)

echo "Vérification des paquets système..."

MISSING_PACKAGES=()

for package in "${REQUIRED_PACKAGES[@]}"; do
    if dpkg-query -W -f='${Status}' "$package" 2>/dev/null | grep -q "install ok installed"; then
        echo "  OK      $package"
    else
        echo "  MISSING $package"
        MISSING_PACKAGES+=("$package")
    fi
done

if (( ${#MISSING_PACKAGES[@]} > 0 )); then
    echo "Installation des paquets manquants..."
    sudo apt-get update
    sudo apt-get install -y "${MISSING_PACKAGES[@]}"
else
    echo "Tous les paquets système sont déjà présents."
fi

echo
echo "Eidolon system bootstrap: READY"

echo
echo "Eidolon system bootstrap: READY"
