# EasyFillet

**A CAD-grade fillet tool for QGIS — part of the PlanX suite**

EasyFillet lets you pick two line segments, set a radius, preview a chord-length guide, and instantly generate a precise tangent arc while trimming the original lines so they meet at a clean node. It brings drafting-grade fillet operations directly into QGIS vector editing.

---

## Features

- Interactive two-segment selection with live radius preview
- Generates true tangent arcs with correct geometric topology
- Trims source lines to meet the arc at a perfect node
- Numeric-radius input dialog for precise control
- Right-click **Extend** mode to lengthen segments before filleting
- Works with any CRS; handles mixed-CRS layer pairs

## Installation

1. Download the latest `.zip` from [Releases](https://github.com/YusufEminoglu/EasyFillet/releases).
2. In QGIS: **Plugins → Manage and Install Plugins → Install from ZIP**.
3. Activate **EasyFillet** from the plugin list.

## Usage

1. Open an editable line layer.
2. Click the **EasyFillet** tool icon in the toolbar.
3. Click the first segment, then the second.
4. Enter the desired radius in the dialog.
5. Press **OK** — the arc and trimmed lines are added automatically.

## Compatibility

| Requirement | Value |
|---|---|
| QGIS minimum | 3.0 |
| QGIS maximum | 3.99 |
| License | GPL-3.0 |

## Changelog

- **1.2.0** — Numeric-radius dialog, chord-length preview, right-click extend
- **1.1.0** — Fixed snapping-tolerance bug for mixed CRS layers
- **1.0.0** — Initial stable release

## Author

**Yusuf Eminoglu** — [GitHub](https://github.com/YusufEminoglu) | geospacephilo@gmail.com

Part of the **[PlanX](https://github.com/YusufEminoglu/PlanX)** urban planning plugin suite.