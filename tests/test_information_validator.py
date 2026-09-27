from core.information.models import Information, InformationType, EpistemicStatus, OperationalState
from core.information.validator import validate_information, is_valid


def make_information():
    return Information(information_id="info-test")


def test_valid_information():
    information = make_information()
    assert validate_information(information) == []
    assert is_valid(information)


def test_empty_information_id():
    information = make_information()
    information.information_id = ""
    errors = validate_information(information)
    assert "id vide" in errors
    assert not is_valid(information)


def test_invalid_type():
    information = make_information()
    information.type = "INVALID"
    errors = validate_information(information)
    assert any("type invalide" in error for error in errors)


def test_invalid_epistemic_status():
    information = make_information()
    information.epistemic_status = "INVALID"
    errors = validate_information(information)
    assert any("epistemic_status invalide" in error for error in errors)


def test_invalid_operational_state():
    information = make_information()
    information.operational_state = "INVALID"
    errors = validate_information(information)
    assert any("operational_state invalide" in error for error in errors)
