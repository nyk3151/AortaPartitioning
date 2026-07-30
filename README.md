# Aorta Partitioning

[![Award](https://img.shields.io/badge/Award-JMAI%202026%20Excellent%20Presentation-gold?style=flat-square)](https://www.japan-medical-ai.org/jmaiaward)
[![Paper](https://img.shields.io/badge/Paper-Published-blue?style=flat-square)](https://doi.org/10.1007/s10278-026-02099-4)
[![Funding](https://img.shields.io/badge/Funding-KAKENHI_25K15998-brightgreen?style=flat-square)](https://kaken.nii.ac.jp/grant/KAKENHI-PROJECT-25K15998/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow?style=flat-square)](https://opensource.org/licenses/MIT)

A [3D Slicer](https://www.slicer.org/) scripted module that partitions an aortic
segmentation into **vertebral-level segments** and reports the volume of each
segment per lumen (true / false).

We proposed this method as **vertebral-based partitioning (VBP)** in our paper (https://doi.org/10.1007/s10278-026-02099-4).

The dividing landmarks are derived **automatically** from a vertebrae segmentation instead of being placed
by hand.

<p align="center">
  <img src="AortaPartitioning/Resources/Screenshots/overview.png" width="700" alt="Aorta Partitioning overview">
</p>

## Features

- Input is a **Segmentation node** (converted internally to a labelmap aligned to the reference CT).
- Vertebral centroids are computed from a vertebrae segmentation; each centroid's
  Z-height is projected onto the centerline to create a named landmark
  (the descending / distal crossing is chosen when the height is met more than once).
- The aorta is split along the **centerline (arc-length based)**, so the cuts
  follow vessel curvature rather than flat axial planes.
- Segments are named by their bounding vertebrae and lumen type, e.g.
  `Th9-Th12_TrueLumen`, `Th12-L2_FalseLumen`.
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

### Preparing the inputs

- **Segmentations** can be created with the **Segment Editor**, or with automatic
  AI tools such as
  [TotalSegmentator](https://github.com/lassoan/SlicerTotalSegmentator),
  [MONAI Auto3DSeg](https://github.com/lassoan/SlicerMONAIAuto3DSeg),
  [nnU-Net](https://github.com/MIC-DKFZ/nnUNet), or
  [MONAI Label](https://github.com/Project-MONAI/MONAILabel).
  - For **aortic dissection**, create the aorta as a single segmentation with
    label values **true lumen = 1** and **false lumen = 2**.
  We have developed deep learning segmentation models (nnU-Net, SwinUNETR, and U-Mamba). 
  The pre-trained models will be released soon.
  - For the **vertebrae**, TotalSegmentator or MONAI Auto3DSeg is convenient
    (each vertebra is produced as a separate, named segment such as `Th8`, `Th12`, `L4`).
- The **centerline** is created with the **Extract Centerline** module of the
  [VMTK extension](https://github.com/vmtk/SlicerExtension-VMTK)
  (install *SlicerVMTK* from the Extensions Manager).

### Running the analysis

1. Load the CT, the aorta segmentation, the centerline, and the vertebrae segmentation.
2. Open **Vascular → Aorta Partitioning** and set the inputs:
   - **Aorta Segmentation** – the aorta (lumen encoded as label values: `1` = true lumen, `2` = false lumen).
   - **Centerline** – a markups curve or model running through the aorta.
   - **Vertebrae Segmentation** – one segment per vertebra; segment names (e.g. `Th6`, 'Th9', `Th12`, `L4`) are used as landmark labels.
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
  centerline Z-height more than once; the module keeps the *descending/distal*
  crossing, which is appropriate for sub-arch levels.
- Proximal/Distal end labels are inferred from centerline endpoint Z-heights.

## License

Released under the MIT License — see [`LICENSE`](LICENSE).


## Acknowledgements

This work was supported by the Japan Society for the Promotion of Science (JSPS) KAKENHI (grant number JP [25K15998]).
Portions of this module were developed with the assistance of Claude (Anthropic).


## Citation

If you find this module or our work useful in your research, please cite our paper:

**BibTeX:**
```bibtex
@article{nakano2026aorta,
  title={AI-Based Segmental Volumetry of the Downstream Aorta in Aortic Dissection: End-to-End Versus Hybrid Strategies},
  author={Nakano, Yu and Nishi, S. and Kojima, I. and others},
  journal={Journal of Imaging Informatics in Medicine},
  year={2026},
  publisher={Springer},
  doi={10.1007/s10278-026-02099-4},
  url={[https://doi.org/10.1007/s10278-026-02099-4](https://doi.org/10.1007/s10278-026-02099-4)}
}
```

## Contact

Yu Nakano — Tokyo Medical University
nyk3151@tokyo-med.ac.jp 