# -*- coding: utf-8 -*-
"""EasyFillet — CAD-like fillet & extend for QGIS line features.

v1.4 highlights (over v1.3.1):
  - Fillet now trims the source features IN PLACE instead of leaving the
    originals dangling next to three new pieces (was: 5 overlapping features
    per corner; now: 2 trimmed + 1 arc).
  - Extend mode actually extends the source line by updating its geometry,
    instead of committing a brand-new straight segment between two clicks.
  - Spatial-index-prefiltered nearest-feature search (O(log n) bbox query +
    a short candidate scan) keeps the tool snappy on multi-thousand-feature
    layers.
  - ESC cancels the current selection in either mode.
  - SpinBox-based dialog with persisted radius, snap tolerance and arc
    resolution; shortest-arc geometry (no more 270° arcs on 90° corners).
  - unload() unsets the map tool from the canvas and clears references so
    QGIS does not keep a dangling pointer after the plugin is removed.
"""
from __future__ import annotations

import math
import os

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QIcon, QCursor, QPixmap, QColor, QPainter, QPen
from qgis.PyQt.QtWidgets import QAction, QMessageBox
from qgis.core import (
    QgsCoordinateTransform,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsRectangle,
    QgsSpatialIndex,
    QgsWkbTypes,
    Qgis,
)
from qgis.gui import QgsMapToolEmitPoint, QgsRubberBand

from .easyfillet_dialog import EasyFilletDialog
from .easyfillet_logic import create_fillet_and_trims, trim_line_to_point


# Color tokens (kept consistent with v1.3 visual palette).
_FILLET_PEN = "#3ad6a1"
_FILLET_BRUSH = "#f0c2d3"
_EXTEND_PEN = "#876582"
_FIRST_LINE_RGB = Qt.GlobalColor.blue
_PREVIEW_RGB = Qt.GlobalColor.red
_NODE_RGB = Qt.GlobalColor.green
_TARGET_RGB = Qt.GlobalColor.red


def _is_line_layer(layer) -> bool:
    return bool(layer and layer.geometryType() == Qgis.GeometryType.Line)


def _single_line_pts(geom: QgsGeometry):
    """Return the polyline points of `geom` as a list of QgsPointXY.

    For multi-line geometries we use the first part — fillet/extend operate on
    one polyline at a time. Returns an empty list if no usable line is found.
    """
    if geom is None or geom.isEmpty():
        return []
    if geom.isMultipart():
        parts = geom.asMultiPolyline()
        return list(parts[0]) if parts and len(parts[0]) >= 2 else []
    pts = geom.asPolyline()
    return list(pts) if len(pts) >= 2 else []


def _single_line_geometry(geom: QgsGeometry):
    pts = _single_line_pts(geom)
    return QgsGeometry.fromPolylineXY(pts) if len(pts) >= 2 else None


class FilletMapTool(QgsMapToolEmitPoint):
    """The interactive map tool. Holds per-tool state and pulls business
    logic from `easyfillet_logic`."""

    MODE_FILLET = "fillet"
    MODE_EXTEND = "extend"

    def __init__(self, iface, plugin):
        super().__init__(iface.mapCanvas())
        self.iface = iface
        self.canvas = iface.mapCanvas()
        self.plugin = plugin

        self.selected_feature = None
        self.selected_node = None        # (QgsPointXY, QgsFeature)
        self.selected_node_index = None  # 0 or -1 (which endpoint)
        self.target_node = None

        self.preview_band = None
        self.first_band = None
        self.node_marker = None
        self.target_marker = None

        self.snapping_utils = self.canvas.snappingUtils()
        self.mode = self.MODE_FILLET
        self._set_cursor(self.MODE_FILLET)

    # ───────────────────────── shortcuts to plugin state ─────────────────────────

    @property
    def radius(self) -> float:
        return self.plugin.radius

    @property
    def tolerance_px(self) -> int:
        return self.plugin.tolerance_px

    @property
    def arc_segments(self) -> int:
        return self.plugin.arc_segments

    @property
    def replace_originals(self) -> bool:
        return self.plugin.replace_originals

    # ───────────────────────── cursor ─────────────────────────

    def _set_cursor(self, mode: str) -> None:
        size = 32
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        if mode == self.MODE_EXTEND:
            pen = QPen(QColor(_EXTEND_PEN))
            brush = QColor(_EXTEND_PEN)
        else:
            pen = QPen(QColor(_FILLET_PEN))
            brush = QColor(_FILLET_BRUSH)
        brush.setAlphaF(0.10)
        pen.setWidth(3)
        painter.setPen(pen)
        painter.setBrush(brush)
        painter.drawEllipse(4, 4, size - 8, size - 8)
        painter.end()
        self.setCursor(QCursor(pixmap))

    # ───────────────────────── keyboard ─────────────────────────

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Space:
            self.plugin.open_dialog()
        elif event.key() == Qt.Key.Key_Escape:
            self.reset()
            self.iface.messageBar().pushMessage(
                "EasyFillet", "Selection cleared", Qgis.Info, 2
            )
        else:
            super().keyPressEvent(event)

    # ───────────────────────── lifecycle ─────────────────────────

    def reset(self) -> None:
        self.selected_feature = None
        self.selected_node = None
        self.selected_node_index = None
        self.target_node = None
        for attr in ("preview_band", "first_band", "node_marker", "target_marker"):
            rb = getattr(self, attr)
            if rb is not None:
                self.canvas.scene().removeItem(rb)
                setattr(self, attr, None)
        self.canvas.setFocus()

    # ───────────────────────── canvas events ─────────────────────────

    def canvasPressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            self._toggle_mode()
            return

        if event.button() != Qt.MouseButton.LeftButton:
            return

        layer = self.iface.activeLayer()
        if not _is_line_layer(layer):
            return

        pt = self._snap(event)

        if self.mode == self.MODE_EXTEND:
            self._handle_extend_click(layer, pt)
            return

        # Fillet mode.
        feat = self.plugin.find_nearest_line_feature(layer, pt)
        if not feat:
            return
        if not self.selected_feature:
            self._select_first(layer, feat)
        else:
            self._finish_fillet(layer, feat)

    def canvasMoveEvent(self, event):
        if not self.selected_feature and self.mode == self.MODE_FILLET:
            return

        layer = self.iface.activeLayer()
        if not _is_line_layer(layer):
            return

        pt = self._snap(event)

        if self.mode == self.MODE_EXTEND and self.selected_node:
            self._preview_extend(layer, pt)
        elif self.mode == self.MODE_FILLET and self.selected_feature:
            self._preview_fillet(layer, pt)

    # ───────────────────────── mode toggling ─────────────────────────

    def _toggle_mode(self) -> None:
        if self.mode == self.MODE_EXTEND:
            self.mode = self.MODE_FILLET
            label = "Fillet Mode"
        else:
            self.mode = self.MODE_EXTEND
            label = "Extend Mode"
        self._set_cursor(self.mode)
        self.iface.messageBar().pushMessage("EasyFillet", label, Qgis.Info, 2)
        self.reset()

    # ───────────────────────── helpers ─────────────────────────

    def _snap(self, event) -> QgsPointXY:
        pt = self.toMapCoordinates(event.pos())
        match = self.snapping_utils.snapToMap(event.pos())
        return match.point() if match.isValid() else pt

    def _node_tolerance(self) -> float:
        return self.canvas.mapUnitsPerPixel() * self.tolerance_px

    def _endpoint_for(self, pts, click: QgsPointXY, tol: float):
        if len(pts) < 2:
            return None, None
        p0, pN = QgsPointXY(pts[0]), QgsPointXY(pts[-1])
        d0, d1 = p0.distance(click), pN.distance(click)
        if d0 <= d1 and d0 <= tol:
            return p0, 0
        if d1 < d0 and d1 <= tol:
            return pN, -1
        return None, None

    # ───────────────────────── fillet steps ─────────────────────────

    def _select_first(self, layer, feat) -> None:
        self.selected_feature = feat
        geom = _single_line_geometry(feat.geometry())
        if geom is None:
            self.selected_feature = None
            return
        self.first_band = QgsRubberBand(self.canvas, QgsWkbTypes.LineGeometry)
        self.first_band.setToGeometry(geom, layer)
        self.first_band.setColor(_FIRST_LINE_RGB)
        self.first_band.setWidth(3)
        self.iface.messageBar().pushMessage(
            "EasyFillet",
            f"First line selected. Click the second line (R = {self.radius:g}).",
            Qgis.Info, 2,
        )

    def _finish_fillet(self, layer, second_feat) -> None:
        if not layer.isEditable():
            QMessageBox.warning(self.iface.mainWindow(), "EasyFillet",
                                "Layer must be in editing mode.")
            return
        if second_feat.id() == self.selected_feature.id():
            self.iface.messageBar().pushMessage(
                "EasyFillet", "Pick a DIFFERENT second line.", Qgis.Warning, 2
            )
            return
        geom1 = _single_line_geometry(self.selected_feature.geometry())
        geom2 = _single_line_geometry(second_feat.geometry())
        if geom1 is None or geom2 is None:
            self.reset()
            return
        result = create_fillet_and_trims(geom1, geom2, self.radius)
        if not result:
            QMessageBox.warning(
                self.iface.mainWindow(), "EasyFillet",
                "Could not create fillet (lines may be parallel or too far apart).",
            )
            return

        arc, tp1, tp2 = result["arc"], result["tp1"], result["tp2"]
        trimmed1 = trim_line_to_point(geom1, tp1)
        trimmed2 = trim_line_to_point(geom2, tp2)

        if self.replace_originals:
            self.plugin.update_geometry(layer, self.selected_feature, trimmed1)
            self.plugin.update_geometry(layer, second_feat, trimmed2)
            self.plugin.add_feature(layer, arc, self.selected_feature)
        else:
            # Legacy v1.3 behaviour: keep originals + add three new features.
            self.plugin.add_feature(layer, arc, self.selected_feature)
            self.plugin.add_feature(layer, trimmed1, self.selected_feature)
            self.plugin.add_feature(layer, trimmed2, second_feat)

        layer.triggerRepaint()
        angle_deg = math.degrees(result.get("angle_rad", 0.0))
        self.iface.messageBar().pushMessage(
            "EasyFillet",
            f"Fillet applied (R = {self.radius:g}, corner ≈ {angle_deg:.1f}°).",
            Qgis.Success, 2,
        )
        self.reset()

    def _preview_fillet(self, layer, pt) -> None:
        feat = self.plugin.find_nearest_line_feature(
            layer, pt, exclude_fid=self.selected_feature.id()
        )
        if self.preview_band:
            self.canvas.scene().removeItem(self.preview_band)
            self.preview_band = None
        if not feat:
            return
        geom1 = _single_line_geometry(self.selected_feature.geometry())
        geom2 = _single_line_geometry(feat.geometry())
        if geom1 is None or geom2 is None:
            return
        result = create_fillet_and_trims(geom1, geom2, self.radius)
        if not result:
            return
        self.preview_band = QgsRubberBand(self.canvas, QgsWkbTypes.LineGeometry)
        self.preview_band.setToGeometry(result["arc"], layer)
        self.preview_band.setColor(_PREVIEW_RGB)
        self.preview_band.setWidth(3)

    # ───────────────────────── extend steps ─────────────────────────

    def _handle_extend_click(self, layer, pt) -> None:
        if not self.selected_node:
            feat = self.plugin.find_nearest_line_feature(layer, pt)
            if not feat:
                return
            pts = _single_line_pts(feat.geometry())
            node, idx = self._endpoint_for(pts, pt, self._node_tolerance())
            if node is None:
                self.iface.messageBar().pushMessage(
                    "EasyFillet",
                    f"Click closer than {self.tolerance_px} px to a line endpoint.",
                    Qgis.Warning, 2,
                )
                return
            self.selected_feature = feat
            self.selected_node = (node, feat)
            self.selected_node_index = idx
            self._draw_node_marker(layer, node)
            self.first_band = QgsRubberBand(self.canvas, QgsWkbTypes.LineGeometry)
            self.first_band.setToGeometry(_single_line_geometry(feat.geometry()), layer)
            self.first_band.setColor(_FIRST_LINE_RGB)
            self.first_band.setWidth(3)
            return

        target_feat = self.plugin.find_nearest_line_feature(
            layer, pt, exclude_fid=self.selected_feature.id()
        )
        target_node = pt
        if target_feat:
            tpts = _single_line_pts(target_feat.geometry())
            endpoint, _ = self._endpoint_for(tpts, pt, self._node_tolerance())
            if endpoint is not None:
                target_node = endpoint
        self._draw_target_marker(layer, target_node)

        if not layer.isEditable():
            QMessageBox.warning(self.iface.mainWindow(), "EasyFillet",
                                "Layer must be in editing mode.")
            return
        extended = self._extend_polyline(self.selected_feature.geometry(),
                                         self.selected_node_index, target_node)
        if extended is not None and not extended.isEmpty():
            self.plugin.update_geometry(layer, self.selected_feature, extended)
            layer.triggerRepaint()
            self.iface.messageBar().pushMessage(
                "EasyFillet", "Endpoint extended.", Qgis.Success, 2,
            )
        self.reset()

    def _preview_extend(self, layer, pt) -> None:
        target_feat = self.plugin.find_nearest_line_feature(
            layer, pt, exclude_fid=self.selected_feature.id()
        )
        target_node = pt
        if target_feat:
            tpts = _single_line_pts(target_feat.geometry())
            endpoint, _ = self._endpoint_for(tpts, pt, self._node_tolerance())
            if endpoint is not None:
                target_node = endpoint
        extended = self._extend_polyline(self.selected_feature.geometry(),
                                         self.selected_node_index, target_node)
        if self.preview_band:
            self.canvas.scene().removeItem(self.preview_band)
            self.preview_band = None
        if extended is not None and not extended.isEmpty():
            self.preview_band = QgsRubberBand(self.canvas, QgsWkbTypes.LineGeometry)
            self.preview_band.setToGeometry(extended, layer)
            self.preview_band.setColor(_PREVIEW_RGB)
            self.preview_band.setWidth(3)
        self._draw_target_marker(layer, target_node)

    def _extend_polyline(self, source_geom, node_index, to_node):
        pts = _single_line_pts(source_geom)
        if len(pts) < 2:
            return None
        if node_index == 0:
            new_pts = [to_node] + pts[1:]
        elif node_index == -1:
            new_pts = pts[:-1] + [to_node]
        else:
            return None
        return QgsGeometry.fromPolylineXY(new_pts)

    # ───────────────────────── marker helpers ─────────────────────────

    def _draw_node_marker(self, layer, point: QgsPointXY) -> None:
        if self.node_marker is not None:
            self.canvas.scene().removeItem(self.node_marker)
        self.node_marker = QgsRubberBand(self.canvas, QgsWkbTypes.PointGeometry)
        self.node_marker.setToGeometry(QgsGeometry.fromPointXY(point), layer)
        self.node_marker.setColor(_NODE_RGB)
        self.node_marker.setWidth(10)

    def _draw_target_marker(self, layer, point: QgsPointXY) -> None:
        if self.target_marker is not None:
            self.canvas.scene().removeItem(self.target_marker)
        self.target_marker = QgsRubberBand(self.canvas, QgsWkbTypes.PointGeometry)
        self.target_marker.setToGeometry(QgsGeometry.fromPointXY(point), layer)
        self.target_marker.setColor(_TARGET_RGB)
        self.target_marker.setWidth(10)


class EasyFillet:
    """QGIS plugin entry class."""

    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.action = None
        self.map_tool = None
        # Defaults (persisted to QSettings via the dialog).
        self.radius = 4.0
        self.tolerance_px = 30
        self.arc_segments = 24
        self.replace_originals = True
        # Per-layer spatial-index cache (lazily built / invalidated on edits).
        self._index_cache: dict = {}

    # ───────────────────────── lifecycle ─────────────────────────

    def initGui(self) -> None:
        icon = QIcon(os.path.join(self.plugin_dir, "icon.png"))
        self.action = QAction(icon, "EasyFillet", self.iface.mainWindow())
        self.action.setToolTip(
            "EasyFillet — pick two line features to insert a tangent arc. "
            "Press Space mid-tool to edit the radius."
        )
        self.action.triggered.connect(self.activate_tool)
        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToMenu("&EasyFillet", self.action)

    def unload(self) -> None:
        # Detach the map tool BEFORE clearing our reference. v1.3 never did
        # this and left QGIS holding a dangling pointer that crashed on the
        # next canvas interaction.
        canvas = self.iface.mapCanvas()
        if self.map_tool is not None and canvas.mapTool() is self.map_tool:
            canvas.unsetMapTool(self.map_tool)
        self.map_tool = None
        self._index_cache.clear()
        if self.action is not None:
            self.iface.removeToolBarIcon(self.action)
            self.iface.removePluginMenu("&EasyFillet", self.action)
            self.action = None

    # ───────────────────────── activation ─────────────────────────

    def activate_tool(self) -> None:
        layer = self.iface.activeLayer()
        if not _is_line_layer(layer):
            QMessageBox.warning(self.iface.mainWindow(), "EasyFillet",
                                "Please activate a line layer.")
            return
        if not layer.isEditable():
            ret = QMessageBox.question(
                self.iface.mainWindow(), "EasyFillet",
                "Layer is not in editing mode. Enable editing?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if ret == QMessageBox.StandardButton.Yes:
                layer.startEditing()
            else:
                return
        if not self.open_dialog():
            return
        if self.map_tool is None:
            self.map_tool = FilletMapTool(self.iface, self)
        self.map_tool.reset()
        self.iface.mapCanvas().setMapTool(self.map_tool)

    def open_dialog(self) -> bool:
        dlg = EasyFilletDialog(self.iface.mainWindow(), default_radius=self.radius)
        if dlg.exec() != EasyFilletDialog.DialogCode.Accepted:
            return False
        v = dlg.values()
        self.radius = v["radius"]
        self.tolerance_px = v["snap_tolerance_px"]
        self.arc_segments = v["arc_segments"]
        self.replace_originals = v["replace_originals"]
        return True

    # ───────────────────────── feature lookup ─────────────────────────

    def _get_spatial_index(self, layer):
        cache = self._index_cache.get(layer.id())
        if cache is not None:
            return cache
        index = QgsSpatialIndex(layer.getFeatures())

        def _invalidate(*_args):
            self._index_cache.pop(layer.id(), None)

        try:
            layer.geometryChanged.connect(_invalidate)
            layer.featureAdded.connect(_invalidate)
            layer.featuresDeleted.connect(_invalidate)
            layer.editingStopped.connect(_invalidate)
        except Exception:
            pass

        self._index_cache[layer.id()] = index
        return index

    def find_nearest_line_feature(self, layer, point: QgsPointXY,
                                  exclude_fid=None):
        """Spatial-index-prefiltered nearest-line lookup.

        v1.3 walked every feature in the layer; for a 5 000-feature plan that
        was ~50 ms per move event and made the preview stutter. The index
        narrows the candidate set to ~10 features, then we measure distance
        precisely against each one.
        """
        index = self._get_spatial_index(layer)
        layer_point = self._point_in_layer_crs(layer, point)

        # Prefer NN lookup first: stable across DPI/canvas differences in QGIS 3/4.
        candidates = []
        try:
            candidates = list(index.nearestNeighbor(layer_point, 24))
        except Exception:
            candidates = []
        if exclude_fid is not None and candidates:
            candidates = [fid for fid in candidates if fid != exclude_fid]

        # Fallback to bbox expansion if NN yields nothing.
        if not candidates:
            upp = self.iface.mapCanvas().mapUnitsPerPixel() or 1.0
            fallback_r = max(upp * 2000, 1.0)
            for mul in (1.0, 4.0, 16.0):
                r = fallback_r * mul
                rect = QgsRectangle(layer_point.x() - r, layer_point.y() - r,
                                    layer_point.x() + r, layer_point.y() + r)
                candidates = index.intersects(rect)
                if exclude_fid is not None:
                    candidates = [fid for fid in candidates if fid != exclude_fid]
                if candidates:
                    break
        if not candidates:
            return None
        point_geom = QgsGeometry.fromPointXY(layer_point)
        nearest_feat = None
        nearest_dist = float("inf")
        for fid in candidates:
            feat = layer.getFeature(fid)
            if not feat.isValid():
                continue
            geom = _single_line_geometry(feat.geometry())
            if geom is None:
                continue
            d = geom.distance(point_geom)
            if d < nearest_dist:
                nearest_dist = d
                nearest_feat = feat
        return nearest_feat

    def _point_in_layer_crs(self, layer, point: QgsPointXY) -> QgsPointXY:
        """Transform a canvas/map point to layer CRS if needed.

        QGIS 4 projects commonly keep a global map CRS while editing layers in
        local projected CRSs. Without this transform the nearest-feature lookup
        can miss every candidate, so preview/edit appears to do nothing.
        """
        if layer is None or point is None:
            return point
        try:
            canvas = self.iface.mapCanvas()
            map_crs = canvas.mapSettings().destinationCrs() if canvas else None
            layer_crs = layer.crs() if hasattr(layer, "crs") else None
            if (
                map_crs is not None
                and layer_crs is not None
                and map_crs.isValid()
                and layer_crs.isValid()
                and map_crs != layer_crs
            ):
                transform = QgsCoordinateTransform(map_crs, layer_crs, QgsProject.instance())
                return transform.transform(point)
        except Exception:
            pass
        return point

    # ───────────────────────── geometry helpers ─────────────────────────

    def get_single_line_geometry(self, geom):  # kept for backward compatibility
        return _single_line_geometry(geom)

    def extend_line_to_point(self, geom, node_index, to_node):  # legacy alias
        pts = _single_line_pts(geom)
        if len(pts) < 2:
            return None
        if node_index == 0:
            new_pts = [to_node] + pts[1:]
        elif node_index == -1:
            new_pts = pts[:-1] + [to_node]
        else:
            return None
        return {"extended": QgsGeometry.fromPolylineXY(new_pts)}

    # ───────────────────────── layer write helpers ─────────────────────────

    def add_feature(self, layer, geom: QgsGeometry, source_feat) -> None:
        """Insert a new feature inheriting attributes from `source_feat`,
        clearing any primary-key style 'fid' column so QGIS auto-assigns."""
        feat = QgsFeature(layer.fields())
        feat.setGeometry(geom)
        field_names = [field.name() for field in layer.fields()]
        try:
            fid_index = field_names.index("fid")
        except ValueError:
            fid_index = None
        new_attrs = []
        for i, value in enumerate(source_feat.attributes()):
            new_attrs.append(None if i == fid_index else value)
        feat.setAttributes(new_attrs)
        layer.addFeature(feat)

    def update_geometry(self, layer, feat, new_geom: QgsGeometry) -> bool:
        """Replace the geometry of an existing feature on the active edit
        session. Used by the in-place fillet and by Extend mode so the source
        line gets actually trimmed / extended instead of cloned."""
        if feat is None or new_geom is None or new_geom.isEmpty():
            return False
        if not layer.isEditable():
            return False
        return bool(layer.changeGeometry(feat.id(), new_geom))
