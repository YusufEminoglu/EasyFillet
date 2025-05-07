from qgis.PyQt.QtWidgets import QDialog, QVBoxLayout, QLabel, QLineEdit, QPushButton

class EasyFilletDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Fillet Radius")
        layout = QVBoxLayout()
        layout.addWidget(QLabel("Enter fillet radius:"))
        self.radiusLineEdit = QLineEdit()
        self.radiusLineEdit.setPlaceholderText("Radius (map units)")
        self.radiusLineEdit.setText("10")  # Default radius for EPSG:5253 (meters)
        layout.addWidget(self.radiusLineEdit)
        btn = QPushButton("OK")
        btn.clicked.connect(self.accept)
        layout.addWidget(btn)
        self.setLayout(layout)
