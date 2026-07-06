#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Local mock of Keycloak + the TRACT file API + the byte-transfer endpoint.

Dev fixture for SPEC-tract-integration Work Item 4 — NOT packaged with the
plugin (lives under dev/, outside tract_geolocation_formatter/). It lets the
whole Send/Receive integration be exercised end-to-end before the real TRACT
endpoints are reachable.

Run:
    python3 dev/mock_tract_server.py            # http://127.0.0.1:8787
    python3 dev/mock_tract_server.py --port 9000
    python3 dev/mock_tract_server.py --shape absolute   # default transfer URL shape

Endpoints (stdlib http.server only, no third-party deps):
    POST /realms/{realm}/protocol/openid-connect/token   fake Keycloak
    POST /v3/files/data-uploads                           mint upload transfer URL + file_id
    GET  /v3/files/statuses?filter[ids]=...               batch ingestion status
    GET  /v3/files/signed-url?filter[bucketType]=...&filter[filenames]=...
    PUT  /transfer/{id}                                   accept uploaded bytes
    GET  /transfer/{id}                                   serve bytes (seeded for download)

Shape rule (spec §2): the transfer URL is served **relative** (``/transfer/..``)
by default so the client's resolve_transfer + bearer-attach path is tested;
pass ``--shape absolute`` (or ``?shape=absolute`` on a mint call) to serve an
absolute ``http://<host>:<port>/transfer/..`` URL so the as-is/no-bearer branch
is tested too.

Seeded fixtures:
    GOOD_DOWNLOAD    - a dirty GeoJSON (self-intersecting) with NodeID/PlotID, so
                       receive -> validate -> fix works end-to-end.
    BROKEN_DOWNLOAD  - signed-url succeeds but the transfer GET fails (500), to
                       exercise the interim not-found fallback (§4.A).
    filenames starting with "bad" upload fine but ingest to staticValidationFailed
                       with a non-empty errorReportName.
"""

import argparse
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

# --- credentials the fake Keycloak accepts ---
CLIENT_ID = "test-client"
CLIENT_SECRET = "test-secret"
TOKEN_TTL_SECONDS = 300

# --- how many status polls return "processing" before a terminal state ---
PROCESSING_POLLS = 2

# --- seeded download filenames (full stored name incl. hash suffix, per spec §2) ---
GOOD_DOWNLOAD = "hungary_5f8010d6c2848bdc331c56c9a9bee9fb.geojson"
BROKEN_DOWNLOAD = "brokenfetch_0000000000000000000000000000dead.geojson"

# A deliberately dirty FeatureCollection: the first ring is a self-intersecting
# "bowtie", which the plugin's existing validation flags. EPSG:4326.
DIRTY_GEOJSON = {
    "type": "FeatureCollection",
    "name": "hungary_sample",
    "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}},
    "features": [
        {
            "type": "Feature",
            "properties": {"NodeID": "NODE_1", "PlotID": "PLOT_1", "geoId": "geo-abc"},
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [19.0000, 47.0000],
                    [19.0020, 47.0020],
                    [19.0020, 47.0000],
                    [19.0000, 47.0020],
                    [19.0000, 47.0000],
                ]],
            },
        },
        {
            "type": "Feature",
            "properties": {"NodeID": "NODE_2", "PlotID": "PLOT_2", "geoId": "geo-def"},
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [19.0100, 47.0100],
                    [19.0130, 47.0100],
                    [19.0130, 47.0130],
                    [19.0100, 47.0130],
                    [19.0100, 47.0100],
                ]],
            },
        },
    ],
}


class MockState:
    """Shared, thread-safe-ish server state (guarded by a single lock)."""

    def __init__(self, host, port, default_shape):
        self.host = host
        self.port = port
        self.default_shape = default_shape  # "relative" | "absolute"
        self.lock = threading.Lock()
        self.issued_tokens = set()
        self.uploads = {}            # file_id -> {filename, will_fail, poll_count, bytes}
        self.upload_transfers = {}   # transfer_id -> file_id
        self.download_transfers = {}  # transfer_id -> filename
        self._counter = 0

    def next_id(self, prefix):
        self._counter += 1
        return "{0}-{1}".format(prefix, self._counter)

    def transfer_url(self, transfer_id, shape):
        rel = "/transfer/{0}".format(transfer_id)
        if shape == "absolute":
            return "http://{0}:{1}{2}".format(self.host, self.port, rel)
        return rel


class Handler(BaseHTTPRequestHandler):
    # set as a class attribute by make_server()
    state = None

    # --- small response helpers -------------------------------------------
    def _json(self, status, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _raw(self, status, data, content_type="application/geo+json"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _error(self, status, code, message):
        self._json(status, {"error": {"code": code, "message": message}})

    def _body(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        return self.rfile.read(length) if length else b""

    def _bearer(self):
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            return auth[len("Bearer "):]
        return None

    def _require_token(self):
        """Return True if a valid bearer is present; else emit 401 and return False."""
        token = self._bearer()
        with self.state.lock:
            valid = token is not None and token in self.state.issued_tokens
        if not valid:
            self._error(401, "Unauthorized", "Missing or invalid bearer token.")
            return False
        return True

    def _shape(self, query):
        vals = query.get("shape")
        if vals and vals[0] in ("relative", "absolute"):
            return vals[0]
        return self.state.default_shape

    # keep the console quiet-ish; comment out to debug
    def log_message(self, fmt, *args):
        return

    # --- routing -----------------------------------------------------------
    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path.endswith("/protocol/openid-connect/token"):
            return self._handle_token()
        if path == "/v3/files/data-uploads":
            return self._handle_data_uploads(parse_qs(parsed.query))
        self._error(404, "NotFound", "No such endpoint: {0}".format(path))

    def do_PUT(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith("/transfer/"):
            return self._handle_transfer_put(parsed.path.split("/transfer/", 1)[1])
        self._error(404, "NotFound", "No such endpoint: {0}".format(parsed.path))

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        if path == "/v3/files/statuses":
            return self._handle_statuses(query)
        if path == "/v3/files/signed-url":
            return self._handle_signed_url(query)
        if path.startswith("/transfer/"):
            return self._handle_transfer_get(path.split("/transfer/", 1)[1])
        self._error(404, "NotFound", "No such endpoint: {0}".format(path))

    # --- Keycloak ----------------------------------------------------------
    def _handle_token(self):
        raw = self._body().decode("utf-8")
        form = parse_qs(raw)

        def one(key):
            vals = form.get(key)
            return vals[0] if vals else None

        if one("grant_type") != "client_credentials":
            return self._error(400, "InvalidGrant", "grant_type must be client_credentials.")
        if one("client_id") != CLIENT_ID or one("client_secret") != CLIENT_SECRET:
            return self._error(401, "InvalidClient", "Bad client credentials.")

        token = self.state.next_id("token")
        with self.state.lock:
            self.state.issued_tokens.add(token)
        self._json(200, {
            "access_token": token,
            "expires_in": TOKEN_TTL_SECONDS,
            "token_type": "Bearer",
        })

    # --- Send: mint upload transfer URL + file_id --------------------------
    def _handle_data_uploads(self, query):
        if not self._require_token():
            return
        try:
            payload = json.loads(self._body().decode("utf-8") or "{}")
        except ValueError:
            return self._error(400, "BadRequest", "Body must be JSON.")
        filenames = payload.get("filenames") or []
        if not filenames:
            return self._error(400, "FileBatchEmptyError", "No filenames supplied.")

        shape = self._shape(query)
        data = []
        with self.state.lock:
            for filename in filenames:
                file_id = self.state.next_id("file")
                transfer_id = self.state.next_id("up")
                self.state.upload_transfers[transfer_id] = file_id
                self.state.uploads[file_id] = {
                    "filename": filename,
                    # filenames starting with "bad" ingest to staticValidationFailed
                    "will_fail": str(filename).lower().startswith("bad"),
                    "poll_count": 0,
                    "bytes": None,
                }
                data.append({
                    "file_id": file_id,
                    "filename": filename,
                    "bucket_type": "data_files",
                    "url": self.state.transfer_url(transfer_id, shape),
                })
        # 201 Created, V3ObjectResponse[list[SignedUrl]] shape
        self._json(201, {"data": data})

    # --- Send: batch status ------------------------------------------------
    def _handle_statuses(self, query):
        if not self._require_token():
            return
        ids = query.get("filter[ids]") or []
        if not ids:
            return self._error(400, "FileBatchEmptyError", "No filter[ids] supplied.")

        data = []
        with self.state.lock:
            for file_id in ids:
                rec = self.state.uploads.get(file_id)
                if rec is None:
                    # Unknown id: report a neutral pending-ish status.
                    data.append({"id": file_id, "fileStatus": "unknown", "errorReportName": None})
                    continue
                rec["poll_count"] += 1
                if rec["poll_count"] <= PROCESSING_POLLS:
                    data.append({"id": file_id, "fileStatus": "processing", "errorReportName": None})
                elif rec["will_fail"]:
                    data.append({
                        "id": file_id,
                        "fileStatus": "staticValidationFailed",
                        "errorReportName": "error_report_{0}.csv".format(file_id),
                    })
                else:
                    data.append({"id": file_id, "fileStatus": "completed", "errorReportName": None})
        self._json(200, {"data": data})

    # --- Receive: mint download transfer URL -------------------------------
    def _handle_signed_url(self, query):
        if not self._require_token():
            return
        bucket = (query.get("filter[bucketType]") or [None])[0]
        if bucket != "data_files":
            # FileBucketUnresolvedError (spec §2)
            return self._error(400, "FileBucketUnresolvedError",
                               "Unresolvable bucket_type: {0!r}".format(bucket))
        filenames = query.get("filter[filenames]") or []
        if not filenames:
            return self._error(400, "FileBatchEmptyError", "No filter[filenames] supplied.")

        shape = self._shape(query)
        data = []
        with self.state.lock:
            for filename in filenames:
                if filename not in (GOOD_DOWNLOAD, BROKEN_DOWNLOAD):
                    # Eng prerequisite (§4.A): unknown filename -> 404.
                    return self._error(404, "FileNotFound",
                                       "No file named {0!r} in data_files.".format(filename))
                transfer_id = self.state.next_id("down")
                self.state.download_transfers[transfer_id] = filename
                data.append({
                    "filename": filename,
                    "url": self.state.transfer_url(transfer_id, shape),
                })
        self._json(200, {"data": data})

    # --- byte transfer -----------------------------------------------------
    def _handle_transfer_put(self, transfer_id):
        with self.state.lock:
            file_id = self.state.upload_transfers.get(transfer_id)
            if file_id is None:
                self._error(404, "NotFound", "Unknown upload transfer id.")
                return
            self.state.uploads[file_id]["bytes"] = self._body()
        # A signed PUT typically returns 200/201 with no meaningful body.
        self._raw(200, b"", content_type="text/plain")

    def _handle_transfer_get(self, transfer_id):
        with self.state.lock:
            filename = self.state.download_transfers.get(transfer_id)
        if filename is None:
            return self._error(404, "NotFound", "Unknown download transfer id.")
        if filename == BROKEN_DOWNLOAD:
            # Signed-url succeeded but the transfer fetch fails: exercises the
            # interim failed-transfer fallback (§4.A).
            return self._error(500, "TransferFailed", "Simulated transfer failure.")
        body = json.dumps(DIRTY_GEOJSON).encode("utf-8")
        self._raw(200, body, content_type="application/geo+json")


def make_server(host, port, default_shape):
    state = MockState(host, port, default_shape)

    class BoundHandler(Handler):
        pass

    BoundHandler.state = state
    httpd = ThreadingHTTPServer((host, port), BoundHandler)
    # Reflect the actually-bound port (matters when port=0 is requested) so
    # absolute transfer URLs point at the real listening port.
    state.port = httpd.server_address[1]
    return httpd, state


def main():
    parser = argparse.ArgumentParser(description="Mock TRACT + Keycloak server (dev fixture).")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--shape", choices=("relative", "absolute"), default="relative",
                        help="default transfer URL shape (override per-call with ?shape=).")
    args = parser.parse_args()

    httpd, _state = make_server(args.host, args.port, args.shape)
    print("Mock TRACT server on http://{0}:{1}  (default transfer shape: {2})".format(
        args.host, args.port, args.shape))
    print("  client_id={0} client_secret={1}".format(CLIENT_ID, CLIENT_SECRET))
    print("  good download filename : {0}".format(GOOD_DOWNLOAD))
    print("  broken-fetch filename  : {0}".format(BROKEN_DOWNLOAD))
    print("  upload a filename starting with 'bad' to get staticValidationFailed")
    print("Ctrl-C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        httpd.shutdown()


if __name__ == "__main__":
    main()
