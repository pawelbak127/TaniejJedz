"""Tests for UberEats UUID decode and adapter v3."""

import base64
import uuid as uuid_module

import pytest

from app.scraper.adapters.ubereats import (
    decode_ubereats_uuid,
    _is_base64url_uuid,
    _ensure_hex_uuid,
)


class TestDecodeUberEatsUuid:

    def test_known_uuid(self):
        """Verified against live API: this decode produces a working UUID."""
        result = decode_ubereats_uuid("skuqnuRLTnWC8PipFYCYfg")
        assert result == "b24baa9e-e44b-4e75-82f0-f8a91580987e"

    def test_roundtrip(self):
        """Encode a known UUID → decode should return original."""
        original = uuid_module.UUID("dc283907-7f26-4417-a1be-38779353993a")
        b64 = base64.urlsafe_b64encode(original.bytes).rstrip(b"=").decode()
        assert decode_ubereats_uuid(b64) == str(original)

    def test_all_verified_uuids(self):
        """All UUIDs confirmed working with getStoreV1 after decode."""
        cases = {
            "skuqnuRLTnWC8PipFYCYfg": "b24baa9e-e44b-4e75-82f0-f8a91580987e",
            "3Cg5B38mRBehvjh3k1OZOg": "dc283907-7f26-4417-a1be-38779353993a",
            "LIRzHG9sU0ai21DfG1GJxA": "2c84731c-6f6c-5346-a2db-50df1b5189c4",
            "mV0wGhrDTEaWWgOz299rng": "995d301a-1ac3-4c46-965a-03b3dbdf6b9e",
        }
        for b64url, expected_hex in cases.items():
            assert decode_ubereats_uuid(b64url) == expected_hex

    def test_invalid_length(self):
        with pytest.raises(ValueError, match="Expected 16 bytes"):
            decode_ubereats_uuid("tooshort")

    def test_output_is_valid_uuid(self):
        result = decode_ubereats_uuid("skuqnuRLTnWC8PipFYCYfg")
        parsed = uuid_module.UUID(result)
        assert str(parsed) == result


class TestIsBase64urlUuid:

    def test_base64url(self):
        assert _is_base64url_uuid("skuqnuRLTnWC8PipFYCYfg") is True

    def test_hex_uuid(self):
        assert _is_base64url_uuid("b24baa9e-e44b-4e75-82f0-f8a91580987e") is False

    def test_short_string(self):
        assert _is_base64url_uuid("abc") is False


class TestEnsureHexUuid:

    def test_converts_base64url(self):
        result = _ensure_hex_uuid("skuqnuRLTnWC8PipFYCYfg")
        assert result == "b24baa9e-e44b-4e75-82f0-f8a91580987e"

    def test_passes_through_hex(self):
        hex_uuid = "b24baa9e-e44b-4e75-82f0-f8a91580987e"
        assert _ensure_hex_uuid(hex_uuid) == hex_uuid
