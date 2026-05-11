"""Device-flow Drive auth helpers - pure logic + httpx polling."""

import json
from pathlib import Path

import pytest


# --------------------------------------------------------------------------- #
# _extract_client_info: handle the various shapes of client_secret*.json
# --------------------------------------------------------------------------- #


class TestExtractClientInfo:
    def test_installed_wrapper(self):
        from sleuth.storage.gdrive_device import _extract_client_info
        data = {"installed": {"client_id": "cid", "client_secret": "csec"}}
        cid, csec = _extract_client_info(data)
        assert cid == "cid"
        assert csec == "csec"

    def test_web_wrapper(self):
        from sleuth.storage.gdrive_device import _extract_client_info
        data = {"web": {"client_id": "cid", "client_secret": "csec"}}
        cid, csec = _extract_client_info(data)
        assert (cid, csec) == ("cid", "csec")

    def test_bare(self):
        from sleuth.storage.gdrive_device import _extract_client_info
        data = {"client_id": "cid", "client_secret": "csec"}
        cid, csec = _extract_client_info(data)
        assert (cid, csec) == ("cid", "csec")

    def test_missing_fields_raises(self):
        from sleuth.storage.gdrive_device import _extract_client_info
        with pytest.raises(ValueError):
            _extract_client_info({"installed": {"client_id": "only-id"}})


# --------------------------------------------------------------------------- #
# _build_credentials_payload: turn a device-flow token response into the
# JSON shape that google-auth's Credentials.from_authorized_user_info reads.
# --------------------------------------------------------------------------- #


class TestBuildCredentialsPayload:
    def _resp(self, **over):
        base = {
            "access_token": "ya29.tok",
            "refresh_token": "1//0refresh",
            "expires_in": 3599,
            "scope": "https://www.googleapis.com/auth/drive.file",
            "token_type": "Bearer",
        }
        base.update(over)
        return base

    def test_basic_shape(self):
        from sleuth.storage.gdrive_device import _build_credentials_payload
        out = _build_credentials_payload(
            self._resp(), client_id="cid", client_secret="csec",
        )
        assert out["token"] == "ya29.tok"
        assert out["refresh_token"] == "1//0refresh"
        assert out["client_id"] == "cid"
        assert out["client_secret"] == "csec"
        assert out["token_uri"] == "https://oauth2.googleapis.com/token"
        assert out["scopes"] == ["https://www.googleapis.com/auth/drive.file"]

    def test_scopes_split_on_space(self):
        from sleuth.storage.gdrive_device import _build_credentials_payload
        out = _build_credentials_payload(
            self._resp(scope="a b c"), client_id="x", client_secret="y",
        )
        assert out["scopes"] == ["a", "b", "c"]

    def test_no_refresh_token_omitted_gracefully(self):
        """First-time grants always come with a refresh_token, but be defensive."""
        from sleuth.storage.gdrive_device import _build_credentials_payload
        resp = self._resp()
        del resp["refresh_token"]
        out = _build_credentials_payload(resp, client_id="x", client_secret="y")
        assert "refresh_token" not in out or out["refresh_token"] is None


# --------------------------------------------------------------------------- #
# _classify_poll_response: read an oauth2/token POST response, decide next step
# --------------------------------------------------------------------------- #


class TestClassifyPollResponse:
    def test_success(self):
        from sleuth.storage.gdrive_device import _classify_poll_response
        body = {"access_token": "ya29.tok", "refresh_token": "1//0r"}
        kind, payload = _classify_poll_response(200, body)
        assert kind == "success"
        assert payload["access_token"] == "ya29.tok"

    def test_pending(self):
        from sleuth.storage.gdrive_device import _classify_poll_response
        body = {"error": "authorization_pending"}
        kind, _ = _classify_poll_response(428, body)
        assert kind == "pending"

    def test_slow_down(self):
        from sleuth.storage.gdrive_device import _classify_poll_response
        body = {"error": "slow_down"}
        kind, _ = _classify_poll_response(403, body)
        assert kind == "slow_down"

    def test_access_denied(self):
        from sleuth.storage.gdrive_device import _classify_poll_response
        body = {"error": "access_denied"}
        kind, msg = _classify_poll_response(403, body)
        assert kind == "denied"
        assert "denied" in msg.lower()

    def test_expired(self):
        from sleuth.storage.gdrive_device import _classify_poll_response
        body = {"error": "expired_token"}
        kind, msg = _classify_poll_response(403, body)
        assert kind == "expired"

    def test_unknown_error_maps_to_failed(self):
        from sleuth.storage.gdrive_device import _classify_poll_response
        body = {"error": "weird_thing", "error_description": "huh"}
        kind, msg = _classify_poll_response(400, body)
        assert kind == "failed"
        assert "weird_thing" in msg


# --------------------------------------------------------------------------- #
# render_qr_ascii: small helper so we can confirm it actually produces output
# --------------------------------------------------------------------------- #


class TestRenderQr:
    def test_produces_blocky_output(self):
        from sleuth.storage.gdrive_device import render_qr_ascii
        out = render_qr_ascii("https://www.google.com/device")
        # The qrcode lib uses unicode block characters; just make sure
        # we got something multi-line and non-trivial back.
        assert isinstance(out, str)
        assert "\n" in out
        assert len(out) > 80  # a smallish QR is at least this big


# --------------------------------------------------------------------------- #
# request payloads sent to Google
# --------------------------------------------------------------------------- #


class TestRequestPayloads:
    def test_device_code_request(self):
        from sleuth.storage.gdrive_device import _device_code_payload
        body = _device_code_payload("the-client-id")
        assert body["client_id"] == "the-client-id"
        assert "drive.file" in body["scope"]

    def test_poll_request(self):
        from sleuth.storage.gdrive_device import _poll_payload
        body = _poll_payload(
            client_id="cid", client_secret="csec", device_code="dc-123",
        )
        assert body["client_id"] == "cid"
        assert body["client_secret"] == "csec"
        assert body["device_code"] == "dc-123"
        assert body["grant_type"] == "urn:ietf:params:oauth:grant-type:device_code"
