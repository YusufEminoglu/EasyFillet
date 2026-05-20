# -*- coding: utf-8 -*-
"""EasyFillet radius dialog.

Modernised over the v1.3 release:
  - QDoubleSpinBox replaces the free-form QLineEdit (no more parse errors).
  - Optional snap-tolerance and arc-segment-count fields surface what was
    previously hard-coded magic.
  - Dialog remembers its last values via QSettings so the second invocation
    inside a session never re-asks for the same number.
"""
from __future__ import annotations

from qgis.PyQt.QtCore import QSettings, Qt
from qgis.PyQt.QtGui import QFont
from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QSpinBox,
    QVBoxLayout,
)


_SETTINGS_PREFIX = "PlanX/EasyFillet"


class EasyFilletDialog(QDialog):
    """Modal parameter dialog for EasyFillet."""

    def __init__(self, parent=None, default_radius: float = 4.0):
        super().__init__(parent)
        self.setWindowTitle("EasyFillet — Parameters")
        self.setModal(True)
        self.setMinimumWidth(320)

        layout = QVBoxLayout(self)

        header = QLabel("⌒ EasyFillet")
        f = QFont()
        f.setBold(True)
        f.setPointSize(11)
        header.setFont(f)
        header.setAlignment(Qt.AlignCenter)
        layout.addWidget(header)

        helper = QLabel(
            "Click two line features on the canvas to insert a tangent arc "
            "between them and trim the originals back to the tangent points. "
            "Press <b>Space</b> to reopen this dialog mid-tool."
        )
        helper.setWordWrap(True)
        helper.setStyleSheet("color: #455; padding: 4px 0;")
        layout.addWidget(helper)

        form = QFormLayout()

        settings = QSettings()
        stored_radius = settings.value(f"{_SETTINGS_PREFIX}/radius", default_radius, type=float)
        stored_tol = settings.value(f"{_SETTINGS_PREFIX}/snap_tolerance_px", 30, type=int)
        stored_segments = settings.value(f"{_SETTINGS_PREFIX}/arc_segments", 24, type=int)
        stored_replace = settings.value(f"{_SETTINGS_PREFIX}/replace_originals", True, type=bool)

        self.spn_radius = QDoubleSpinBox()
        self.spn_radius.setRange(0.001, 1e6)
        self.spn_radius.setDecimals(3)
        self.spn_radius.setSingleStep(0.5)
        self.spn_radius.setValue(stored_radius)
        self.spn_radius.setSuffix(" m")
        form.addRow("Radius:", self.spn_radius)

        self.spn_tol = QSpinBox()
        self.spn_tol.setRange(5, 200)
        self.spn_tol.setValue(stored_tol)
        self.spn_tol.setSuffix(" px")
        self.spn_tol.setToolTip("Endpoint-snap radius for Extend mode targets.")
        form.addRow("Endpoint tolerance:", self.spn_tol)

        self.spn_segments = QSpinBox()
        self.spn_segments.setRange(4, 200)
        self.spn_segments.setValue(stored_segments)
        self.spn_segments.setToolTip("Arc resolution: more segments = smoother but heavier geometry.")
        form.addRow("Arc segments:", self.spn_segments)

        self.chk_replace = QCheckBox("Trim originals in place (recommended)")
        self.chk_replace.setChecked(stored_replace)
        self.chk_replace.setToolTip(
            "When on, the two source segments are trimmed in place to the tangent "
            "points and a new arc feature is added. When off (legacy behaviour) "
            "the originals are kept and three new features are inserted, which "
            "leaves five overlapping pieces at the corner."
        )
        form.addRow(self.chk_replace)

        layout.addLayout(form)

        # Backward-compat alias — code paths in v1.3 read radiusLineEdit.text().
        # Provide a tiny shim so any third-party hook continues to work.
        self.radiusLineEdit = _RadiusLineEditShim(self.spn_radius)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.accepted.connect(self._persist)

    # ───────────────────────── helpers ─────────────────────────

    def _persist(self) -> None:
        settings = QSettings()
        settings.setValue(f"{_SETTINGS_PREFIX}/radius", self.spn_radius.value())
        settings.setValue(f"{_SETTINGS_PREFIX}/snap_tolerance_px", self.spn_tol.value())
        settings.setValue(f"{_SETTINGS_PREFIX}/arc_segments", self.spn_segments.value())
        settings.setValue(f"{_SETTINGS_PREFIX}/replace_originals", self.chk_replace.isChecked())

    def values(self) -> dict:
        return {
            "radius": float(self.spn_radius.value()),
            "snap_tolerance_px": int(self.spn_tol.value()),
            "arc_segments": int(self.spn_segments.value()),
            "replace_originals": bool(self.chk_replace.isChecked()),
        }


class _RadiusLineEditShim:
    """Compatibility shim so legacy callers reading `dlg.radiusLineEdit.text()`
    continue to work against the new QDoubleSpinBox-based dialog."""

    def __init__(self, spinbox: QDoubleSpinBox):
        self._spn = spinbox

    def text(self) -> str:
        return f"{self._spn.value():.6g}"

    def setText(self, value) -> None:
        try:
            self._spn.setValue(float(value))
        except (TypeError, ValueError):
            pass
