<div align="center">

<img src="icon.svg" width="96" alt="EasyFillet icon"/>

# EasyFillet

**CAD-grade fillet for QGIS — true tangent arcs with live radius preview and automatic trimming. Part of the PlanX suite.**

[![QGIS](https://img.shields.io/badge/QGIS-3.0%2B-93b023?logo=qgis&logoColor=white)](https://plugins.qgis.org/plugins/EasyFillet/)
[![Documentation](https://img.shields.io/badge/📖_Reference_Manual-13a0a0)](https://geophilo.com/EasyFillet/)
[![Version](https://img.shields.io/github/v/tag/YusufEminoglu/EasyFillet?label=version&color=blue)](https://github.com/YusufEminoglu/EasyFillet/releases)
[![License](https://img.shields.io/badge/license-GPL--3.0-orange)](LICENSE)
[![QGIS Plugin Hub](https://img.shields.io/badge/QGIS%20Hub-install-589632?logo=qgis&logoColor=white)](https://plugins.qgis.org/plugins/EasyFillet/)

</div>

---

## 📖 Documentation

**[Comprehensive Academic Reference Manual](https://geophilo.com/EasyFillet/)** — complete documentation of every feature, parameter, and workflow. Hosted on Web Documentation.


## Why EasyFillet?

Rounding a corner between two line segments in plain QGIS means manual arc construction and tedious trimming. EasyFillet brings the drafting-grade fillet operation straight into QGIS vector editing: pick two segments, set a radius, and get a precise tangent arc with both source lines trimmed to meet it at a clean node.

## ✨ Features

- **Interactive two-segment selection** with live radius and chord-length preview.
- **True tangent arcs** — geometrically correct topology, not polyline approximations.
- **Automatic trimming** — source lines are cut to meet the arc at a perfect node.
- **Numeric-radius dialog** for precise, repeatable input.
- **Right-click Extend mode** — lengthen short segments before filleting.
- **CRS-robust** — works with any CRS and handles mixed-CRS layer pairs.

## 🚀 Installation

**From the QGIS Plugin Hub (recommended):** `Plugins → Manage and Install Plugins…` → search for **"EasyFillet"** → *Install*.

**From a release zip:** download the latest zip from [Releases](https://github.com/YusufEminoglu/EasyFillet/releases) → `Plugins → Install from ZIP`.

Requires QGIS 3.0 or newer. No external Python dependencies.

## 📖 Quick start

1. Open an editable line layer.
2. Click the **EasyFillet** tool icon in the toolbar.
3. Click the first segment, then the second.
4. Enter the desired radius in the dialog and press **OK**.
5. The tangent arc is drawn and both lines are trimmed automatically.

Full version history: [CHANGELOG.md](CHANGELOG.md)

## 🧩 Part of the PlanX ecosystem

This plugin is one of 15 open-source QGIS plugins for urban planning by the same author:

| Planning & analysis | CAD & production | 3D & visualization |
|---|---|---|
| [PlanX](https://github.com/YusufEminoglu/EasyFillet) — spatial-planning suite | [PlanX CAD Toolset](https://github.com/YusufEminoglu/EasyFillet) — drafting-grade CAD | [PlanX 3D City](https://github.com/YusufEminoglu/EasyFillet) — Three.js city viewer |
| [GeoStats Lab](https://github.com/YusufEminoglu/EasyFillet) — spatial statistics | [EasyFillet](https://github.com/YusufEminoglu/EasyFillet) — tangent-arc fillet | [3D OSM Model](https://github.com/YusufEminoglu/EasyFillet) — OSM → 3D city in browser |
| [Suitability Lab](https://github.com/YusufEminoglu/EasyFillet) — raster MCDA | [Settlement Toolset](https://github.com/YusufEminoglu/EasyFillet) — 9-stage settlement plans | [OSM Quick 3D](https://github.com/YusufEminoglu/EasyFillet) — OSM → native QGIS 3D |
| [DataCube Lab](https://github.com/YusufEminoglu/EasyFillet) — spatiotemporal cubes | [UIP Toolset](https://github.com/YusufEminoglu/EasyFillet) — Turkish master-plan automation | [Urban Procedural 3D](https://github.com/YusufEminoglu/EasyFillet) — parametric zoning lab |
| [Urban Resilience](https://github.com/YusufEminoglu/EasyFillet) — 28 resilience tools | [ParcelFlux](https://github.com/YusufEminoglu/EasyFillet) — parcel subdivision | [CartoLab](https://github.com/YusufEminoglu/EasyFillet) — publication cartography |

## 📜 License & author

GPL-3.0 © [Yusuf Eminoğlu](https://github.com/YusufEminoglu) — bug reports and feature requests welcome in [Issues](https://github.com/YusufEminoglu/EasyFillet/issues).
