# -*- coding: utf-8 -*-
"""
Background tasks for the TRACT integration (SPEC-tract-integration, WI-2 & WI-3).

Both tasks subclass ``QgsTask`` so all networking runs off the UI thread.
``run()`` does only network + data work (safe in a worker thread via
``QgsBlockingNetworkRequest``); it never touches the QGIS project or widgets.
``finished()`` runs back on the main thread and invokes the ``on_finished``
callback supplied by the plugin, which does all UI / layer work there.
"""

import time

from qgis.core import QgsTask

from .tract_client import (
    TRACT_DATA_FILES_BUCKET_TYPE,
    TractAuthError,
    TractError,
)

# Short-poll cadence with a hard ceiling (spec §6) — never spin forever.
POLL_INTERVAL_SECONDS = 3
POLL_CAP_SECONDS = 120


class UploadTask(QgsTask):
    """Send one or more GeoJSON files: per file, mint -> PUT -> short-poll status.

    ``files`` is a list of ``(filename, data_bytes)``. Each file is uploaded
    sequentially and its per-file outcome recorded in ``self.results``. An auth
    failure aborts the whole batch (credentials are broken); any other per-file
    error is recorded and the batch continues.
    """

    OUTCOME_COMPLETED = "completed"
    OUTCOME_VALIDATION_FAILED = "validation_failed"
    OUTCOME_TIMEOUT = "timeout"
    OUTCOME_ERROR = "error"

    def __init__(self, client, files, on_finished=None,
                 poll_interval=POLL_INTERVAL_SECONDS, poll_cap=POLL_CAP_SECONDS):
        super().__init__("Send {0} file(s) to TRACT".format(len(files)))
        self.client = client
        self.files = files
        self._on_finished = on_finished
        self.poll_interval = poll_interval
        self.poll_cap = poll_cap
        # Read by the finished callback (main thread):
        self.results = []          # list of {filename, outcome, error_report_name, error}
        self.fatal_error = None     # set on an aborting failure (e.g. auth)
        self.fatal_error_kind = None

    def run(self):
        for filename, data in self.files:
            if self.isCanceled():
                return False
            try:
                self.results.append(self._upload_one(filename, data))
            except TractAuthError as exc:
                # Credentials are broken — no point continuing the batch.
                self.fatal_error = str(exc)
                self.fatal_error_kind = "TractAuthError"
                return False
            except TractError as exc:
                self.results.append({
                    "filename": filename, "outcome": self.OUTCOME_ERROR,
                    "error_report_name": "", "error": str(exc)})
            except Exception as exc:  # defensive — record and keep going
                self.results.append({
                    "filename": filename, "outcome": self.OUTCOME_ERROR,
                    "error_report_name": "", "error": str(exc)})
        return True

    def _upload_one(self, filename, data):
        ticket = self.client.create_upload(filename)
        self.client.put_bytes(ticket.transfer_url, data)

        elapsed = 0
        status = None
        while elapsed <= self.poll_cap:
            if self.isCanceled():
                break
            status = self.client.get_status(ticket.file_id)
            if status.is_terminal:
                break
            time.sleep(self.poll_interval)
            elapsed += self.poll_interval

        if status is None or not status.is_terminal:
            outcome, report = self.OUTCOME_TIMEOUT, ""
        elif status.is_success:
            outcome, report = self.OUTCOME_COMPLETED, ""
        else:
            outcome, report = self.OUTCOME_VALIDATION_FAILED, status.error_report_name
        return {"filename": filename, "outcome": outcome,
                "error_report_name": report, "error": None}

    def finished(self, result):
        # Runs on the main thread (QGIS guarantee) — safe to touch UI from the cb.
        if self._on_finished is not None:
            self._on_finished(self, result)


class DownloadTask(QgsTask):
    """Receive: mint signed download URL -> GET bytes (raw GeoJSON)."""

    def __init__(self, client, filename, on_finished=None,
                 bucket_type=TRACT_DATA_FILES_BUCKET_TYPE):
        super().__init__("Download {0} from TRACT".format(filename))
        self.client = client
        self.filename = filename
        self._on_finished = on_finished
        self.bucket_type = bucket_type
        # Results read by the finished callback (main thread):
        self.data = None
        self.error = None
        self.error_kind = None

    def run(self):
        try:
            url = self.client.create_download(self.filename, self.bucket_type)
            self.data = self.client.get_bytes(url)
            return True
        except TractError as exc:
            self.error = str(exc)
            self.error_kind = type(exc).__name__
            return False
        except Exception as exc:  # defensive
            self.error = str(exc)
            self.error_kind = "Exception"
            return False

    def finished(self, result):
        if self._on_finished is not None:
            self._on_finished(self, result)
