#!/usr/bin/env bash

# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Script      : presentation.sh
# Description : Affichage commun des installateurs, sans effets système
# Standard    : Eidolon Presentation Standard v1
# ==========================================================

# Source this helper only; no installation, permissions, clearing or exit here.
eidolon_text() {
    local value="$*"
    while [[ "$value" =~ [[:cntrl:]] ]]; do
        value=${value//"${BASH_REMATCH[0]}"/}
    done
    printf '%s' "$value"
}
eidolon_separator() {
    printf '%s\n' '========================================================='
}
eidolon_section() {
    printf '\n'; eidolon_separator
    eidolon_text "$*"; printf '\n'; eidolon_separator
}
eidolon_message() {
    local level="$1"; shift
    printf '[%s] ' "$level"; eidolon_text "$*"; printf '\n'
}
eidolon_header() {
    printf '\n%s\n' '#########################################################'
    printf '# %-53s #\n' 'Eidolon Memory Engine' "$1"
    printf '%s\n' '#########################################################'
    printf '%s\n' 'Eidolon Core Technologies (ECT)' 'Local AI • Modular • Reliable • Reproducible'
    eidolon_message INFO 'Statut : outil opérationnel, validation sur la cible requise'
    eidolon_message INFO "Mode : $2"
}
eidolon_preview() {
    eidolon_header "$1" 'aperçu de présentation, sans installation'
    eidolon_section 'Opérations prévues'
    eidolon_message INFO "$2"
    eidolon_section 'Exemples de messages — aucune opération exécutée'
    eidolon_message INFO 'Une vérification serait annoncée ici.'
    eidolon_message ATTENTION 'Cet aperçu ne vérifie ni ne modifie la machine.'
    eidolon_section 'Suite'
    eidolon_message INFO 'Lire la procédure du composant avant son installation.'
}
