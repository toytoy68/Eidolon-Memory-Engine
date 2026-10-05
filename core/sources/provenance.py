# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : core/sources/provenance.py
# Description : Model-origin vocabulary; historical labels are recognized, never rewritten.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================

"""Model-origin vocabulary; historical labels are recognized, never rewritten."""
MODEL_OUTPUT = 'MODEL_OUTPUT'


def is_model_source_type(value):
    """Origin only: neither human review nor this label confirms a claim."""
    return isinstance(value, str) and value in {
        MODEL_OUTPUT, 'MODEL_GENERATED', 'MODEL_INFERENCE',
    }
