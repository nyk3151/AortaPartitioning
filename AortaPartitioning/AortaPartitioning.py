import os
import unittest
import logging
import vtk, qt, ctk, slicer
from slicer.ScriptedLoadableModule import *
from slicer.util import VTKObservationMixin
import numpy as np
from scipy.spatial import cKDTree
import re
import SegmentStatistics

# =========================================================================
#  AortaPartitioning (Module Metadata)
# =========================================================================
class AortaPartitioning(ScriptedLoadableModule):
  def __init__(self, parent):
    ScriptedLoadableModule.__init__(self, parent)
    self.parent.title = "Aorta Partitioning"
    self.parent.categories = ["Vascular"]
    self.parent.dependencies = []
    self.parent.contributors = ["Yu Nakano (Tokyo Medical University)" ]
    self.parent.helpText = """
    Partitions an aortic segmentation into vertebral-level segments.
    Vertebral centroids are computed from a vertebrae segmentation, their
    Z-heights are projected onto the centerline (descending/distal crossing),
    and the aorta labelmap is split along the centerline (perpendicular /
    arc-length based partitioning). Segment volumes per level and lumen type
    are exported to a table.
    """
    self.parent.acknowledgementText = """
    Portions of this module were developed with the assistance of Claude (Anthropic).
    """

# =========================================================================
#  AortaPartitioningWidget (GUI)
# =========================================================================
class AortaPartitioningWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):
  def __init__(self, parent=None):
    ScriptedLoadableModuleWidget.__init__(self, parent)
    VTKObservationMixin.__init__(self)
    self.logic = None

  def setup(self):
    ScriptedLoadableModuleWidget.setup(self)

    # --- UI Layout ---
    parametersCollapsibleButton = ctk.ctkCollapsibleButton()
    parametersCollapsibleButton.text = "Inputs"
    self.layout.addWidget(parametersCollapsibleButton)
    parametersFormLayout = qt.QFormLayout(parametersCollapsibleButton)

    # 1. Aorta Segmentation Selector
    self.aortaSegSelector = slicer.qMRMLNodeComboBox()
    self.aortaSegSelector.nodeTypes = ["vtkMRMLSegmentationNode"]
    self.aortaSegSelector.selectNodeUponCreation = True
    self.aortaSegSelector.addEnabled = False
    self.aortaSegSelector.removeEnabled = False
    self.aortaSegSelector.noneEnabled = False
    self.aortaSegSelector.showHidden = False
    self.aortaSegSelector.setMRMLScene(slicer.mrmlScene)
    self.aortaSegSelector.setToolTip("Select the Aorta Segmentation (single segment encoding True/False lumen as label values)")
    parametersFormLayout.addRow("Aorta Segmentation:", self.aortaSegSelector)

    # 2. Centerline Selector
    self.centerlineSelector = slicer.qMRMLNodeComboBox()
    self.centerlineSelector.nodeTypes = ["vtkMRMLMarkupsCurveNode", "vtkMRMLModelNode"]
    self.centerlineSelector.selectNodeUponCreation = True
    self.centerlineSelector.addEnabled = False
    self.centerlineSelector.removeEnabled = False
    self.centerlineSelector.noneEnabled = False
    self.centerlineSelector.setMRMLScene(slicer.mrmlScene)
    self.centerlineSelector.setToolTip("Select the Centerline (Curve or Model)")
    parametersFormLayout.addRow("Centerline:", self.centerlineSelector)

    # 3. Vertebrae Segmentation Selector
    self.vertSegSelector = slicer.qMRMLNodeComboBox()
    self.vertSegSelector.nodeTypes = ["vtkMRMLSegmentationNode"]
    self.vertSegSelector.selectNodeUponCreation = True
    self.vertSegSelector.addEnabled = False
    self.vertSegSelector.removeEnabled = False
    self.vertSegSelector.noneEnabled = False
    self.vertSegSelector.setMRMLScene(slicer.mrmlScene)
    self.vertSegSelector.setToolTip("Select the Vertebrae Segmentation (one segment per vertebra, e.g. Th8/Th12/L4)")
    parametersFormLayout.addRow("Vertebrae Segmentation:", self.vertSegSelector)

    # 4. Reference CT Volume Selector (for geometry alignment)
    self.referenceVolumeSelector = slicer.qMRMLNodeComboBox()
    self.referenceVolumeSelector.nodeTypes = ["vtkMRMLScalarVolumeNode"]
    self.referenceVolumeSelector.selectNodeUponCreation = True
    self.referenceVolumeSelector.addEnabled = False
    self.referenceVolumeSelector.removeEnabled = False
    self.referenceVolumeSelector.noneEnabled = False
    self.referenceVolumeSelector.showHidden = False
    self.referenceVolumeSelector.setMRMLScene(slicer.mrmlScene)
    self.referenceVolumeSelector.setToolTip("Select the original CT volume used as geometry reference for labelmap conversion")
    parametersFormLayout.addRow("Reference CT Volume:", self.referenceVolumeSelector)

    # 5. Run Button
    self.applyButton = qt.QPushButton("Run Analysis")
    self.applyButton.enabled = False
    self.applyButton.toolTip = "Start processing"
    self.applyButton.setStyleSheet("font-weight: bold; font-size: 14px; min-height: 40px;")
    self.layout.addWidget(self.applyButton)

    # Status Label
    self.statusLabel = qt.QLabel("")
    self.layout.addWidget(self.statusLabel)

    self.layout.addStretch(1)

    # --- Connections ---
    self.aortaSegSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.updateGUIStates)
    self.centerlineSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.updateGUIStates)
    self.vertSegSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.updateGUIStates)
    self.referenceVolumeSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.updateGUIStates)
    self.applyButton.connect('clicked(bool)', self.onApplyButton)

    self.logic = AortaPartitioningLogic()
    self.updateGUIStates()

  def updateGUIStates(self):
    self.applyButton.enabled = (
      self.aortaSegSelector.currentNode() and
      self.centerlineSelector.currentNode() and
      self.vertSegSelector.currentNode() and
      self.referenceVolumeSelector.currentNode()
    )

  def onApplyButton(self):
    # Lock GUI
    self.applyButton.enabled = False
    self.statusLabel.setText("Processing... Please wait.")
    slicer.app.processEvents()

    try:
      self.logic.process(
        self.aortaSegSelector.currentNode(),
        self.centerlineSelector.currentNode(),
        self.vertSegSelector.currentNode(),
        self.referenceVolumeSelector.currentNode()
      )
      self.statusLabel.setText("Analysis Complete!")
    except Exception as e:
      self.statusLabel.setText(f"Error: {str(e)}")
      import traceback
      traceback.print_exc()

    self.applyButton.enabled = True

# =========================================================================
#  AortaPartitioningLogic (The Core Algorithm)
# =========================================================================
class AortaPartitioningLogic(ScriptedLoadableModuleLogic):

  def __init__(self):
    ScriptedLoadableModuleLogic.__init__(self)
    # Configuration
    self.LUMEN_MAPPING = {1: "TrueLumen", 2: "FalseLumen"}
    self.RANDOM_SEED = 12
    self.SUBDIVISION_LENGTH = 0.5
    self.NUM_CONTROL_POINTS = 20

  # -----------------------------------------------------------------------
  #  Centerline smoothing (reused from AortaZoneSplitter)
  # -----------------------------------------------------------------------
  def get_smooth_dense_centerline(self, centerlineNode):
    """Upsample and smooth the centerline using a Spline Filter."""
    if centerlineNode.IsA("vtkMRMLMarkupsCurveNode"):
        raw_polyData = centerlineNode.GetCurveWorld()
    elif centerlineNode.IsA("vtkMRMLModelNode"):
        raw_polyData = centerlineNode.GetPolyData()
    else:
        raise ValueError(f"Node '{centerlineNode.GetName()}' must be a MarkupsCurveNode or ModelNode.")

    if raw_polyData is None or raw_polyData.GetNumberOfPoints() == 0:
        raise ValueError("Centerline data is empty.")

    # 1. Downsample to remove noise
    points = vtk.util.numpy_support.vtk_to_numpy(raw_polyData.GetPoints().GetData())
    diffs = np.diff(points, axis=0)
    dists = np.linalg.norm(diffs, axis=1)
    cum_dist = np.insert(np.cumsum(dists), 0, 0.0)
    total_length = cum_dist[-1]

    target_dists = np.linspace(0, total_length, self.NUM_CONTROL_POINTS)
    control_points_array = np.zeros((self.NUM_CONTROL_POINTS, 3))
    for dim in range(3):
        control_points_array[:, dim] = np.interp(target_dists, cum_dist, points[:, dim])

    sparsePolyData = vtk.vtkPolyData()
    vPoints = vtk.vtkPoints()
    vPoints.SetData(vtk.util.numpy_support.numpy_to_vtk(control_points_array))
    sparsePolyData.SetPoints(vPoints)
    lines = vtk.vtkCellArray()
    lines.InsertNextCell(self.NUM_CONTROL_POINTS)
    for i in range(self.NUM_CONTROL_POINTS):
        lines.InsertCellPoint(i)
    sparsePolyData.SetLines(lines)

    # 2. Spline Interpolation for density
    splineFilter = vtk.vtkSplineFilter()
    splineFilter.SetInputData(sparsePolyData)
    splineFilter.SetSubdivideToLength()
    splineFilter.SetLength(self.SUBDIVISION_LENGTH)
    splineFilter.Update()

    return splineFilter.GetOutput()

  # -----------------------------------------------------------------------
  #  Step 0: Segmentation -> LabelMap (aligned to reference CT geometry)
  # -----------------------------------------------------------------------
  def _segmentation_to_labelmap(self, segNode, referenceVolumeNode, name):
    self._remove_node_by_name(name)
    labelmapNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLLabelMapVolumeNode", name)

    segIds = vtk.vtkStringArray()
    segNode.GetSegmentation().GetSegmentIDs(segIds)
    if segIds.GetNumberOfValues() == 0:
        raise ValueError(f"Segmentation '{segNode.GetName()}' has no segments.")

    ok = slicer.modules.segmentations.logic().ExportSegmentsToLabelmapNode(
        segNode, segIds, labelmapNode, referenceVolumeNode,
        slicer.vtkSegmentation.EXTENT_REFERENCE_GEOMETRY)
    if not ok:
        raise ValueError(f"Failed to export segmentation '{segNode.GetName()}' to labelmap.")
    return labelmapNode

  # -----------------------------------------------------------------------
  #  Step 3 helper: find centerline crossing at a given Z (distal side)
  # -----------------------------------------------------------------------
  def _find_centerline_crossing_index(self, smooth_points, target_z, distal_is_last):
    """Return the index on the centerline whose Z crosses target_z.
    When several crossings exist (e.g. arch), choose the descending/distal one."""
    z = smooth_points[:, 2]
    dz = z - target_z
    crossings = []
    for i in range(len(z) - 1):
        if dz[i] == 0.0:
            crossings.append(i)
        elif dz[i] * dz[i + 1] < 0.0:
            # crossing between i and i+1; snap to the nearer node
            frac = abs(dz[i]) / (abs(dz[i]) + abs(dz[i + 1]))
            crossings.append(i if frac < 0.5 else i + 1)
    if len(dz) > 0 and dz[-1] == 0.0:
        crossings.append(len(z) - 1)

    if not crossings:
        return None
    crossings = sorted(set(crossings))
    # distal end = caudal end. Pick crossing nearest to it.
    return crossings[-1] if distal_is_last else crossings[0]

  # -----------------------------------------------------------------------
  #  Step 2 + 3: vertebra centroids -> centerline crossings (landmarks)
  # -----------------------------------------------------------------------
  def _compute_landmarks(self, vertSegNode, referenceVolumeNode, smooth_points, distal_is_last):
    seg = vertSegNode.GetSegmentation()
    segIds = vtk.vtkStringArray()
    seg.GetSegmentIDs(segIds)

    ijkToRas = vtk.vtkMatrix4x4()
    referenceVolumeNode.GetIJKToRASMatrix(ijkToRas)

    landmarks = []  # list of (name, centerline_index, ras_point)
    for i in range(segIds.GetNumberOfValues()):
        segId = segIds.GetValue(i)
        name = seg.GetSegment(segId).GetName()

        # Binary labelmap in reference CT geometry -> IJK matches the CT grid
        arr = slicer.util.arrayFromSegmentBinaryLabelmap(vertSegNode, segId, referenceVolumeNode)
        if arr is None:
            logging.warning(f"Vertebra '{name}' has no labelmap; skipped.")
            continue
        vox = np.argwhere(arr > 0)  # rows of [z, y, x]
        if vox.shape[0] == 0:
            logging.warning(f"Vertebra '{name}' is empty; skipped.")
            continue

        mz, my, mx = vox.mean(axis=0)
        ras = [0.0, 0.0, 0.0, 0.0]
        ijkToRas.MultiplyPoint([mx, my, mz, 1.0], ras)
        target_z = ras[2]

        idx = self._find_centerline_crossing_index(smooth_points, target_z, distal_is_last)
        if idx is None:
            logging.warning(f"No centerline crossing for vertebra '{name}' (Z={target_z:.1f}); skipped.")
            continue
        landmarks.append((name, int(idx), smooth_points[idx].tolist()))

    if not landmarks:
        raise ValueError("No valid vertebral landmark could be projected onto the centerline.")

    # Sort proximal -> distal along the centerline index axis
    landmarks.sort(key=lambda t: t[1])
    return landmarks

  # -----------------------------------------------------------------------
  #  Build level -> region name map (vertebral boundaries)
  # -----------------------------------------------------------------------
  def _build_level_names(self, landmarks, proximal_is_first):
    asc_names = [lm[0] for lm in landmarks]  # already sorted by ascending centerline index
    n = len(asc_names)
    start_label = "Proximal" if proximal_is_first else "Distal"
    end_label = "Distal" if proximal_is_first else "Proximal"

    level_names = {}
    for lvl in range(1, n + 2):
        if lvl == 1:
            level_names[lvl] = f"{start_label}-{asc_names[0]}"
        elif lvl == n + 1:
            level_names[lvl] = f"{asc_names[-1]}-{end_label}"
        else:
            level_names[lvl] = f"{asc_names[lvl - 2]}-{asc_names[lvl - 1]}"
    return level_names

  # -----------------------------------------------------------------------
  #  Main process
  # -----------------------------------------------------------------------
  def process(self, aortaSegNode, centerlineNode, vertSegNode, referenceVolumeNode):
    logging.info('Processing started')
    from slicer.util import arrayFromVolume, updateVolumeFromArray

    # --- Step 0: Aorta Segmentation -> LabelMap (reference CT geometry) ---
    labelmapNode = self._segmentation_to_labelmap(
        aortaSegNode, referenceVolumeNode, "Temp_Aorta_LabelMap")

    # --- Step 1: Centerline Processing ---
    smooth_polyData = self.get_smooth_dense_centerline(centerlineNode)
    smooth_points = vtk.util.numpy_support.vtk_to_numpy(smooth_polyData.GetPoints().GetData())

    # Orientation: proximal (root) end is the more cranial (higher Z) endpoint.
    proximal_is_first = smooth_points[0, 2] >= smooth_points[-1, 2]
    distal_is_last = proximal_is_first

    # Visualization 1: Green Line Model
    vis_model_name = "Analysis_Centerline_Model"
    self._remove_node_by_name(vis_model_name)
    modelNode = slicer.modules.models.logic().AddModel(smooth_polyData)
    modelNode.SetName(vis_model_name)
    modelNode.GetDisplayNode().SetColor(0, 1, 0)
    modelNode.GetDisplayNode().SetLineWidth(2)

    # Visualization 2: Markups Curve (Control Points)
    vis_markup_name = "Analysis_Centerline_Curve"
    self._remove_node_by_name(vis_markup_name)
    markupCurveNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLMarkupsCurveNode", vis_markup_name)
    slicer.util.updateMarkupsControlPointsFromArray(markupCurveNode, smooth_points)
    markupCurveNode.GetDisplayNode().SetSelectedColor(1, 0, 0)  # Red
    markupCurveNode.GetDisplayNode().SetGlyphScale(0.5)
    markupCurveNode.GetDisplayNode().SetCurveLineSizeMode(slicer.vtkMRMLMarkupsDisplayNode.UseLineDiameter)

    # --- Step 2 + 3: Vertebra centroids -> centerline crossings (Fiducials) ---
    landmarks = self._compute_landmarks(vertSegNode, referenceVolumeNode, smooth_points, distal_is_last)

    # Place named Fiducial points
    fid_name = "Aorta_Landmarks"
    self._remove_node_by_name(fid_name)
    fidNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLMarkupsFiducialNode", fid_name)
    for (name, idx, ras) in landmarks:
        ptIndex = fidNode.AddControlPoint(vtk.vtkVector3d(ras[0], ras[1], ras[2]))
        fidNode.SetNthControlPointLabel(ptIndex, name)

    # --- Step 4: Splitting LabelMap (Method B: centerline arc-length partition) ---
    label_array = arrayFromVolume(labelmapNode)
    active_indices = np.where(label_array > 0)
    z, y, x = active_indices

    if len(x) == 0:
        raise ValueError("Aorta LabelMap is empty.")

    # IJK to RAS conversion
    ijk_to_ras = vtk.vtkMatrix4x4()
    labelmapNode.GetIJKToRASMatrix(ijk_to_ras)
    coords_ijk = np.vstack((x, y, z, np.ones_like(x))).T
    m = np.array([[ijk_to_ras.GetElement(r, c) for c in range(4)] for r in range(4)])
    coords_ras = (coords_ijk @ m.T)[:, :3]

    # Assign each voxel to its nearest centerline node, then bin by landmark indices
    tree = cKDTree(smooth_points)
    _, closest_centerline_indices = tree.query(coords_ras)
    boundary_indices = [lm[1] for lm in landmarks]
    bins = [0] + boundary_indices + [len(smooth_points)]
    voxel_levels = np.digitize(closest_centerline_indices, bins)

    # Encoding: Level * 100 + OriginalLumenValue
    original_values = label_array[z, y, x]
    encoded_values = (voxel_levels * 100) + original_values

    new_label_array = np.zeros_like(label_array)
    new_label_array[z, y, x] = encoded_values

    max_label_value = int(np.max(encoded_values)) if len(encoded_values) > 0 else 255

    # Region (level) -> name map using vertebral boundaries
    level_names = self._build_level_names(landmarks, proximal_is_first)

    # Temporary split LabelMap
    temp_label_name = "Temp_Split_LabelMap"
    self._remove_node_by_name(temp_label_name)
    outputLabelMap = slicer.modules.volumes.logic().CloneVolume(labelmapNode, temp_label_name)
    updateVolumeFromArray(outputLabelMap, new_label_array)

    # Temporary Color Table (Crucial for naming)
    color_node_name = "Temp_Analysis_ColorTable"
    self._remove_node_by_name(color_node_name)
    colorNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLColorTableNode", color_node_name)
    colorNode.SetTypeToUser()
    colorNode.SetNumberOfColors(max_label_value + 1)

    np.random.seed(self.RANDOM_SEED)
    for i in range(max_label_value + 1):
        colorNode.SetColor(i, np.random.random(), np.random.random(), np.random.random(), 1.0)
        colorNode.SetColorName(i, str(i))  # Explicit naming

    colorNode.SetColor(0, 0, 0, 0, 0)
    colorNode.SetColorName(0, "Background")
    outputLabelMap.GetDisplayNode().SetAndObserveColorNodeID(colorNode.GetID())

    # --- Step 5: Convert to Segmentation ---
    seg_node_name = "Aorta_Partitioned_Segmentation"
    self._remove_node_by_name(seg_node_name)

    segNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSegmentationNode", seg_node_name)
    segNode.CreateDefaultDisplayNodes()
    slicer.modules.segmentations.logic().ImportLabelmapToSegmentationNode(outputLabelMap, segNode)

    # Cleanup temps
    slicer.mrmlScene.RemoveNode(outputLabelMap)
    slicer.mrmlScene.RemoveNode(colorNode)
    slicer.mrmlScene.RemoveNode(labelmapNode)

    # Rename Segments using vertebral boundaries + lumen type
    segmentation = segNode.GetSegmentation()
    n_segments = segmentation.GetNumberOfSegments()

    for i in range(n_segments):
        segment_id = segmentation.GetNthSegmentID(i)
        segment = segmentation.GetSegment(segment_id)
        match = re.search(r'\d+', segment.GetName())
        if match:
            label_val = int(match.group())
            if label_val < 100:
                continue

            level = label_val // 100
            lumen_type_val = label_val % 100
            type_str = self.LUMEN_MAPPING.get(lumen_type_val, f"Type{lumen_type_val}")
            region = level_names.get(level, f"Level{level}")

            segment.SetName(f"{region}_{type_str}")

    # Set Opacity 0.5
    segDisplayNode = segNode.GetDisplayNode()
    if segDisplayNode:
        segDisplayNode.SetOpacity3D(0.5)
        segDisplayNode.SetVisibility3D(True)

    # --- Step 6: Statistics ---
    statsLogic = SegmentStatistics.SegmentStatisticsLogic()
    statsLogic.getParameterNode().SetParameter("Segmentation", segNode.GetID())
    statsLogic.getParameterNode().SetParameter("ScalarVolume", "")
    statsLogic.getParameterNode().SetParameter("LabelmapSegmentStatisticsPlugin.enabled", "True")
    statsLogic.getParameterNode().SetParameter("ScalarVolumeSegmentStatisticsPlugin.enabled", "False")

    statsLogic.computeStatistics()

    resultsTableNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLTableNode", "Aorta_Partitioning_Results")
    statsLogic.exportToTable(resultsTableNode)

    # Show Results
    layoutManager = slicer.app.layoutManager()
    if layoutManager:
        layoutManager.setLayout(3)  # FourUp

    slicer.app.applicationLogic().GetSelectionNode().SetReferenceActiveTableID(resultsTableNode.GetID())
    slicer.app.applicationLogic().PropagateTableSelection()

    logging.info('Processing completed')

  def _remove_node_by_name(self, name):
    try:
        node = slicer.util.getNode(name)
        slicer.mrmlScene.RemoveNode(node)
    except:
        pass

# =========================================================================
#  AortaPartitioningTest (Unit Test - Placeholder)
# =========================================================================
class AortaPartitioningTest(ScriptedLoadableModuleTest):
  def runTest(self):
    self.setUp()
    self.test_AortaPartitioning1()

  def setUp(self):
    slicer.mrmlScene.Clear(0)

  def test_AortaPartitioning1(self):
    self.delayDisplay("Starting the test")
    # Test logic here if needed
    self.delayDisplay('Test passed!')