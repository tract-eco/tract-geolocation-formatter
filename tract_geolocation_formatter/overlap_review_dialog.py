# -*- coding: utf-8 -*-
"""
Review dialog for overlaps between plots (GH-12 FR-5, categories B and C).

Qt only (via ``qgis.PyQt``), no plugin state: the caller passes the findings,
plot info and NodeID counts, and reads plain dicts back from ``results()``.
Nothing is changed unless the user presses **Apply**; **Skip fixes** is the
default button and Escape rejects.

Manual check from the QGIS Python console::

    from shapely.geometry import box
    from tract_geolocation_formatter.overlaps import Finding
    from tract_geolocation_formatter.overlap_review_dialog import OverlapReviewDialog
    f = [
        Finding(0, 1, "B", "partial", None, None, box(0, 0, 1, 1), 50.0, 5.0, False),
        Finding(2, 3, "B", "containment", 2, 3, box(0, 0, 1, 1), 10.0, 100.0, False),
        Finding(4, 5, "C", "containment", 4, 5, box(0, 0, 1, 1), 10.0, 100.0, False),
        Finding(6, 7, "C", "partial", None, None, box(0, 0, 1, 1), 20.0, 2.0, False),
        Finding(8, 9, "C", "partial", None, None, box(0, 0, 1, 1), 90.0, 9.0, False),
    ]
    plots = {i: {"label": "Plot %d" % i, "node_id": n, "area": 1000.0 + i}
             for i, n in enumerate("AABBCDEFGH")}
    counts = {n: list("AABBCDEFGH").count(n) for n in set("AABBCDEFGH")}
    d = OverlapReviewDialog(f, plots, counts)
    d.exec(); print(d.result(), d.results())
"""

from qgis.PyQt.QtCore import QCoreApplication, Qt
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QStyle,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from .overlaps import (
    CATEGORY_CROSS_NODE,
    CATEGORY_SAME_NODE,
    KIND_PARTIAL,
    would_remove_last_plot,
)

DELETE_CONTAINED = "delete_contained"
DELETE_CONTAINER = "delete_container"
KEEP = "keep"
REMOVE_FROM_A = "remove_from_a"
REMOVE_FROM_B = "remove_from_b"

_BULK_NONE = ""
_BULK_KEEP = "keep"
_BULK_SMALLER = "smaller"
_BULK_LARGER = "larger"


def _tr(message):
    return QCoreApplication.translate("OverlapReviewDialog", message)


def is_fixable(finding):
    """Findings the dialog offers an action for (spec FR-5)."""
    return not finding.below_threshold and finding.category in (
        CATEGORY_SAME_NODE,
        CATEGORY_CROSS_NODE,
    )


class OverlapReviewDialog(QDialog):
    """Modal review of fixable B/C overlaps.

    ``findings``: ``overlaps.Finding`` list (below-threshold ones are ignored).
    ``plots``: ``{index: {"label": str, "node_id": str, "area": float m²}}`` for
    every plot referenced by a finding. ``node_counts``: ``{NodeID: number of
    plots in the output}`` (used for the last-plot warning).
    """

    def __init__(self, findings, plots, node_counts, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_tr("Review polygon overlaps"))
        self.setModal(True)
        self.resize(960, 640)

        self._plots = plots
        self._node_counts = dict(node_counts)
        self._node_ids = {idx: info.get("node_id") for idx, info in plots.items()}

        fixable = [f for f in findings if is_fixable(f)]
        self._same_partial = sorted(
            (f for f in fixable if f.category == CATEGORY_SAME_NODE and f.kind == KIND_PARTIAL),
            key=lambda f: (-f.pct_of_smaller, f.index_a, f.index_b),
        )
        self._containment = [f for f in fixable if f.kind != KIND_PARTIAL]
        self._cross_partial = sorted(
            (f for f in fixable if f.category == CATEGORY_CROSS_NODE and f.kind == KIND_PARTIAL),
            key=lambda f: (-f.pct_of_smaller, f.index_a, f.index_b),
        )
        self._containment_combos = []
        self._same_combos = []
        self._cross_combos = []

        layout = QVBoxLayout(self)

        # 1. Containment / identical.
        containment_header = QHBoxLayout()
        self.containmentLabel = QLabel(_tr("Contained plots"))
        self.containmentBulkCombo = QComboBox()
        self.containmentBulkCombo.addItem(_tr("Set all to: —"), _BULK_NONE)
        self.containmentBulkCombo.addItem(_tr("Delete contained"), DELETE_CONTAINED)
        self.containmentBulkCombo.addItem(_tr("Delete container"), DELETE_CONTAINER)
        self.containmentBulkCombo.addItem(_tr("Keep both"), KEEP)
        self.containmentBulkCombo.currentIndexChanged.connect(
            self._apply_bulk_containment_action
        )
        containment_header.addWidget(self.containmentLabel)
        containment_header.addStretch(1)
        containment_header.addWidget(self.containmentBulkCombo)
        self.containmentTable = self._make_table(
            [
                _tr("Contained"),
                _tr("NodeID"),
                _tr("Area m²"),
                _tr("Container"),
                _tr("NodeID"),
                _tr("Area m²"),
                _tr("Action"),
            ],
            len(self._containment),
        )
        for row, f in enumerate(self._containment):
            self._fill_plot_cells(self.containmentTable, row, 0, f.contained)
            self._fill_plot_cells(self.containmentTable, row, 3, f.container)
            combo = QComboBox()
            combo.addItem(_tr("Delete contained"), DELETE_CONTAINED)
            combo.addItem(_tr("Delete container"), DELETE_CONTAINER)
            combo.addItem(_tr("Keep both"), KEEP)
            default = DELETE_CONTAINED if f.category == CATEGORY_SAME_NODE else KEEP
            combo.setCurrentIndex(combo.findData(default))
            combo.currentIndexChanged.connect(self._refresh_last_plot_marks)
            self.containmentTable.setCellWidget(row, 6, combo)
            self._containment_combos.append(combo)
        has_containment = bool(self._containment)
        self.containmentLabel.setVisible(has_containment)
        self.containmentBulkCombo.setVisible(has_containment)
        self.containmentTable.setVisible(has_containment)
        layout.addLayout(containment_header)
        layout.addWidget(self.containmentTable)

        # 2. Partial overlaps, same NodeID (default: remove from the smaller plot).
        (self.sameLabel, self.sameBulkCombo, self.sameTable) = self._add_partial_section(
            layout,
            _tr("Partial overlaps within the same NodeID"),
            self._same_partial,
            self._same_combos,
            default_mode=_BULK_SMALLER,
        )

        # 3. Partial overlaps, different NodeIDs (default: keep both).
        (self.crossLabel, self.bulkCombo, self.crossTable) = self._add_partial_section(
            layout,
            _tr("Partial overlaps between different NodeIDs"),
            self._cross_partial,
            self._cross_combos,
            default_mode=_BULK_KEEP,
        )

        # 4. Disclaimer.
        disclaimer = QLabel(
            "<ul>"
            "<li>{0}</li><li>{1}</li><li>{2}</li>"
            "</ul>".format(
                _tr("Clipping and deleting change the plots you submit."),
                _tr("Check the results before uploading."),
                _tr("Keep your source data."),
            )
        )
        disclaimer.setTextFormat(Qt.TextFormat.RichText)
        disclaimer.setWordWrap(True)
        layout.addWidget(disclaimer)

        # 5. Buttons: Skip fixes is the default; Escape rejects (QDialog default).
        self.buttonBox = QDialogButtonBox()
        self.applyButton = self.buttonBox.addButton(
            _tr("Apply"), QDialogButtonBox.ButtonRole.AcceptRole
        )
        self.skipButton = self.buttonBox.addButton(
            _tr("Skip fixes"), QDialogButtonBox.ButtonRole.RejectRole
        )
        self.applyButton.setAutoDefault(False)
        self.skipButton.setDefault(True)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)
        layout.addWidget(self.buttonBox)

        self._refresh_last_plot_marks()

    # ------------------------------------------------------------------ #

    def _make_table(self, headers, rows):
        table = QTableWidget(rows, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        table.horizontalHeader().setStretchLastSection(True)
        return table

    @staticmethod
    def _number_item(text):
        item = QTableWidgetItem(text)
        item.setTextAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        return item

    def _fill_plot_cells(self, table, row, col, index):
        info = self._plots.get(index, {})
        node_id = info.get("node_id")
        table.setItem(row, col, QTableWidgetItem(str(info.get("label", index))))
        table.setItem(row, col + 1, QTableWidgetItem("" if node_id is None else str(node_id)))
        area = info.get("area")
        table.setItem(
            row, col + 2, self._number_item("" if area is None else "{:.2f}".format(area))
        )

    def _containment_target(self, row):
        f = self._containment[row]
        choice = self._containment_combos[row].currentData()
        if choice == DELETE_CONTAINED:
            return f.contained
        if choice == DELETE_CONTAINER:
            return f.container
        return None

    def _refresh_last_plot_marks(self, *_args):
        """Warn on rows whose deletion would empty a NodeID (all rows interact)."""
        targets = {}
        for row in range(len(self._containment)):
            target = self._containment_target(row)
            if target is not None:
                targets[row] = target
        marked = would_remove_last_plot(
            self._node_counts, self._node_ids, set(targets.values())
        )
        warning = self.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxWarning)
        for row in range(len(self._containment)):
            item = self.containmentTable.item(row, 0)
            target = targets.get(row)
            if target is not None and target in marked:
                node_id = self._node_ids.get(target)
                item.setIcon(warning)
                item.setToolTip(
                    _tr("This deletion removes the last plot of NodeID {0}.").format(
                        "" if node_id is None else node_id
                    )
                )
            else:
                item.setIcon(QIcon())
                item.setToolTip("")

    def _apply_bulk_containment_action(self, *_args):
        """Set every containment row from the bulk control; rows stay editable."""
        choice = self.containmentBulkCombo.currentData()
        if not choice:
            return
        for combo in self._containment_combos:
            # Signals off: the last-plot marks are refreshed once, below.
            combo.blockSignals(True)
            combo.setCurrentIndex(combo.findData(choice))
            combo.blockSignals(False)
        self._refresh_last_plot_marks()
        # Back to "—" so a later bulk choice of the same value applies again.
        self.containmentBulkCombo.blockSignals(True)
        self.containmentBulkCombo.setCurrentIndex(0)
        self.containmentBulkCombo.blockSignals(False)

    def _add_partial_section(self, layout, title, findings, combos, default_mode):
        """Header (label + "Set all to") and table for one list of partial overlaps."""
        header = QHBoxLayout()
        label = QLabel(title)
        bulk = QComboBox()
        bulk.addItem(_tr("Set all to: —"), _BULK_NONE)
        bulk.addItem(_tr("Keep both"), _BULK_KEEP)
        bulk.addItem(_tr("Remove from smaller"), _BULK_SMALLER)
        bulk.addItem(_tr("Remove from larger"), _BULK_LARGER)
        header.addWidget(label)
        header.addStretch(1)
        header.addWidget(bulk)

        table = self._make_table(
            [
                _tr("Plot A"),
                _tr("NodeID"),
                _tr("Area m²"),
                _tr("Plot B"),
                _tr("NodeID"),
                _tr("Area m²"),
                _tr("Overlap m²"),
                _tr("% of smaller"),
                _tr("Action"),
            ],
            len(findings),
        )
        for row, f in enumerate(findings):
            self._fill_plot_cells(table, row, 0, f.index_a)
            self._fill_plot_cells(table, row, 3, f.index_b)
            table.setItem(row, 6, self._number_item("{:.2f}".format(f.area)))
            table.setItem(row, 7, self._number_item("{:.2f}".format(f.pct_of_smaller)))
            combo = QComboBox()
            combo.addItem(_tr("Keep both"), KEEP)
            combo.addItem(_tr("Remove overlap from A"), REMOVE_FROM_A)
            combo.addItem(_tr("Remove overlap from B"), REMOVE_FROM_B)
            combo.setCurrentIndex(combo.findData(self._partial_choice(f, default_mode)))
            table.setCellWidget(row, 8, combo)
            combos.append(combo)

        bulk.currentIndexChanged.connect(
            lambda _i, b=bulk, fs=findings, cs=combos: self._apply_bulk_partial_action(b, fs, cs)
        )
        has_rows = bool(findings)
        label.setVisible(has_rows)
        bulk.setVisible(has_rows)
        table.setVisible(has_rows)
        layout.addLayout(header)
        layout.addWidget(table)
        return label, bulk, table

    def _partial_choice(self, f, mode):
        """Row action for a bulk mode: keep, or remove from the smaller/larger plot."""
        if mode == _BULK_KEEP:
            return KEEP
        area_a = self._plots.get(f.index_a, {}).get("area") or 0.0
        area_b = self._plots.get(f.index_b, {}).get("area") or 0.0
        a_is_smaller = area_a < area_b or (area_a == area_b and f.index_a > f.index_b)
        remove_from_a = a_is_smaller if mode == _BULK_SMALLER else not a_is_smaller
        return REMOVE_FROM_A if remove_from_a else REMOVE_FROM_B

    def _apply_bulk_partial_action(self, bulk, findings, combos):
        """Set every row of one partial table from its bulk control; rows stay editable."""
        mode = bulk.currentData()
        if not mode:
            return
        for f, combo in zip(findings, combos):
            combo.setCurrentIndex(combo.findData(self._partial_choice(f, mode)))
        # Back to "—" so a later bulk choice of the same value applies again.
        bulk.blockSignals(True)
        bulk.setCurrentIndex(0)
        bulk.blockSignals(False)

    # ------------------------------------------------------------------ #

    def results(self):
        """``(same_node_actions, containment_actions, cross_node_actions)``.

        Action dicts are keyed by ``(index_a, index_b)``.
        """
        same_node_actions = {
            (f.index_a, f.index_b): self._same_combos[row].currentData()
            for row, f in enumerate(self._same_partial)
        }
        containment_actions = {
            (f.index_a, f.index_b): self._containment_combos[row].currentData()
            for row, f in enumerate(self._containment)
        }
        cross_node_actions = {
            (f.index_a, f.index_b): self._cross_combos[row].currentData()
            for row, f in enumerate(self._cross_partial)
        }
        return same_node_actions, containment_actions, cross_node_actions
