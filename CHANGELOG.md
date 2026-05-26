# Changelog

## [1.4.2] - 2026-05-26

- Maintenance release: refreshed Plugin Hub package after QGIS 3 and QGIS 4 compatibility validation.

All notable changes to **EasyFillet** are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) · versioning: [SemVer](https://semver.org/).

## [1.4.0] - 2026-05-20

Comprehensive correctness + UX revision. Existing single-tool structure preserved — no new sub-panels.

### Fixed
- **Shortest-arc bug** (`easyfillet_logic.create_fillet_and_trims`): the arc generator walked the unsigned `a2 < a1 → a2 += 2π` direction, which produced a 270° counter-clockwise sweep for half of 90° corners. The fix uses a signed angular diff clamped to (−π, π] so the shortest arc is always taken.
- **In-place trim** (`FilletMapTool._finish_fillet`): the two source line features are now updated via `layer.changeGeometry`. v1.3 emitted three new features (arc + two trimmed pieces) and left the originals untouched, so every corner ended up with five overlapping line features. A new "Trim originals in place" checkbox in the dialog (default on) controls the behaviour; flipping it off restores the v1.3 additive mode for users who scripted around it.
- **Extend mode** (`FilletMapTool._handle_extend_click`): the source line is actually extended via `changeGeometry` now. v1.3 committed a brand-new straight segment between the two clicks and never modified the original line, contradicting the preview the user saw while hovering.
- **`unload()` cleanup**: the map tool is detached from the canvas via `canvas.unsetMapTool()` before the reference is cleared. v1.3 left QGIS holding a dangling pointer that crashed on the next canvas interaction after the plugin was removed.
- **Nearest-feature search performance**: a per-layer `QgsSpatialIndex` is now built lazily and invalidated on `geometryChanged` / `featureAdded` / `featuresDeleted` / `editingStopped`. A four-step bbox probe narrows the candidate set to ~10 features before precise distance is measured. v1.3 scanned every feature on every move event (~50 ms per frame on 5 000-feature layers).

### Added
- `Esc` clears the current selection without exiting the tool (CAD convention).
- Modern `QDoubleSpinBox`-based dialog (replaces free-form `QLineEdit`):
  - Persisted radius, endpoint tolerance (px), arc segments, and "trim originals in place" flag via `QSettings` under `PlanX/EasyFillet`.
  - Helper text describes the click-flow and the `Space` re-open hotkey.
  - Backward-compatible `radiusLineEdit` shim so any external code keeps working.
- Status-bar feedback after each step: "First line selected", "Fillet applied (R=…, corner ≈ X°)", "Endpoint extended", etc.
- Tooltip on the toolbar action describing the click flow and `Space` hotkey.

### Internal
- `easyfillet_logic.create_fillet_and_trims` now also returns `center` and `angle_rad` in the result dict, used for the success-banner angle read-out.
- Shared `_single_line_pts` / `_single_line_geometry` helpers in `easyfillet.py` replace the duplicated multipart/single-part normalisation that was scattered across four call sites in v1.3.

## [1.3.1] - 2026

- Standardized Plugin Hub metadata, updated contact email, added DEU educational context, and refreshed the stable release package.

## [1.3.0]

- Added right-click Extend Mode for extending a selected endpoint until it intersects another line.

## [1.2.0]

- Added numeric radius input and chord-length preview.

## [1.1.0]

- Fixed snapping tolerance behavior for mixed CRS layers.
