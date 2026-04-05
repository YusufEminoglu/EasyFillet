from qgis.PyQt.QtCore import QCoreApplication, Qt
from qgis.PyQt.QtGui import QIcon, QCursor, QPixmap, QColor, QPainter, QPen
from qgis.PyQt.QtWidgets import QAction, QMessageBox
from qgis.core import (
    QgsProject, QgsFeature, QgsGeometry, QgsPointXY, QgsWkbTypes,
    QgsSpatialIndex, QgsRectangle, QgsSnappingConfig, Qgis
)
from qgis.gui import QgsMapToolEmitPoint, QgsRubberBand
from qgis.utils import iface
import math
import os
from .easyfillet_dialog import EasyFilletDialog

from .easyfillet_logic import create_fillet_and_trims, trim_line_to_point, line_intersection

class FilletMapTool(QgsMapToolEmitPoint):
    def __init__(self, iface, plugin):
        super().__init__(iface.mapCanvas())
        self.iface = iface
        self.canvas = iface.mapCanvas()
        self.plugin = plugin
        
        self.selected_feature = None
        self.selected_node = None
        self.selected_node_index = None
        self.target_node = None
        
        self.preview_band = None
        self.first_band = None
        self.node_marker = None
        self.target_marker = None
        
        self.radius = plugin.radius
        self.snapping_utils = self.canvas.snappingUtils()
        self.mode = 'fillet'
        self._set_cursor('fillet')

    def _set_cursor(self, mode):
        size = 32
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        if mode == 'extend':
            pen = QPen(QColor('#876582'))
            brush = QColor('#876582')
            brush.setAlphaF(0.1)
        else:
            pen = QPen(QColor('#3ad6a1'))
            brush = QColor('#f0c2d3')
            brush.setAlphaF(0.1)
        pen.setWidth(3)
        painter.setPen(pen)
        painter.setBrush(brush)
        painter.drawEllipse(4, 4, size-8, size-8)
        painter.end()
        self.setCursor(QCursor(pixmap))

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Space:
            dlg = EasyFilletDialog()
            dlg.radiusLineEdit.setText(str(self.radius))
            if dlg.exec_():
                try:
                    val = float(dlg.radiusLineEdit.text())
                    if val > 0:
                        self.radius = val
                        self.plugin.radius = val
                except Exception:
                    pass
        else:
            super().keyPressEvent(event)

    def reset(self):
        self.selected_feature = None
        self.selected_node = None
        self.selected_node_index = None
        self.target_node = None
        if self.preview_band:
            self.canvas.scene().removeItem(self.preview_band)
        if self.first_band:
            self.canvas.scene().removeItem(self.first_band)
        if self.node_marker:
            self.canvas.scene().removeItem(self.node_marker)
        if self.target_marker:
            self.canvas.scene().removeItem(self.target_marker)
        self.preview_band = None
        self.first_band = None
        self.node_marker = None
        self.target_marker = None
        self.canvas.setFocus()

    def canvasPressEvent(self, event):
        if event.button() == Qt.RightButton:
            if self.mode == 'extend':
                self.mode = 'fillet'
                self._set_cursor('fillet')
                self.iface.messageBar().pushMessage('Fillet Mode', '', Qgis.Info, 2)
                self.reset()
                return
            else:
                self.mode = 'extend'
                self._set_cursor('extend')
                self.iface.messageBar().pushMessage('Extend Mode', '', Qgis.Info, 2)
                self.reset()
                return

        elif event.button() == Qt.LeftButton and self.mode == 'extend':
            layer = self.iface.activeLayer()
            if not layer or layer.geometryType() != QgsWkbTypes.LineGeometry:
                return
            pt = self.toMapCoordinates(event.pos())
            snap = self.snapping_utils.snapToMap(event.pos())
            if snap.isValid():
                pt = snap.point()

            if not self.selected_node:
                feat = self.plugin.find_nearest_line_feature(layer, pt)
                if not feat:
                    return
                geom = self.plugin.get_single_line_geometry(feat.geometry())
                if not geom:
                    return
                pts = geom.asPolyline() if not geom.isMultipart() else geom.asMultiPolyline()[0]
                d0 = QgsPointXY(pts[0]).distance(pt)
                d1 = QgsPointXY(pts[-1]).distance(pt)
                tol = self.canvas.mapUnitsPerPixel() * 10
                if d0 < d1 and d0 < tol:
                    node = QgsPointXY(pts[0])
                    node_index = 0
                elif d1 < tol:
                    node = QgsPointXY(pts[-1])
                    node_index = -1
                else:
                    return
                self.selected_feature = feat
                self.selected_node = (node, feat)
                self.selected_node_index = node_index

                if self.node_marker:
                    self.canvas.scene().removeItem(self.node_marker)
                self.node_marker = QgsRubberBand(self.canvas, QgsWkbTypes.PointGeometry)
                self.node_marker.setToGeometry(QgsGeometry.fromPointXY(node), layer)
                self.node_marker.setColor(Qt.green)
                self.node_marker.setWidth(10)

                if self.first_band:
                    self.canvas.scene().removeItem(self.first_band)
                self.first_band = QgsRubberBand(self.canvas, QgsWkbTypes.LineGeometry)
                self.first_band.setToGeometry(geom, layer)
                self.first_band.setColor(Qt.blue)
                self.first_band.setWidth(3)
            else:
                target_feat = self.plugin.find_nearest_line_feature(layer, pt, exclude_fid=self.selected_feature.id())
                target_node = None
                tol = self.canvas.mapUnitsPerPixel() * 30
                if target_feat:
                    ngeom = self.plugin.get_single_line_geometry(target_feat.geometry())
                    if ngeom:
                        npts = ngeom.asPolyline() if not ngeom.isMultipart() else ngeom.asMultiPolyline()[0]
                        d0 = QgsPointXY(npts[0]).distance(pt)
                        d1 = QgsPointXY(npts[-1]).distance(pt)
                        if d0 < d1 and d0 < tol:
                            target_node = QgsPointXY(npts[0])
                        elif d1 < tol:
                            target_node = QgsPointXY(npts[-1])
                if not target_node:
                    target_node = pt
                
                self.target_node = (target_node, target_feat)
                
                if self.target_marker:
                    self.canvas.scene().removeItem(self.target_marker)
                self.target_marker = QgsRubberBand(self.canvas, QgsWkbTypes.PointGeometry)
                self.target_marker.setToGeometry(QgsGeometry.fromPointXY(target_node), layer)
                self.target_marker.setColor(Qt.red)
                self.target_marker.setWidth(10)

                node, feat = self.selected_node
                start_point = QgsPointXY(node)
                end_point = QgsPointXY(target_node)
                new_geom = QgsGeometry.fromPolylineXY([start_point, end_point])
                self.plugin.add_feature(layer, new_geom, feat)
                layer.triggerRepaint()
                self.reset()
            return

        if self.mode == 'fillet':
            self._set_cursor('fillet')
            layer = self.iface.activeLayer()
            if not layer or layer.geometryType() != QgsWkbTypes.LineGeometry:
                return
            pt = self.toMapCoordinates(event.pos())
            snap = self.snapping_utils.snapToMap(event.pos())
            if snap.isValid():
                pt = snap.point()
            feat = self.plugin.find_nearest_line_feature(layer, pt)
            if not feat:
                return
            if not self.selected_feature:
                self.selected_feature = feat
                if self.first_band:
                    self.canvas.scene().removeItem(self.first_band)
                self.first_band = QgsRubberBand(self.canvas, QgsWkbTypes.LineGeometry)
                geom = self.plugin.get_single_line_geometry(feat.geometry())
                self.first_band.setToGeometry(geom, layer)
                self.first_band.setColor(Qt.blue)
                self.first_band.setWidth(3)
            else:
                if not layer.isEditable():
                    QMessageBox.warning(self.iface.mainWindow(), "EasyFillet", "Layer must be in editing mode.")
                    return
                geom1 = self.plugin.get_single_line_geometry(self.selected_feature.geometry())
                geom2 = self.plugin.get_single_line_geometry(feat.geometry())
                result = create_fillet_and_trims(geom1, geom2, self.radius)
                if not result:
                    QMessageBox.warning(self.iface.mainWindow(), "EasyFillet", "Could not create fillet (lines may be parallel or too far apart).")
                    return
                arc, tp1, tp2 = result['arc'], result['tp1'], result['tp2']
                trimmed1 = trim_line_to_point(geom1, tp1)
                trimmed2 = trim_line_to_point(geom2, tp2)
                
                self.plugin.add_feature(layer, arc, self.selected_feature)
                self.plugin.add_feature(layer, trimmed1, self.selected_feature)
                self.plugin.add_feature(layer, trimmed2, feat)
                layer.triggerRepaint()
                self.reset()

    def canvasMoveEvent(self, event):
        if self.mode == 'extend' and self.selected_node:
            layer = self.iface.activeLayer()
            if not layer or layer.geometryType() != QgsWkbTypes.LineGeometry:
                return
            pt = self.toMapCoordinates(event.pos())
            snap = self.snapping_utils.snapToMap(event.pos())
            if snap.isValid():
                pt = snap.point()
            target_feat = self.plugin.find_nearest_line_feature(layer, pt, exclude_fid=self.selected_feature.id())
            target_node = None
            tol = self.canvas.mapUnitsPerPixel() * 30
            if target_feat:
                ngeom = self.plugin.get_single_line_geometry(target_feat.geometry())
                if ngeom:
                    npts = ngeom.asPolyline() if not ngeom.isMultipart() else ngeom.asMultiPolyline()[0]
                    d0 = QgsPointXY(npts[0]).distance(pt)
                    d1 = QgsPointXY(npts[-1]).distance(pt)
                    if d0 < d1 and d0 < tol:
                        target_node = QgsPointXY(npts[0])
                    elif d1 < tol:
                        target_node = QgsPointXY(npts[-1])
            if not target_node:
                target_node = pt

            node, feat = self.selected_node
            geom = self.plugin.get_single_line_geometry(feat.geometry())
            result = self.plugin.extend_line_to_point(geom, self.selected_node_index, target_node)
            if self.preview_band:
                self.canvas.scene().removeItem(self.preview_band)
                self.preview_band = None
            if result:
                self.preview_band = QgsRubberBand(self.canvas, QgsWkbTypes.LineGeometry)
                self.preview_band.setToGeometry(result['extended'], layer)
                self.preview_band.setColor(Qt.red)
                self.preview_band.setWidth(3)

            if self.target_marker:
                self.canvas.scene().removeItem(self.target_marker)
                self.target_marker = None
            self.target_marker = QgsRubberBand(self.canvas, QgsWkbTypes.PointGeometry)
            self.target_marker.setToGeometry(QgsGeometry.fromPointXY(target_node), layer)
            self.target_marker.setColor(Qt.red)
            self.target_marker.setWidth(10)
        else:
            if self.mode == 'fillet':
                self._set_cursor('fillet')
            if not self.selected_feature:
                return
            layer = self.iface.activeLayer()
            if not layer or layer.geometryType() != QgsWkbTypes.LineGeometry:
                return
            pt = self.toMapCoordinates(event.pos())
            snap = self.snapping_utils.snapToMap(event.pos())
            if snap.isValid():
                pt = snap.point()
            feat = self.plugin.find_nearest_line_feature(layer, pt, exclude_fid=self.selected_feature.id())
            if self.preview_band:
                self.canvas.scene().removeItem(self.preview_band)
                self.preview_band = None
            if not feat:
                return
            result = create_fillet_and_trims(
                self.plugin.get_single_line_geometry(self.selected_feature.geometry()),
                self.plugin.get_single_line_geometry(feat.geometry()),
                self.radius
            )
            if result:
                self.preview_band = QgsRubberBand(self.canvas, QgsWkbTypes.LineGeometry)
                self.preview_band.setToGeometry(result['arc'], layer)
                self.preview_band.setColor(Qt.red)
                self.preview_band.setWidth(3)


class EasyFillet:
    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.action = None
        self.map_tool = None
        self.radius = 4  # Default radius

    def initGui(self):
        icon = QIcon(os.path.join(self.plugin_dir, "icon.png"))
        self.action = QAction(icon, "EasyFillet", self.iface.mainWindow())
        self.action.triggered.connect(self.activate_tool)
        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToMenu("&EasyFillet", self.action)

    def unload(self):
        self.iface.removeToolBarIcon(self.action)
        self.iface.removePluginMenu("&EasyFillet", self.action)

    def activate_tool(self):
        layer = self.iface.activeLayer()
        if not layer or layer.geometryType() != QgsWkbTypes.LineGeometry:
            QMessageBox.warning(self.iface.mainWindow(), "EasyFillet", "Please activate a line layer.")
            return
        if not layer.isEditable():
            ret = QMessageBox.question(self.iface.mainWindow(), "EasyFillet", "Layer is not in editing mode. Enable editing?", QMessageBox.Yes | QMessageBox.No)
            if ret == QMessageBox.Yes:
                layer.startEditing()
            else:
                return
        dlg = EasyFilletDialog()
        dlg.radiusLineEdit.setText(str(self.radius))
        if not dlg.exec_():
            return
        try:
            self.radius = float(dlg.radiusLineEdit.text())
            if self.radius <= 0:
                raise ValueError
        except Exception:
            QMessageBox.warning(self.iface.mainWindow(), "EasyFillet", "Invalid radius.")
            return
        if self.map_tool is None:
            self.map_tool = FilletMapTool(self.iface, self)
        self.map_tool.radius = self.radius
        self.map_tool.reset()
        self.iface.mapCanvas().setMapTool(self.map_tool)

    def find_nearest_line_feature(self, layer, point, exclude_fid=None):
        min_dist = float('inf')
        nearest_feat = None
        for feat in layer.getFeatures():
            if exclude_fid is not None and feat.id() == exclude_fid:
                continue
            geom = self.get_single_line_geometry(feat.geometry())
            if not geom:
                continue
            dist = geom.distance(QgsGeometry.fromPointXY(point))
            if dist < min_dist:
                min_dist = dist
                nearest_feat = feat
        return nearest_feat

    def get_single_line_geometry(self, geom):
        if geom.isMultipart():
            parts = geom.asMultiPolyline()
            if not parts or len(parts[0]) < 2:
                return None
            return QgsGeometry.fromPolylineXY(parts[0])
        else:
            pts = geom.asPolyline()
            if not pts or len(pts) < 2:
                return None
            return geom

    def extend_line_to_point(self, geom, node_index, to_node):
        pts = geom.asPolyline() if not geom.isMultipart() else geom.asMultiPolyline()[0]
        if len(pts) < 2:
            return None
        if node_index == 0:
            new_pts = [to_node] + pts[1:]
        elif node_index == -1:
            new_pts = pts[:-1] + [to_node]
        else:
            return None
        return {'extended': QgsGeometry.fromPolylineXY(new_pts)}

    def add_feature(self, layer, geom, source_feat):
        feat = QgsFeature(layer.fields())
        feat.setGeometry(geom)
        field_names = [field.name() for field in layer.fields()]
        try:
            fid_index = field_names.index('fid')
        except ValueError:
            fid_index = None
        source_attrs = source_feat.attributes()
        new_attrs = []
        for i, val in enumerate(source_attrs):
            if i == fid_index:
                new_attrs.append(None)
            else:
                new_attrs.append(val)
        feat.setAttributes(new_attrs)
        layer.addFeature(feat)
