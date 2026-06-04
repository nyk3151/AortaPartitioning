# Aorta Partitioning

A [3D Slicer](https://www.slicer.org/) scripted module that partitions an aortic
segmentation into **vertebral-level segments** and reports the volume of each
segment per lumen (true / false).

It is an improved version of *Aorta Zone Splitter*: the dividing landmarks are
derived **automatically** from a vertebrae segmentation instead of being placed
by hand.

<!-- ![screenshot](Resources/Screenshots/overview.png) -->

## Features

- Input is a **Segmentation node** (converted internally to a labelmap aligned to the reference CT).
- Vertebral centroids are computed from a vertebrae segmentation; each centroid's
  Z-height is projected onto the centerline to create a named landmark
  (the descending / distal crossing is chosen when the height is met more than once).
- The aorta is split along the **centerline (arc-length based)**, so the cuts
  follow vessel curvature rather than flat axial planes.
- Segments are named by their bounding vertebrae and lumen type, e.g.
  `Th8-Th12_TrueLumen`, `Th12-L4_FalseLumen`.
- Per-segment volumes are exported to a results table.

## Requirements

- **3D Slicer 5.x** (uses `arrayFromSegmentBinaryLabelmap` with a reference volume).
- `numpy` (bundled with Slicer).
- `scipy` (for `cKDTree`). If it is not already available, install it from the
  Slicer Python console:
  ```python
  slicer.util.pip_install("scipy")
  ```

## Installation

**Manual (for development / testing)**

1. Clone this repository.
   ```bash
   git clone https://github.com/nyk3151/AortaPartitioning.git
   ```
2. In Slicer: *Edit → Application Settings → Modules → Additional module paths*,
   add the `AortaPartitioning/` module folder.
3. Restart Slicer. The module appears under the **Vascular** category.

*(Distribution through the Extensions Manager requires a separate submission to
the Slicer ExtensionsIndex; not covered here.)*

## Usage

1. Load the CT, the aorta segmentation, the centerline, and the vertebrae segmentation.
2. Open **Vascular → Aorta Partitioning** and set the inputs:
   - **Aorta Segmentation** – the aorta (lumen encoded as label values: `1` = true lumen, `2` = false lumen).
   - **Centerline** – a markups curve or model running through the aorta.
   - **Vertebrae Segmentation** – one segment per vertebra; segment names (e.g. `Th8`, `Th12`, `L4`) are used as landmark labels.
   - **Reference CT Volume** – the original CT, used as the geometry reference for all conversions.
3. Click **Run Analysis**.

### Outputs

| Node | Description |
| --- | --- |
| `Aorta_Landmarks` | Named fiducials at the centerline crossings |
| `Aorta_Partitioned_Segmentation` | The partitioned aorta (`<Vertebra>-<Vertebra>_<Lumen>`) |
| `Aorta_Partitioning_Results` | Table of per-segment volumes |
| `Analysis_Centerline_Model` / `Analysis_Centerline_Curve` | Smoothed centerline (visualization) |

## How it works

1. The aorta segmentation is exported to a labelmap on the reference CT grid.
2. The centerline is downsampled and re-densified with a spline filter.
3. For each vertebra, the RAS centroid is computed and its Z-height is matched to a
   point on the centerline (distal crossing when ambiguous).
4. Each aortic voxel is assigned to its nearest centerline node; landmark indices
   define the level boundaries via arc-length binning.
5. Levels and lumen type are encoded, imported as a segmentation, renamed, and
   measured with the Segment Statistics logic.

## Notes & limitations

- Landmarks above the aortic arch (e.g. upper thoracic levels) may match the
  centerline Z-height more than once; the module keeps the descending/distal
  crossing, which is appropriate for sub-arch levels (Th8 / Th12 / L4).
- Proximal/Distal end labels are inferred from centerline endpoint Z-heights.

## License

Released under the MIT License — see [`LICENSE`](LICENSE).
*(Switch to Apache-2.0 if you prefer; update this section and the `LICENSE` file accordingly.)*

## Acknowledgements

Developed for aortic dissection morphology analysis.
Portions of this module were developed with the assistance of Claude (Anthropic).

## Contact

nyk3151 — Tokyo Medical University
