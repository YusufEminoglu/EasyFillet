from qgis.PyQt.QtCore import QCoreApplication, Qt
from qgis.PyQt.QtGui import QIcon, QCursor, QPixmap, QColor
from qgis.PyQt.QtWidgets import QAction, QMessageBox
from qgis.core import (
    QgsProject, QgsFeature, QgsGeometry, QgsPointXY, QgsWkbTypes,
    QgsSpatialIndex, QgsRectangle, QgsSnappingConfig
)
from qgis.gui import QgsMapToolEmitPoint, QgsRubberBand
from qgis.utils import iface
import math
from .easyfillet_dialog import EasyFilletDialog
import os
from qgis.PyQt import QtGui

class FilletMapTool(QgsMapToolEmitPoint):
    def __init__(self, iface, plugin):
        super().__init__(iface.mapCanvas())
        self.iface = iface
        self.canvas = iface.mapCanvas()
        self.plugin = plugin
        self.selected_feature = None
        self.preview_band = None
        self.first_band = None
        self.radius = plugin.radius
        self.snapping_utils = self.canvas.snappingUtils()
        # Custom circle cursor
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.transparent)
        painter = QtGui.QPainter(pixmap)
        pen = QtGui.QPen(QColor('#3ad6a1'))
        pen.setWidth(3)
        painter.setPen(pen)
        fill = QColor('#f0c2d3')
        fill.setAlphaF(0.1)  # 90% transparent
        painter.setBrush(fill)
        painter.drawEllipse(4, 4, 24, 24)
        painter.end()
        self.setCursor(QCursor(pixmap))

    def reset(self):
        self.selected_feature = None
        if self.preview_band:
            self.canvas.scene().removeItem(self.preview_band)
            self.preview_band = None
        if self.first_band:
            self.canvas.scene().removeItem(self.first_band)
            self.first_band = None

    def canvasPressEvent(self, event):
        layer = self.iface.activeLayer()
        if not layer:
            return
        point = self.toMapCoordinates(event.pos())
        snap_match = self.snapping_utils.snapToMap(event.pos())
        if snap_match.isValid():
            point = snap_match.point()
        nearest = self.plugin.find_nearest_line_feature(layer, point)
        if not nearest:
            return
        if not self.selected_feature:
            self.selected_feature = nearest
            # Highlight the first selected line
            if self.first_band:
                self.canvas.scene().removeItem(self.first_band)
            self.first_band = QgsRubberBand(self.canvas, QgsWkbTypes.LineGeometry)
            geom = self.plugin.get_single_line_geometry(nearest.geometry())
            if geom:
                self.first_band.setToGeometry(geom, layer)
                self.first_band.setColor(Qt.blue)
                self.first_band.setWidth(3)
        else:
            if not layer.isEditable():
                QMessageBox.warning(self.iface.mainWindow(), "EasyFillet", "Layer must be in editing mode.")
                return
            # --- Fillet and trim logic ---
            geom1 = self.plugin.get_single_line_geometry(self.selected_feature.geometry())
            geom2 = self.plugin.get_single_line_geometry(nearest.geometry())
            fillet_result = self.plugin.create_fillet_with_trim(geom1, geom2, self.radius)
            if not fillet_result:
                QMessageBox.warning(self.iface.mainWindow(), "EasyFillet", "Could not create fillet (lines may be parallel or too far apart).")
                return
            arc_geom, tp1, tp2 = fillet_result['arc'], fillet_result['tp1'], fillet_result['tp2']
            trimmed1 = self.plugin.trim_line_to_point(geom1, tp1)
            trimmed2 = self.plugin.trim_line_to_point(geom2, tp2)
            # Add arc (attributes from first line)
            new_arc = QgsFeature(layer.fields())
            new_arc.setGeometry(arc_geom)
            new_arc.setAttributes(self.selected_feature.attributes())
            layer.addFeature(new_arc)
            # Add trimmed lines (attributes from originals)
            new_trim1 = QgsFeature(layer.fields())
            new_trim1.setGeometry(trimmed1)
            new_trim1.setAttributes(self.selected_feature.attributes())
            layer.addFeature(new_trim1)
            new_trim2 = QgsFeature(layer.fields())
            new_trim2.setGeometry(trimmed2)
            new_trim2.setAttributes(nearest.attributes())
            layer.addFeature(new_trim2)
            layer.triggerRepaint()
            self.reset()

    def canvasMoveEvent(self, event):
        if not self.selected_feature:
            return
        layer = self.iface.activeLayer()
        if not layer:
            return
        point = self.toMapCoordinates(event.pos())
        snap_match = self.snapping_utils.snapToMap(event.pos())
        if snap_match.isValid():
            point = snap_match.point()
        nearest = self.plugin.find_nearest_line_feature(layer, point, exclude_fid=self.selected_feature.id())
        if not nearest:
            if self.preview_band:
                self.canvas.scene().removeItem(self.preview_band)
                self.preview_band = None
            return
        fillet_result = self.plugin.create_fillet_with_trim(
            self.plugin.get_single_line_geometry(self.selected_feature.geometry()),
            self.plugin.get_single_line_geometry(nearest.geometry()),
            self.radius
        )
        if self.preview_band:
            self.canvas.scene().removeItem(self.preview_band)
            self.preview_band = None
        if fillet_result:
            arc_geom = fillet_result['arc']
            self.preview_band = QgsRubberBand(self.canvas, QgsWkbTypes.LineGeometry)
            self.preview_band.setToGeometry(arc_geom, layer)
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
        # Show radius dialog before selection
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
        # Find the nearest line feature to the point, optionally excluding a feature by id
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
        # Returns a single-part line geometry for preview/fillet
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

    def create_fillet_with_trim(self, geom1, geom2, radius):
        # Returns {'arc': arc_geom, 'tp1': tangent_point1, 'tp2': tangent_point2} or None
        pts1 = geom1.asPolyline() or geom1.asMultiPolyline()[0]
        pts2 = geom2.asPolyline() or geom2.asMultiPolyline()[0]
        intersection = geom1.intersection(geom2)
        if intersection.isEmpty():
            p1a, p1b = pts1[0], pts1[-1]
            p2a, p2b = pts2[0], pts2[-1]
            inter_pt = self.line_intersection(p1a, p1b, p2a, p2b)
            if not inter_pt:
                return None
        else:
            inter_pt = intersection.asPoint()
        def unit_vec(a, b):
            dx, dy = b.x() - a.x(), b.y() - a.y()
            d = math.hypot(dx, dy)
            return (dx/d, dy/d) if d != 0 else (0, 0)
        idx1 = 0 if QgsPointXY(pts1[0]).distance(inter_pt) < QgsPointXY(pts1[-1]).distance(inter_pt) else -1
        idx2 = 0 if QgsPointXY(pts2[0]).distance(inter_pt) < QgsPointXY(pts2[-1]).distance(inter_pt) else -1
        v1 = unit_vec(inter_pt, pts1[idx1])
        v2 = unit_vec(inter_pt, pts2[idx2])
        dot = v1[0]*v2[0] + v1[1]*v2[1]
        if abs(abs(dot) - 1) < 1e-6:
            return None
        angle = math.acos(max(-1, min(1, v1[0]*v2[0] + v1[1]*v2[1])))
        if angle == 0:
            return None
        tan_len = radius / math.tan(angle/2)
        tp1 = QgsPointXY(inter_pt.x() + v1[0]*tan_len, inter_pt.y() + v1[1]*tan_len)
        tp2 = QgsPointXY(inter_pt.x() + v2[0]*tan_len, inter_pt.y() + v2[1]*tan_len)
        bisec_angle = math.atan2(v1[1]+v2[1], v1[0]+v2[0])
        center_dist = radius / math.sin(angle/2)
        center = QgsPointXY(inter_pt.x() + math.cos(bisec_angle)*center_dist,
                            inter_pt.y() + math.sin(bisec_angle)*center_dist)
        arc_pts = self.arc_points(center, tp1, tp2, radius, 20)
        # Ensure arc is on the smaller angle (not reflex)
        v_tp1 = (tp1.x() - center.x(), tp1.y() - center.y())
        v_tp2 = (tp2.x() - center.x(), tp2.y() - center.y())
        angle1 = math.atan2(v_tp1[1], v_tp1[0])
        angle2 = math.atan2(v_tp2[1], v_tp2[0])
        angle_diff = (angle2 - angle1) % (2 * math.pi)
        if angle_diff > math.pi:
            arc_pts = list(reversed(arc_pts))
        arc_geom = QgsGeometry.fromPolylineXY(arc_pts)
        return {'arc': arc_geom, 'tp1': tp1, 'tp2': tp2}

    def trim_line_to_point(self, geom, trim_point):
        # Trims the line to the trim_point (from the endpoint closest to trim_point)
        pts = geom.asPolyline() or geom.asMultiPolyline()[0]
        d0 = QgsPointXY(pts[0]).distance(trim_point)
        d1 = QgsPointXY(pts[-1]).distance(trim_point)
        if d0 < d1:
            new_pts = [trim_point] + pts[1:]
        else:
            new_pts = pts[:-1] + [trim_point]
        return QgsGeometry.fromPolylineXY(new_pts)

    def line_intersection(self, p1, p2, p3, p4):
        # Returns intersection point of lines (p1,p2) and (p3,p4), or None if parallel
        x1, y1, x2, y2 = p1.x(), p1.y(), p2.x(), p2.y()
        x3, y3, x4, y4 = p3.x(), p3.y(), p4.x(), p4.y()
        denom = (x1-x2)*(y3-y4) - (y1-y2)*(x3-x4)
        if denom == 0:
            return None
        px = ((x1*y2 - y1*x2)*(x3-x4) - (x1-x2)*(x3*y4 - y3*x4)) / denom
        py = ((x1*y2 - y1*x2)*(y3-y4) - (y1-y2)*(x3*y4 - y3*x4)) / denom
        return QgsPointXY(px, py)

    def arc_points(self, center, pt1, pt2, radius, segments):
        # Returns list of points along arc from pt1 to pt2, CCW
        def angle(p):
            return math.atan2(p.y() - center.y(), p.x() - center.x())
        a1 = angle(pt1)
        a2 = angle(pt2)
        # Ensure shortest arc
        if a2 < a1:
            a2 += 2*math.pi
        arc = []
        for i in range(segments+1):
            t = a1 + (a2 - a1) * i / segments
            arc.append(QgsPointXY(center.x() + radius*math.cos(t),
                                  center.y() + radius*math.sin(t)))
        return arc
