# -*- coding: utf-8 -*-
"""
TRACT integration client seam (SPEC-tract-integration, Work Items 1 & 3).

All networking for the optional Send-to-TRACT / Receive-from-TRACT features lives
behind the small interface defined here. UI and QgsTask code talk to a
``TractClient`` and never touch ``QgsBlockingNetworkRequest`` or transfer URLs
directly.

Design notes:
- ``resolve_transfer``, the data holders, the exception hierarchy, and the
  ``TractClient`` ABC are pure Python (stdlib only) so they import and unit-test
  without a QGIS environment.
- Raw HTTP is isolated behind a tiny ``_Transport`` seam so the request-shaping
  and response-mapping logic is shared by both clients:
    * ``TractHttpClient``  -> ``QgsTransport``   (QGIS ``QgsBlockingNetworkRequest``;
      works inside a background thread).
    * ``MockTractClient``  -> ``UrllibTransport`` (stdlib ``urllib``); points at the
      local mock server (dev/mock_tract_server.py) and needs **no** QGIS, so the
      Task-7 tests run without a QGIS environment.
- QGIS imports are deferred (lazy) inside ``QgsTransport`` — the rest of the module
  imports without QGIS.
- Constitution §4/§7 (amended 2026-07-06): network access is limited to the TRACT
  API + Keycloak, on explicit user action. No new third-party dependencies — QGIS
  network classes or stdlib only, never ``requests``.
"""

import json
import time
from abc import ABC, abstractmethod
from urllib.parse import urlencode, urlsplit, urlunsplit


# Hardcoded per spec §5 — the only bucket the plugin reads/writes in v1.
TRACT_DATA_FILES_BUCKET_TYPE = "data_files"

# Terminal ingestion states from GET /v3/files/statuses (spec §2).
_TERMINAL_STATUSES = frozenset({"completed", "staticValidationFailed"})

_DEFAULT_TIMEOUT = 30


# ---------------------------------------------------------------------------
# Exceptions — let callers (tasks/UI) present distinct messages (spec §7).
# ---------------------------------------------------------------------------
class TractError(Exception):
    """Base for all TRACT client errors, carrying an HTTP status when known."""

    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


class TractAuthError(TractError):
    """Keycloak/authorization failure (typically HTTP 401)."""


class TractNotFoundError(TractError):
    """Requested file was not found (target: signed-url HTTP 404, spec §4.A)."""


class TractTransportError(TractError):
    """Network/transfer failure distinct from auth and not-found."""


# ---------------------------------------------------------------------------
# Transfer-URL shape resolution (spec §2) — pure, the crux of the design.
# ---------------------------------------------------------------------------
def resolve_transfer(url, base_url):
    """Resolve a minted transfer URL and decide whether to attach the bearer.

    Shape-driven (never config-driven), per spec §2:

    - starts with ``http`` -> absolute (e.g. a GCS signed URL on a second host);
      use as-is and do **not** attach the Keycloak bearer (the URL carries its
      own auth). Returns ``(url, False)``.
    - starts with ``/`` -> relative; the transfer goes back to TRACT's own host,
      so resolve against the ``base_url`` origin and **do** attach the bearer.
      Returns ``(base_origin + url, True)``.

    Any other shape is a transport error (we cannot tell how to reach it).
    """
    if url.startswith("http"):
        return url, False
    if url.startswith("/"):
        parts = urlsplit(base_url)
        if not parts.scheme or not parts.netloc:
            raise TractTransportError(
                "Cannot resolve a relative transfer URL against base URL "
                "{0!r}.".format(base_url)
            )
        origin = urlunsplit((parts.scheme, parts.netloc, "", "", ""))
        return origin + url, True
    raise TractTransportError(
        "Unrecognized transfer URL shape: {0!r}".format(url)
    )


def _response_detail(resp, limit=800):
    """A short, human-readable snippet of a response body for error messages.

    Returns '' when there is no body. This is what turns an opaque
    'Unexpected response (422)' into '(422) Server said: {"product": "required"}'.
    """
    if resp is None or not resp.content:
        return ""
    try:
        text = resp.content.decode("utf-8", "replace").strip()
    except Exception:
        return ""
    if not text:
        return ""
    if len(text) > limit:
        text = text[:limit] + "…"
    return " Server said: {0}".format(text)


def _keycloak_error_detail(resp):
    """Extract Keycloak's error / error_description for a clearer auth message."""
    try:
        payload = resp.json()
        parts = [payload.get("error"), payload.get("error_description")]
        detail = " - ".join(p for p in parts if p)
        if detail:
            return ": " + detail
    except Exception:
        pass
    return _response_detail(resp)


# ---------------------------------------------------------------------------
# Data holders — map the camelCase API fields into stable snake_case attrs.
# ---------------------------------------------------------------------------
class UploadTicket:
    """Result of minting an upload: the id to poll + the URL to PUT bytes to."""

    def __init__(self, file_id, transfer_url, bucket_type):
        self.file_id = file_id
        self.transfer_url = transfer_url
        self.bucket_type = bucket_type

    def __repr__(self):
        return "UploadTicket(file_id={0!r}, bucket_type={1!r})".format(
            self.file_id, self.bucket_type
        )


class FileStatus:
    """One element of GET /v3/files/statuses (fields are camelCase in the API)."""

    def __init__(self, id, file_status, error_report_name=None):
        self.id = id
        self.file_status = file_status
        self.error_report_name = error_report_name or ""

    @classmethod
    def from_api(cls, obj):
        """Build from a raw status element: id / fileStatus / errorReportName."""
        return cls(
            id=obj.get("id"),
            file_status=obj.get("fileStatus"),
            error_report_name=obj.get("errorReportName"),
        )

    @property
    def is_terminal(self):
        return self.file_status in _TERMINAL_STATUSES

    @property
    def is_success(self):
        return self.file_status == "completed"

    @property
    def failed(self):
        """Terminal but not successful (e.g. staticValidationFailed)."""
        return self.is_terminal and not self.is_success

    def __repr__(self):
        return "FileStatus(id={0!r}, file_status={1!r}, error_report_name={2!r})".format(
            self.id, self.file_status, self.error_report_name
        )


# ---------------------------------------------------------------------------
# HTTP transport seam — isolates the one QGIS-vs-stdlib difference.
# ---------------------------------------------------------------------------
class HttpResponse:
    """A normalized HTTP result. ``error`` is set only on transport failure
    (no status at all); HTTP 4xx/5xx come back with a ``status`` and ``content``
    so the caller can map them (401 -> auth, 404 -> not-found, etc.)."""

    def __init__(self, status, content, error=None):
        self.status = status
        self.content = content or b""
        self.error = error

    def json(self):
        return json.loads(self.content.decode("utf-8"))


class _Transport(ABC):
    @abstractmethod
    def send(self, method, url, headers=None, body=None, timeout=_DEFAULT_TIMEOUT):
        """Perform one request. Returns HttpResponse; never raises for HTTP
        error statuses (only for genuine transport failure via error=...)."""


class QgsTransport(_Transport):
    """Real transport using QGIS ``QgsBlockingNetworkRequest`` (lazy QGIS import)."""

    def send(self, method, url, headers=None, body=None, timeout=_DEFAULT_TIMEOUT):
        from qgis.PyQt.QtCore import QByteArray, QUrl
        from qgis.PyQt.QtNetwork import QNetworkRequest
        from qgis.core import QgsBlockingNetworkRequest

        request = QNetworkRequest(QUrl(url))
        for key, value in (headers or {}).items():
            request.setRawHeader(
                QByteArray(key.encode("utf-8")), QByteArray(value.encode("utf-8"))
            )

        blocking = QgsBlockingNetworkRequest()
        payload = QByteArray(body or b"")
        method = method.upper()
        if method == "GET":
            err = blocking.get(request)
        elif method == "POST":
            err = blocking.post(request, payload)
        elif method == "PUT":
            put = getattr(blocking, "put", None)
            if put is None:
                raise TractTransportError(
                    "This QGIS version's QgsBlockingNetworkRequest has no put(); "
                    "a newer QGIS is required for uploads."
                )
            err = put(request, payload)
        else:
            raise TractTransportError("Unsupported HTTP method: {0}".format(method))

        reply = blocking.reply()
        status = None
        content = b""
        if reply is not None:
            status = reply.attribute(
                QNetworkRequest.Attribute.HttpStatusCodeAttribute
            )
            content = bytes(reply.content())

        # An HTTP error status is a valid response, not a transport error.
        if status is not None:
            return HttpResponse(status, content, error=None)
        if err != QgsBlockingNetworkRequest.NoError:
            return HttpResponse(None, content, error=blocking.errorMessage() or "network error")
        return HttpResponse(status, content, error=None)


class UrllibTransport(_Transport):
    """Stdlib transport (no QGIS) used by MockTractClient and the tests."""

    def send(self, method, url, headers=None, body=None, timeout=_DEFAULT_TIMEOUT):
        import urllib.error
        import urllib.request

        request = urllib.request.Request(
            url, data=body, method=method.upper(), headers=headers or {}
        )
        try:
            resp = urllib.request.urlopen(request, timeout=timeout)
            return HttpResponse(getattr(resp, "status", resp.getcode()), resp.read())
        except urllib.error.HTTPError as exc:
            # HTTP error status: still a response — hand back status + body.
            return HttpResponse(exc.code, exc.read())
        except urllib.error.URLError as exc:
            return HttpResponse(None, b"", error=str(exc.reason))
        except OSError as exc:  # e.g. connection refused / timeout
            return HttpResponse(None, b"", error=str(exc))


# ---------------------------------------------------------------------------
# Keycloak token provider (OAuth2 client-credentials) — spec §2.
# ---------------------------------------------------------------------------
class KeycloakTokenProvider:
    """Fetches and caches a Keycloak access token via client-credentials.

    Renewal is deliberately simple (spec §2): when the cached token is expired or
    within ``leeway`` seconds of expiry, re-request. No refresh-token logic. The
    ``transport`` is the seam that makes this usable with QGIS or stdlib; when
    omitted it defaults to a real ``QgsTransport``.
    """

    def __init__(self, keycloak_base, realm, client_id, client_secret,
                 transport=None, leeway=30, timeout=_DEFAULT_TIMEOUT):
        self.keycloak_base = keycloak_base
        self.realm = realm
        self.client_id = client_id
        self.client_secret = client_secret
        self.transport = transport or QgsTransport()
        self.leeway = leeway
        self.timeout = timeout
        self._token = None
        self._expires_at = 0.0

    def token_url(self):
        return "{0}/realms/{1}/protocol/openid-connect/token".format(
            self.keycloak_base.rstrip("/"), self.realm
        )

    def get_token(self):
        """Return a valid access token, re-fetching if expired/near expiry."""
        now = time.time()
        if self._token and now < (self._expires_at - self.leeway):
            return self._token
        self._fetch()
        return self._token

    def invalidate(self):
        """Drop the cached token so the next get_token() re-fetches."""
        self._token = None
        self._expires_at = 0.0

    def _fetch(self):
        body = urlencode(
            {
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            }
        ).encode("utf-8")
        headers = {"Content-Type": "application/x-www-form-urlencoded"}

        resp = self.transport.send("POST", self.token_url(), headers, body, self.timeout)

        if resp.error is not None:
            raise TractAuthError(
                "Could not reach Keycloak: {0}".format(resp.error), status=None
            )
        if resp.status == 401 or resp.status == 400:
            raise TractAuthError(
                "Keycloak rejected the client credentials ({0}){1}. Check the client "
                "id and secret in TRACT Connection Settings.".format(
                    resp.status, _keycloak_error_detail(resp)),
                status=resp.status,
            )
        if resp.status != 200:
            raise TractAuthError(
                "Unexpected Keycloak response ({0}).{1}".format(
                    resp.status, _response_detail(resp)),
                status=resp.status,
            )

        try:
            payload = resp.json()
        except (ValueError, AttributeError) as exc:
            raise TractAuthError("Malformed token response from Keycloak: {0}".format(exc))

        token = payload.get("access_token")
        if not token:
            raise TractAuthError("Keycloak response did not include an access_token.")

        self._token = token
        # Default 5 min if expires_in is absent; leeway handles clock skew.
        self._expires_at = time.time() + int(payload.get("expires_in", 300))


# ---------------------------------------------------------------------------
# Client interface — UI/tasks depend only on this ABC (spec §3).
# ---------------------------------------------------------------------------
class TractClient(ABC):
    """Abstract TRACT client. Concrete impls: TractHttpClient, MockTractClient."""

    @abstractmethod
    def test_connection(self):
        """Return True if Keycloak auth + a basic TRACT call both succeed;
        raise TractAuthError / TractTransportError otherwise (so the UI can show
        distinct messages)."""

    # --- Send ---
    @abstractmethod
    def create_upload(self, filename):
        """POST /v3/files/data-uploads for one filename -> UploadTicket."""

    @abstractmethod
    def put_bytes(self, transfer_url, data):
        """Transfer bytes to the minted URL (resolve_transfer first)."""

    @abstractmethod
    def get_status(self, file_id):
        """GET /v3/files/statuses?filter[ids]=<file_id> -> FileStatus."""

    # --- Receive ---
    @abstractmethod
    def create_download(self, filename, bucket_type):
        """GET /v3/files/signed-url for one filename -> transfer URL (str)."""

    @abstractmethod
    def get_bytes(self, transfer_url):
        """Fetch bytes from the minted URL (resolve_transfer first) -> bytes."""


# ---------------------------------------------------------------------------
# Shared implementation — everything except the raw transport.
# ---------------------------------------------------------------------------
class _BaseTractClient(TractClient):
    """All request-shaping + response-mapping logic, transport-agnostic."""

    def __init__(self, base_url, token_provider, transport,
                 bucket_type=TRACT_DATA_FILES_BUCKET_TYPE, timeout=_DEFAULT_TIMEOUT):
        self.base_url = base_url.rstrip("/")
        self.tokens = token_provider
        self.transport = transport
        self.bucket_type = bucket_type
        self.timeout = timeout

    # -- helpers ------------------------------------------------------------
    def _auth_headers(self, extra=None):
        headers = {"Authorization": "Bearer " + self.tokens.get_token()}
        if extra:
            headers.update(extra)
        return headers

    def _call_api(self, method, path, body=None, headers=None):
        """Authenticated TRACT API call. Maps 401 and transport failures; returns
        the HttpResponse for the caller to interpret further (404/400/2xx)."""
        url = self.base_url + path
        resp = self.transport.send(method, url, self._auth_headers(headers), body, self.timeout)
        if resp.error is not None:
            raise TractTransportError(
                "Could not reach TRACT ({0}): {1}".format(path, resp.error)
            )
        if resp.status == 401:
            raise TractAuthError(
                "TRACT rejected the token (401).{0}".format(_response_detail(resp)),
                status=401,
            )
        return resp

    @staticmethod
    def _query(params):
        # urlencode escapes the bracketed filter[...] keys; the server decodes them.
        pairs = []
        for key, value in params:
            pairs.append((key, value))
        return urlencode(pairs)

    # -- connection ---------------------------------------------------------
    def test_connection(self):
        # 1) Keycloak: get_token() raises TractAuthError on bad credentials.
        self.tokens.get_token()
        # 2) TRACT reachability: any authed API response (even a 4xx that isn't
        #    401) proves the host is reachable and the token accepted.
        query = self._query([("filter[ids]", "__connection_test__")])
        resp = self._call_api("GET", "/v3/files/statuses?" + query)
        return resp.status is not None

    # -- send ---------------------------------------------------------------
    def create_upload(self, filename):
        # TRACT wraps the request in a "data" envelope: {"data": {"filenames": [...]}}.
        body = json.dumps({"data": {"filenames": [filename]}}).encode("utf-8")
        resp = self._call_api(
            "POST", "/v3/files/data-uploads", body,
            headers={"Content-Type": "application/json"},
        )
        if resp.status not in (200, 201):
            raise TractTransportError(
                "Unexpected response minting upload ({0}).{1}".format(
                    resp.status, _response_detail(resp)),
                status=resp.status,
            )
        # Response "data" may be a list (batch) or a single object; field names
        # are matched tolerantly (snake_case or camelCase) pending real-API confirm.
        items = resp.json().get("data")
        if isinstance(items, list):
            el = items[0] if items else None
        elif isinstance(items, dict):
            el = items
        else:
            el = None
        if not el:
            raise TractTransportError(
                "Upload mint returned no data.{0}".format(_response_detail(resp)))
        file_id = el.get("file_id") or el.get("fileId") or el.get("id")
        transfer_url = el.get("url") or el.get("signedUrl") or el.get("uploadUrl")
        if not transfer_url:
            raise TractTransportError(
                "Upload mint response had no transfer URL.{0}".format(_response_detail(resp)))
        return UploadTicket(
            file_id=file_id,
            transfer_url=transfer_url,
            bucket_type=el.get("bucket_type", self.bucket_type),
        )

    def put_bytes(self, transfer_url, data):
        url, attach_token = resolve_transfer(transfer_url, self.base_url)
        headers = {"Content-Type": "application/geo+json"}
        if attach_token:
            headers["Authorization"] = "Bearer " + self.tokens.get_token()
        resp = self.transport.send("PUT", url, headers, data, self.timeout)
        if resp.error is not None:
            raise TractTransportError("Upload transfer failed: {0}".format(resp.error))
        if resp.status is None or resp.status >= 400:
            raise TractTransportError(
                "Upload transfer rejected ({0}).{1}".format(
                    resp.status, _response_detail(resp)),
                status=resp.status,
            )

    def get_status(self, file_id):
        query = self._query([("filter[ids]", file_id)])
        resp = self._call_api("GET", "/v3/files/statuses?" + query)
        if resp.status != 200:
            raise TractTransportError(
                "Unexpected status response ({0}).{1}".format(
                    resp.status, _response_detail(resp)),
                status=resp.status,
            )
        data = resp.json().get("data") or []
        # Batch endpoint: pick the element whose id matches ours (spec §2).
        match = next((el for el in data if el.get("id") == file_id), None)
        if match is None:
            if not data:
                raise TractTransportError("Status response contained no entries.")
            match = data[0]
        return FileStatus.from_api(match)

    # -- receive ------------------------------------------------------------
    def create_download(self, filename, bucket_type):
        query = self._query([
            ("filter[bucketType]", bucket_type),
            ("filter[filenames]", filename),
        ])
        resp = self._call_api("GET", "/v3/files/signed-url?" + query)
        if resp.status == 404:
            raise TractNotFoundError(
                "No file named {0!r} was found. Check the filename, including its "
                "hash suffix.".format(filename),
                status=404,
            )
        if resp.status == 400:
            # FileBucketUnresolvedError — bucket_type is hardcoded, so this is a bug.
            raise TractError(
                "TRACT could not resolve bucket_type {0!r} (400).{1}".format(
                    bucket_type, _response_detail(resp)),
                status=400,
            )
        if resp.status != 200:
            raise TractTransportError(
                "Unexpected signed-url response ({0}).{1}".format(
                    resp.status, _response_detail(resp)),
                status=resp.status,
            )
        data = resp.json().get("data") or []
        if not data or not data[0].get("url"):
            raise TractTransportError("signed-url returned no transfer URL.")
        return data[0]["url"]

    def get_bytes(self, transfer_url):
        url, attach_token = resolve_transfer(transfer_url, self.base_url)
        headers = {}
        if attach_token:
            headers["Authorization"] = "Bearer " + self.tokens.get_token()
        resp = self.transport.send("GET", url, headers, None, self.timeout)
        if resp.error is not None:
            raise TractTransportError("Download transfer failed: {0}".format(resp.error))
        if resp.status == 404:
            # Interim not-found detection until signed-url 404 lands (spec §4.A).
            raise TractNotFoundError("The requested file could not be fetched (404).", status=404)
        if resp.status is None or resp.status >= 400:
            raise TractTransportError(
                "Download transfer failed ({0}).{1}".format(
                    resp.status, _response_detail(resp)),
                status=resp.status,
            )
        return resp.content


class TractHttpClient(_BaseTractClient):
    """Real client — QGIS network stack. Use against the actual TRACT API."""

    def __init__(self, base_url, keycloak_base, realm, client_id, client_secret,
                 bucket_type=TRACT_DATA_FILES_BUCKET_TYPE, timeout=_DEFAULT_TIMEOUT):
        transport = QgsTransport()
        tokens = KeycloakTokenProvider(
            keycloak_base, realm, client_id, client_secret,
            transport=transport, timeout=timeout,
        )
        super().__init__(base_url, tokens, transport, bucket_type, timeout)


class MockTractClient(_BaseTractClient):
    """Dev client — stdlib urllib, points at the local mock server (§7). No QGIS."""

    def __init__(self, base_url, keycloak_base, realm, client_id, client_secret,
                 bucket_type=TRACT_DATA_FILES_BUCKET_TYPE, timeout=_DEFAULT_TIMEOUT):
        transport = UrllibTransport()
        tokens = KeycloakTokenProvider(
            keycloak_base, realm, client_id, client_secret,
            transport=transport, timeout=timeout,
        )
        super().__init__(base_url, tokens, transport, bucket_type, timeout)


def build_client(base_url, keycloak_base, realm, client_id, client_secret,
                 use_mock=False, bucket_type=TRACT_DATA_FILES_BUCKET_TYPE,
                 timeout=_DEFAULT_TIMEOUT):
    """Factory: return a MockTractClient when use_mock is set, else a real one."""
    cls = MockTractClient if use_mock else TractHttpClient
    return cls(base_url, keycloak_base, realm, client_id, client_secret,
               bucket_type=bucket_type, timeout=timeout)
