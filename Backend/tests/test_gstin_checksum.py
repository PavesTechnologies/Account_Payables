"""GSTIN check digit (Business_Layer/utils/extraction/normalizers.gstin_checksum_valid)."""
import pytest

from Backend.Business_Layer.utils.extraction.normalizers import gstin_checksum_valid


@pytest.mark.parametrize("gstin", ["07AAJCA9880A1ZL", "36AAFCK5835K1Z6", "27AAPFU0939F1ZV", "29AAGCB7383J1Z4"])
def test_real_gstins_pass(gstin):
    assert gstin_checksum_valid(gstin)


@pytest.mark.parametrize("gstin", ["07AAJCA9880A1ZM", "36AAFCK5835K1Z7", "36TSTFS0001T1ZB"])
def test_wrong_check_digit_fails(gstin):
    assert not gstin_checksum_valid(gstin)


def test_malformed_fails():
    assert not gstin_checksum_valid("NOTAGSTIN")
