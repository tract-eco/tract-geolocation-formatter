"""
Round-trip tests for the TRACT client against the local mock server
(SPEC-tract-integration, Work Item 4 / AC-4.2).

These need **no** QGIS environment: MockTractClient uses stdlib urllib, and the
mock server (dev/mock_tract_server.py) is stdlib http.server. They exercise the
same request-shaping and response-mapping logic as the real TractHttpClient —
only the transport differs.

    python -m pytest tests/test_tract_client.py -v
    python -m unittest tests.test_tract_client -v
"""

import os
import sys
import threading
import unittest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _REPO_ROOT)
sys.path.insert(0, os.path.join(_REPO_ROOT, "dev"))

import mock_tract_server as mock  # noqa: E402
from tract_geolocation_formatter.tract_client import (  # noqa: E402
    TRACT_DATA_FILES_BUCKET_TYPE,
    MockTractClient,
    TractAuthError,
    TractError,
    TractNotFoundError,
    TractTransportError,
    resolve_transfer,
)

_GOOD = "test-client"
_SECRET = "test-secret"
_REALM = "myrealm"


def _poll_until_terminal(client, file_id, max_polls=6):
    status = None
    for _ in range(max_polls):
        status = client.get_status(file_id)
        if status.is_terminal:
            break
    return status


class TestResolveTransfer(unittest.TestCase):
    """The §2 shape rule — pure, no server."""

    def test_absolute_http_as_is_no_token(self):
        url = "https://storage.googleapis.com/bucket/obj?sig=abc"
        self.assertEqual(resolve_transfer(url, "https://api.tract/"), (url, False))

    def test_relative_resolves_to_origin_with_token(self):
        resolved, attach = resolve_transfer("/v3/transfer/xyz", "https://api.tract.example/base/x")
        self.assertEqual(resolved, "https://api.tract.example/v3/transfer/xyz")
        self.assertTrue(attach)

    def test_unknown_shape_raises(self):
        with self.assertRaises(TractTransportError):
            resolve_transfer("ftp://nope/x", "https://api.tract/")

    def test_relative_against_bad_base_raises(self):
        with self.assertRaises(TractTransportError):
            resolve_transfer("/rel", "not-a-url")


class _MockServerTestCase(unittest.TestCase):
    """Base: spin up a mock server with a given transfer-URL shape per client."""

    def _client(self, shape="relative", client_id=_GOOD, secret=_SECRET):
        httpd, _state = mock.make_server("127.0.0.1", 0, shape)
        port = httpd.server_address[1]
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()

        def _stop():
            httpd.shutdown()
            httpd.server_close()  # release the listening socket (no ResourceWarning)

        self.addCleanup(_stop)
        base = "http://127.0.0.1:{0}".format(port)
        # Keycloak is served by the same mock host.
        return MockTractClient(base, base, _REALM, client_id, secret)


class TestSend(_MockServerTestCase):

    def test_send_success_both_shapes(self):
        """AC-2.1: mint -> PUT -> poll -> completed, for both URL shapes."""
        for shape in ("relative", "absolute"):
            with self.subTest(shape=shape):
                client = self._client(shape)
                ticket = client.create_upload("plots.geojson")
                self.assertTrue(ticket.file_id)
                if shape == "absolute":
                    self.assertTrue(ticket.transfer_url.startswith("http"))
                else:
                    self.assertTrue(ticket.transfer_url.startswith("/"))
                client.put_bytes(ticket.transfer_url, b'{"type":"FeatureCollection","features":[]}')
                status = _poll_until_terminal(client, ticket.file_id)
                self.assertTrue(status.is_terminal)
                self.assertTrue(status.is_success)
                self.assertFalse(status.failed)

    def test_send_validation_failed(self):
        """AC-2.2: a 'bad*' filename ingests to staticValidationFailed + report."""
        client = self._client()
        ticket = client.create_upload("bad_plots.geojson")
        client.put_bytes(ticket.transfer_url, b"{}")
        status = _poll_until_terminal(client, ticket.file_id)
        self.assertTrue(status.failed)
        self.assertEqual(status.file_status, "staticValidationFailed")
        self.assertTrue(status.error_report_name)


class TestReceive(_MockServerTestCase):

    def test_receive_success_both_shapes(self):
        """AC-3.1: signed-url -> get bytes returns the seeded dirty GeoJSON."""
        for shape in ("relative", "absolute"):
            with self.subTest(shape=shape):
                client = self._client(shape)
                url = client.create_download(mock.GOOD_DOWNLOAD, TRACT_DATA_FILES_BUCKET_TYPE)
                data = client.get_bytes(url)
                self.assertIn(b"FeatureCollection", data)
                self.assertIn(b"NODE_1", data)

    def test_receive_unknown_filename_not_found(self):
        """AC-3.3: unknown filename -> TractNotFoundError (signed-url 404)."""
        client = self._client()
        with self.assertRaises(TractNotFoundError):
            client.create_download("does-not-exist.geojson", TRACT_DATA_FILES_BUCKET_TYPE)

    def test_receive_bad_bucket_is_not_not_found(self):
        """AC (spec §7): bad bucket_type -> a distinct TractError(400), not NotFound."""
        client = self._client()
        with self.assertRaises(TractError) as ctx:
            client.create_download(mock.GOOD_DOWNLOAD, "wrong_bucket")
        self.assertNotIsInstance(ctx.exception, TractNotFoundError)
        self.assertEqual(ctx.exception.status, 400)

    def test_receive_transfer_failure(self):
        """AC-3.5: signed-url succeeds but the transfer GET fails -> transport error."""
        client = self._client()
        url = client.create_download(mock.BROKEN_DOWNLOAD, TRACT_DATA_FILES_BUCKET_TYPE)
        with self.assertRaises(TractTransportError):
            client.get_bytes(url)


class TestAuth(_MockServerTestCase):

    def test_bad_secret_is_auth_error(self):
        """AC-1.2 / AC-3.4: a wrong client_secret -> TractAuthError (not not-found)."""
        client = self._client(secret="WRONG-SECRET")
        with self.assertRaises(TractAuthError):
            client.test_connection()

    def test_good_credentials_connect(self):
        """AC-1.2: valid credentials -> test_connection() returns True."""
        client = self._client()
        self.assertTrue(client.test_connection())


if __name__ == "__main__":
    unittest.main()
