# -*- coding: utf-8 -*-
"""
TRACT connection & authentication settings (SPEC-tract-integration, Work Item 1).

Persists the TRACT API base URL + Keycloak config in ``QgsSettings`` (not secret)
and the Keycloak ``client_secret`` in the encrypted QGIS auth DB via
``QgsAuthManager`` — only the auth-config id is kept in ``QgsSettings``. The
``bucket_type`` is not user-configurable; it is the hardcoded
``TRACT_DATA_FILES_BUCKET_TYPE`` constant.

Constitution §7 (amended 2026-07-06): no secret is written to QgsSettings in
plaintext — the client_secret lives only in the auth DB.
"""

from qgis.PyQt.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)
from qgis.core import (
    QgsApplication,
    QgsAuthMethodConfig,
    QgsSettings,
)

from .tract_client import (
    TractAuthError,
    TractError,
    TractTransportError,
    build_client,
)


# QgsSettings keys (spec §5). None of these hold a secret.
_PREFIX = "TRACTGeolocationFormatter/tract"
KEY_BASE_URL = _PREFIX + "/base_url"
KEY_KEYCLOAK_BASE = _PREFIX + "/keycloak_base"
KEY_REALM = _PREFIX + "/realm"
KEY_CLIENT_ID = _PREFIX + "/client_id"
KEY_AUTHCFG = _PREFIX + "/authcfg"
KEY_USE_MOCK = _PREFIX + "/use_mock"

# Name attached to the stored auth config, for recognizability in the QGIS UI.
_AUTHCFG_NAME = "TRACT Geolocation Formatter"


def load_connection_settings():
    """Read the non-secret connection settings into a dict."""
    s = QgsSettings()
    return {
        "base_url": s.value(KEY_BASE_URL, "", type=str),
        "keycloak_base": s.value(KEY_KEYCLOAK_BASE, "", type=str),
        "realm": s.value(KEY_REALM, "", type=str),
        "client_id": s.value(KEY_CLIENT_ID, "", type=str),
        "authcfg": s.value(KEY_AUTHCFG, "", type=str),
        "use_mock": s.value(KEY_USE_MOCK, False, type=bool),
    }


def load_client_secret(authcfg):
    """Load the client_secret from the auth DB for the given auth-config id."""
    if not authcfg:
        return ""
    cfg = QgsAuthMethodConfig()
    ok = QgsApplication.authManager().loadAuthenticationConfig(authcfg, cfg, True)
    if not ok:
        return ""
    return cfg.config("password", "")


def _store_client_secret(authcfg, client_id, secret):
    """Create or update the Basic auth config holding the secret; return its id."""
    auth_mgr = QgsApplication.authManager()
    cfg = QgsAuthMethodConfig()
    if authcfg and auth_mgr.loadAuthenticationConfig(authcfg, cfg, True):
        # Update the existing config in place.
        cfg.setName(_AUTHCFG_NAME)
        cfg.setMethod("Basic")
        cfg.setConfig("username", client_id)
        cfg.setConfig("password", secret)
        auth_mgr.updateAuthenticationConfig(cfg)
        return cfg.id()
    # Create a fresh config; storeAuthenticationConfig populates cfg.id().
    cfg = QgsAuthMethodConfig()
    cfg.setName(_AUTHCFG_NAME)
    cfg.setMethod("Basic")
    cfg.setConfig("username", client_id)
    cfg.setConfig("password", secret)
    auth_mgr.storeAuthenticationConfig(cfg)
    return cfg.id()


def build_client_from_settings():
    """Build a TractClient from stored settings (secret pulled from the auth DB).

    Returns None if the essential settings are not configured yet.
    """
    cfg = load_connection_settings()
    if not (cfg["base_url"] and cfg["keycloak_base"] and cfg["realm"] and cfg["client_id"]):
        return None
    secret = load_client_secret(cfg["authcfg"])
    return build_client(
        cfg["base_url"], cfg["keycloak_base"], cfg["realm"], cfg["client_id"], secret,
        use_mock=cfg["use_mock"],
    )


class TractConnectionDialog(QDialog):
    """Dialog to configure and test the TRACT connection."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("TRACT Connection Settings"))
        self.setMinimumWidth(480)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.base_url_edit = QLineEdit()
        self.base_url_edit.setPlaceholderText("https://api.dev.tract.ninja")
        self.keycloak_edit = QLineEdit()
        self.keycloak_edit.setPlaceholderText("https://keycloak-dev.tooling.tract.ninja")
        self.realm_edit = QLineEdit()
        self.client_id_edit = QLineEdit()
        self.client_secret_edit = QLineEdit()
        self.client_secret_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.client_secret_edit.setPlaceholderText(
            self.tr("(unchanged — leave blank to keep the stored secret)")
        )

        form.addRow(self.tr("TRACT API base URL:"), self.base_url_edit)
        form.addRow(self.tr("Keycloak base URL:"), self.keycloak_edit)
        form.addRow(self.tr("Realm:"), self.realm_edit)
        form.addRow(self.tr("Client ID:"), self.client_id_edit)
        form.addRow(self.tr("Client secret:"), self.client_secret_edit)
        layout.addLayout(form)

        # Test connection row + inline result label.
        self.test_button = QPushButton(self.tr("Test connection"))
        self.test_button.clicked.connect(self._on_test_connection)
        layout.addWidget(self.test_button)

        self.result_label = QLabel("")
        self.result_label.setWordWrap(True)
        layout.addWidget(self.result_label)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        self.button_box.accepted.connect(self._on_save)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

        self._authcfg = ""
        self._load_into_fields()

    # -- helpers ------------------------------------------------------------
    def _load_into_fields(self):
        cfg = load_connection_settings()
        self.base_url_edit.setText(cfg["base_url"])
        self.keycloak_edit.setText(cfg["keycloak_base"])
        self.realm_edit.setText(cfg["realm"])
        self.client_id_edit.setText(cfg["client_id"])
        self._authcfg = cfg["authcfg"]
        # The secret field is intentionally left blank — we never display it.
        # use_mock has no UI (dev-only); it is read from settings when present.
        self._use_mock = cfg["use_mock"]

    def _effective_secret(self):
        """Secret to use for a test: the typed value, else the stored one."""
        typed = self.client_secret_edit.text()
        if typed:
            return typed
        return load_client_secret(self._authcfg)

    def _current_client(self):
        return build_client(
            self.base_url_edit.text().strip(),
            self.keycloak_edit.text().strip(),
            self.realm_edit.text().strip(),
            self.client_id_edit.text().strip(),
            self._effective_secret(),
            use_mock=getattr(self, "_use_mock", False),
        )

    def _set_result(self, message, ok):
        color = "#1a7f37" if ok else "#b42318"
        self.result_label.setText(message)
        self.result_label.setStyleSheet("color: {0};".format(color))

    # -- actions ------------------------------------------------------------
    def _on_test_connection(self):
        if not (self.base_url_edit.text().strip() and self.keycloak_edit.text().strip()
                and self.realm_edit.text().strip() and self.client_id_edit.text().strip()):
            self._set_result(
                self.tr("Fill in the base URL, Keycloak URL, realm, and client id first."),
                ok=False,
            )
            return
        self.test_button.setEnabled(False)
        try:
            client = self._current_client()
            client.test_connection()
        except TractAuthError as exc:
            self._set_result(self.tr("Keycloak authentication failed: {0}").format(exc), ok=False)
        except TractTransportError as exc:
            self._set_result(self.tr("Could not reach TRACT: {0}").format(exc), ok=False)
        except TractError as exc:
            self._set_result(self.tr("Connection failed: {0}").format(exc), ok=False)
        except Exception as exc:  # defensive: never let the dialog crash on test
            self._set_result(self.tr("Unexpected error: {0}").format(exc), ok=False)
        else:
            self._set_result(self.tr("Connection OK — Keycloak token obtained and TRACT reachable."), ok=True)
        finally:
            self.test_button.setEnabled(True)

    def _on_save(self):
        s = QgsSettings()
        s.setValue(KEY_BASE_URL, self.base_url_edit.text().strip())
        s.setValue(KEY_KEYCLOAK_BASE, self.keycloak_edit.text().strip())
        s.setValue(KEY_REALM, self.realm_edit.text().strip())
        s.setValue(KEY_CLIENT_ID, self.client_id_edit.text().strip())
        # KEY_USE_MOCK has no UI; leave any existing (dev-set) value untouched.

        # Only touch the auth DB if the user typed a new secret; otherwise keep
        # the existing stored secret. Never write the secret into QgsSettings.
        typed_secret = self.client_secret_edit.text()
        if typed_secret:
            self._authcfg = _store_client_secret(
                self._authcfg, self.client_id_edit.text().strip(), typed_secret
            )
        s.setValue(KEY_AUTHCFG, self._authcfg)

        self.accept()
