import re
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pyvista as pv
import config as c

#----------------------------------------------------------------------------------------------------------------------------
# PATHS (define project root, locate simulation outputs, and prepare output directories for compaction post-processing)
#----------------------------------------------------------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent
# absolute path to the directory containing this compaction script
# used as the root reference so that all other project paths remain relative and portable

OUTPUT_ROOT = Path(getattr(c, "COMPACTION_OUT_DIR", PROJECT_ROOT / "DEM-Calibration-Project-Chrono"))
OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
# directory where all post-processing outputs from this script will be written
# includes per-slip overlay maps, aggregated CSVs, and cross-slip comparison outputs
# created automatically if it does not already exist

SETTLED_TERRAIN_CSV = (
    PROJECT_ROOT
    / c.SPHERE_TERRAIN_GEN_OUT_DIR
    / getattr(c, "SPHERE_TERRAIN_GEN_SETTLED_SUBDIR", "settled data")
    / f"{c.SPHERE_TERRAIN_GENERATION_SETTLED_DATA_FILE_NAME}.csv"
)
# path to the baseline settled terrain file generated before wheel loading
# this serves as the undeformed reference state against which compaction and settlement are measured
# FIXED: terrain generation writes the settled file inside the "settled data" subdirectory

SLIP_ROOT_DIR = PROJECT_ROOT / c.SLIP_SINKAGE_OUT_DIR
# root directory containing all slip-sinkage simulation trial folders
# each trial folder is expected to contain per-slip subfolders, and each slip folder contains
# terrain motion CSV files and wheel motion VTK files inside dedicated subdirectories

SLIP_TERRAIN_MOTION_SUBDIR = getattr(c, "SLIP_SINKAGE_TERRAIN_MOTION_SUBDIR", "terrain motion")
SLIP_WHEEL_MOTION_SUBDIR = getattr(c, "SLIP_SINKAGE_WHEEL_MOTION_SUBDIR", "wheel motion")
# subdirectory names inside each slip case folder
# FIXED: slip-sinkage outputs are nested under Trial X / Slip Y / {terrain motion, wheel motion, ...}

WHEEL_LABEL = getattr(c, "WHEEL_LABEL_st", "TREAD Coupon Wheel")
# descriptive label used in plot titles, legends, and summary file names


#----------------------------------------------------------------------------------------------------------------------------
# SETTINGS (define analysis-grid resolution, smoothing behavior, thresholding, and visualization controls)
#----------------------------------------------------------------------------------------------------------------------------

DX = 0.05
DY = 0.05
# grid spacing in x and y directions (m)
# terrain response is binned onto this structured grid to compute local top-surface elevation and packing fraction
# smaller grid spacing increases spatial resolution but may also increase noise from particle-scale fluctuations

N_TEMPLATES = 12
# number of terrain particle templates used during DEM terrain generation
# must match the number of particle-size templates created in the original simulation scripts

TERRAIN_GLOB = f"{c.SLIP_SINKAGE_TRIALS_MOTION_TERRAIN_FILE_NAME}_*.csv"
# filename pattern used to identify terrain motion snapshots for each slip trial

WHEEL_GLOB = f"{c.SLIP_SINKAGE_TRIALS_MOTION_WHEEL_FILE_NAME}_*.vtk"
# filename pattern used to identify wheel mesh snapshots for each slip trial
# these files are used to reconstruct the wheel center trajectory for overlay on compaction maps

SMOOTH_WIN_X = 3
SMOOTH_WIN_Y = 3
# spatial smoothing window size in grid cells
# applied after frame aggregation to reduce local numerical noise and reveal coherent terrain-response patterns

PLOT_FIELD = "compaction_max"
# field selected for visualization
# compaction_mean -> mean increase in local packing fraction over all frames
# compaction_max  -> maximum increase in local packing fraction over all frames
# settlement_mean -> mean downward terrain displacement over all frames
# settlement_max  -> maximum downward terrain displacement over all frames

COMPACTION_THRESHOLD = 1e-4
# threshold used to classify a grid cell as significantly compacted
# used in summary metrics such as impacted area

SUBTRACT_BACKGROUND = True
# whether to subtract a global background level from the plotted field
# useful when the response field has a weak nonzero offset over the entire domain

BACKGROUND_STAT = "median"
# statistic used to estimate the background level (median or mean)
# median is generally more robust when the field contains localized high-intensity regions

THRESHOLD_PERCENTILE = 92.0
MASK_BELOW_THRESHOLD = True
# visualization masking settings
# values below the selected percentile are hidden so that the strongest response regions dominate the displayed map

COLOR_VMIN_PERCENTILE = 5.0
COLOR_VMAX_PERCENTILE = 99.5
# percentile-based color scaling limits
# reduces sensitivity to outliers and improves the interpretability of the color map

MASKED_BACKGROUND_COLOR = "#355C9A"
# color assigned to masked / NaN regions in the overlay plot


#----------------------------------------------------------------------------------------------------------------------------
# HELPERS (utility functions for geometry, gridding, smoothing, file parsing, visualization, and summary metrics)
#----------------------------------------------------------------------------------------------------------------------------

def sphere_volume(r):
    # compute the volume of spherical particles from their radii
    # required for estimation of local solid volume fraction (packing fraction, phi)
    return (4.0 / 3.0) * np.pi * np.asarray(r) ** 3


def load_xyz_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        # ensure expected input file exists before attempting to load it
        raise FileNotFoundError(f"Missing file: {path}")

    # read CSV data into a pandas DataFrame
    df = pd.read_csv(path)

    required = ["X", "Y", "Z"]
    missing = [col for col in required if col not in df.columns]
    if missing:
        # validate that the file contains the minimum coordinate fields needed for spatial reconstruction
        raise ValueError(f"{path.name} missing columns {missing}. Found: {list(df.columns)}")

    # return loaded and validated terrain or particle data
    return df


def get_base_radius() -> float:
    if c.USE_DEMO_WHEEL_st:
        return float(c.BASE_TERRAIN_RAD_DEMO_st)

    # determine the base terrain particle radius from config.py
    # ensures post-processing uses the same terrain scale as the original simulation
    return float(c.BASE_TERRAIN_RAD_st)


def build_radius_map(radius_start: float, radius_increment: float, n_templates: int):
    mapping = {}
    r = radius_start

    for i in range(n_templates):
        mapping[f"{i}"] = r
        mapping[f"{i:02d}"] = r
        mapping[f"t{i}"] = r
        mapping[f"t{i:02d}"] = r
        r += radius_increment

    # construct a lookup table mapping clump-type identifiers to particle radii
    # supports multiple formatting conventions because clump_type may appear in CSVs as:
    # integer strings ("0", "1", ...)
    # zero-padded strings ("00", "01", ...)
    # template-labeled strings ("t0", "t1", ...)
    # radius_increment reproduces the slight polydispersity defined during terrain generation
    return mapping


def infer_radii(df: pd.DataFrame, radius_map, default_radius: float):
    if "r" in df.columns:
        # if the CSV explicitly stores radius per particle, use that directly
        return df["r"].astype(float).to_numpy()

    if "clump_type" in df.columns:
        # otherwise infer radius from clump_type using the radius map
        # any unknown particle types fall back to the default radius
        return (
            df["clump_type"]
            .astype(str)
            .str.strip()
            .map(radius_map)
            .fillna(default_radius)
            .to_numpy(dtype=float)
        )

    # final fallback: assume all particles have the same radius
    return np.full(len(df), default_radius, dtype=float)


def make_grid(x, y, dx, dy):
    x_edges = np.arange(np.min(x) - dx, np.max(x) + 2 * dx, dx)
    y_edges = np.arange(np.min(y) - dy, np.max(y) + 2 * dy, dy)

    # construct structured x- and y-grid edges spanning the terrain footprint
    # a margin is added around the data so edge particles are not excluded from the analysis domain
    return x_edges, y_edges


def digitize_points(x, y, x_edges, y_edges):
    ix = np.clip(np.digitize(x, x_edges) - 1, 0, len(x_edges) - 2)
    iy = np.clip(np.digitize(y, y_edges) - 1, 0, len(y_edges) - 2)

    # assign each particle center to a grid-cell index
    # clipping prevents out-of-range indices for points near the boundaries
    return ix, iy


def compute_top_surface_grid(df, x_edges, y_edges, radii):
    x = df["X"].to_numpy(float)
    y = df["Y"].to_numpy(float)
    z = df["Z"].to_numpy(float)
    # extract particle center coordinates

    ix, iy = digitize_points(x, y, x_edges, y_edges)
    # determine the grid cell occupied by each particle

    top = np.full((len(x_edges) - 1, len(y_edges) - 1), np.nan, dtype=float)
    # initialize grid of local terrain-surface elevations

    zsurf = z + radii
    # approximate local particle-top elevation as center elevation + particle radius
    # assumes spherical particles and uses the uppermost point of each sphere as a proxy for the terrain surface

    for k in range(len(df)):
        i, j = ix[k], iy[k]
        if np.isnan(top[i, j]) or zsurf[k] > top[i, j]:
            top[i, j] = zsurf[k]
            # store the highest particle-top elevation in each grid cell
            # this provides a discrete estimate of terrain free-surface topography

    return top


def compute_phi_grid(df, x_edges, y_edges, top_surface, z_bottom, radii):
    x = df["X"].to_numpy(float)
    y = df["Y"].to_numpy(float)
    # extract horizontal particle coordinates

    ix, iy = digitize_points(x, y, x_edges, y_edges)
    # determine spatial bins for all particles

    solid = np.zeros((len(x_edges) - 1, len(y_edges) - 1), dtype=float)
    # initialize accumulator for total particle solid volume in each cell

    vol = sphere_volume(radii)
    # compute particle volumes from radii

    for k in range(len(df)):
        solid[ix[k], iy[k]] += vol[k]
        # add the volume of each particle into the grid cell containing its center
        # this is a computationally simple approximation of local solid occupancy

    dx = float(x_edges[1] - x_edges[0])
    dy = float(y_edges[1] - y_edges[0])
    # compute cell width and height in the horizontal plane

    h = np.maximum(top_surface - z_bottom, 1e-8)
    # compute local terrain-column height from the common bottom surface up to the local top surface
    # lower-bounded to avoid division by zero

    cell_vol = dx * dy * h
    # total geometric volume of each analysis cell column

    phi = solid / cell_vol
    # local solid volume fraction (packing fraction)
    # this acts as the primary compaction metric: larger phi indicates denser local terrain packing

    phi[np.isnan(top_surface)] = np.nan
    # cells without a valid top surface remain undefined

    return phi


def extract_frame_number(path: Path):
    m = re.search(r"_(\d+)\.(csv|vtk)$", path.name)
    if not m:
        raise ValueError(f"Could not extract frame number from {path.name}")

    # parse numerical frame index from filenames ending in _####.csv or _####.vtk
    # used to sort terrain and wheel outputs in correct temporal order
    return int(m.group(1))


def moving_average_1d(arr, window):
    if window <= 1:
        # no smoothing requested -> return original data
        return arr.copy()

    kernel = np.ones(window, dtype=float)
    # uniform kernel for simple moving average

    valid = np.isfinite(arr).astype(float)
    # identify entries that contain valid numerical data

    filled = np.where(np.isfinite(arr), arr, 0.0)
    # replace NaNs with zero temporarily so convolution can proceed

    num = np.convolve(filled, kernel, mode="same")
    den = np.convolve(valid, kernel, mode="same")
    # numerator stores summed values in each window
    # denominator stores the number of valid contributions in each window

    out = np.full_like(arr, np.nan, dtype=float)
    mask = den > 0
    out[mask] = num[mask] / den[mask]
    # compute moving average only where at least one valid sample exists

    return out


def smooth_2d(arr, wx, wy):
    out = np.array(arr, dtype=float, copy=True)
    # create working copy of the 2D field

    if wx > 1:
        temp = np.full_like(out, np.nan, dtype=float)
        for j in range(out.shape[1]):
            temp[:, j] = moving_average_1d(out[:, j], wx)
        out = temp
        # apply smoothing in the x direction first

    if wy > 1:
        temp = np.full_like(out, np.nan, dtype=float)
        for i in range(out.shape[0]):
            temp[i, :] = moving_average_1d(out[i, :], wy)
        out = temp
        # then apply smoothing in the y direction
        # this separable filtering reduces spatial noise while preserving broad terrain-response trends

    return out


def read_wheel_center_from_vtk(path: Path):
    if not path.exists():
        # if the wheel mesh file is missing, return no center
        return None

    try:
        mesh = pv.read(path)
        # read the VTK wheel mesh using PyVista

        if mesh.points is None or len(mesh.points) == 0:
            # empty mesh -> cannot infer wheel center
            return None

        # approximate wheel center as the centroid of all wheel-mesh vertices
        # sufficient for overlaying wheel path on compaction maps
        return np.asarray(mesh.points, dtype=float).mean(axis=0)

    except Exception:
        # fail gracefully if a VTK file cannot be read
        return None


def save_aggregate_csv(x_edges, y_edges, phi0, comp_mean, comp_max, settle_mean, settle_max, out_csv):
    x_centers = 0.5 * (x_edges[:-1] + x_edges[1:])
    y_centers = 0.5 * (y_edges[:-1] + y_edges[1:])
    # compute center coordinates for each grid cell

    rows = []
    for i, xc in enumerate(x_centers):
        for j, yc in enumerate(y_centers):
            rows.append(
                {
                    "x": xc,
                    "y": yc,
                    "phi_initial": phi0[i, j],
                    "compaction_mean_over_frames": comp_mean[i, j],
                    "compaction_max_over_frames": comp_max[i, j],
                    "settlement_mean_over_frames": settle_mean[i, j],
                    "settlement_max_over_frames": settle_max[i, j],
                }
            )
            # flatten gridded response fields into row-wise tabular form
            # each row corresponds to one analysis cell in physical x-y space

    # save aggregated compaction/settlement data for further analysis outside this script
    pd.DataFrame(rows).to_csv(out_csv, index=False)


def prepare_display_grid(grid):
    g = np.array(grid, dtype=float, copy=True)
    # create working copy of the selected field for plotting

    finite = np.isfinite(g)
    if not np.any(finite):
        # if the grid contains no valid data, no display limits can be computed
        return g, None, None

    if SUBTRACT_BACKGROUND:
        if BACKGROUND_STAT == "mean":
            bg = np.nanmean(g)
        else:
            bg = np.nanmedian(g)

        g = g - bg
        g[g < 0.0] = 0.0
        # subtract global background level to emphasize localized response
        # values below background are clipped to zero because negative compaction has no physical meaning in this display context

    positive = np.isfinite(g) & (g > 0.0)
    if MASK_BELOW_THRESHOLD and np.any(positive):
        thresh = np.nanpercentile(g[positive], THRESHOLD_PERCENTILE)
        g = np.where(g >= thresh, g, np.nan)
        # mask weaker-response regions so that only the strongest terrain changes remain visible

    vals = g[np.isfinite(g)]
    if vals.size == 0:
        # after masking, there may be nothing left to plot
        return g, None, None

    vmin = np.nanpercentile(vals, COLOR_VMIN_PERCENTILE)
    vmax = np.nanpercentile(vals, COLOR_VMAX_PERCENTILE)
    # compute robust lower/upper color limits from percentiles

    if not np.isfinite(vmin) or not np.isfinite(vmax) or vmax <= vmin:
        vmin = np.nanmin(vals)
        vmax = np.nanmax(vals)
        # fallback if percentile-based color scaling becomes degenerate

    return g, vmin, vmax


def save_overlay_png(grid, x_edges, y_edges, wheel_xy, title, cbar_label, out_png):
    g, vmin, vmax = prepare_display_grid(grid)
    # preprocess selected grid for display and determine color scale

    finite_vals = g[np.isfinite(g)]
    if finite_vals.size == 0:
        # ensure there is still something to visualize after masking/background subtraction
        raise RuntimeError("Grid has no finite values to plot after masking.")

    cmap = plt.cm.viridis.copy()
    cmap.set_bad(MASKED_BACKGROUND_COLOR)
    # assign a distinct color to masked/undefined regions

    plt.figure(figsize=(10, 7))
    plt.imshow(
        g.T,
        origin="lower",
        extent=[x_edges[0], x_edges[-1], y_edges[0], y_edges[-1]],
        aspect="auto",
        vmin=vmin,
        vmax=vmax,
        cmap=cmap,
    )
    # display gridded field in physical coordinates
    # transpose is used so array indexing aligns correctly with plotting axes

    plt.colorbar(label=cbar_label)
    # add scalar legend showing field magnitude

    if wheel_xy is not None and len(wheel_xy) > 1:
        plt.plot(
            wheel_xy[:, 0],
            wheel_xy[:, 1],
            color="red",
            linewidth=3.0,
            label="wheel center path",
            zorder=5,
        )
        # overlay wheel trajectory on the terrain-response map

        plt.scatter(
            wheel_xy[0, 0],
            wheel_xy[0, 1],
            s=70,
            marker="o",
            facecolors="white",
            edgecolors="black",
            linewidths=1.2,
            label="start",
            zorder=6,
        )
        # mark the starting wheel position

        plt.scatter(
            wheel_xy[-1, 0],
            wheel_xy[-1, 1],
            s=70,
            marker="x",
            color="white",
            linewidths=2.0,
            label="end",
            zorder=6,
        )
        # mark the ending wheel position

        plt.legend(loc="upper right", framealpha=0.9)
        # add plot legend

    plt.xlabel("X [m]")
    plt.ylabel("Y [m]")
    plt.title(title)
    plt.tight_layout()
    plt.savefig(out_png, dpi=240)
    plt.close()
    # save high-resolution PNG overlay map


def summarize_compaction_metrics(compaction_mean_s, compaction_max_s, settlement_max_s, dx, dy, threshold):
    cell_area = dx * dy
    # horizontal area of one analysis cell

    positive_max = np.where(np.isfinite(compaction_max_s) & (compaction_max_s > 0.0), compaction_max_s, 0.0)
    positive_mean = np.where(np.isfinite(compaction_mean_s) & (compaction_mean_s > 0.0), compaction_mean_s, 0.0)
    positive_settlement = np.where(np.isfinite(settlement_max_s) & (settlement_max_s > 0.0), settlement_max_s, 0.0)
    # isolate positive response values for integral-style summary metrics

    impacted_mask = positive_max > threshold
    # define which cells are considered significantly compacted

    return {
        "peak_compaction_max": float(np.nanmax(compaction_max_s)),
        "peak_compaction_mean": float(np.nanmax(compaction_mean_s)),
        "mean_compaction_all_cells": float(np.nanmean(compaction_mean_s)),
        "mean_compaction_impacted_cells": float(np.nanmean(compaction_mean_s[impacted_mask])) if np.any(impacted_mask) else np.nan,
        "compaction_area_above_threshold_m2": float(np.sum(impacted_mask) * cell_area),
        "integrated_compaction_max_map_m2": float(np.sum(positive_max) * cell_area),
        "integrated_compaction_mean_map_m2": float(np.sum(positive_mean) * cell_area),
        "max_settlement_m": float(np.nanmax(settlement_max_s)),
        "integrated_settlement_max_map_m3_per_m": float(np.sum(positive_settlement) * cell_area),
    }
    # return scalar descriptors of terrain response:
    # peak_compaction_* -> strongest local densification
    # mean_compaction_* -> average densification intensity
    # compaction_area_above_threshold_m2 -> spatial footprint of substantial compaction
    # integrated_* maps -> area-integrated magnitudes useful for comparing runs globally


def build_summary_figure(results, out_path):
    n = len(results)
    fig, axes = plt.subplots(1, n, figsize=(5.5 * n, 5.2), constrained_layout=True)
    # create one subplot per slip case for side-by-side comparison

    if n == 1:
        axes = [axes]
        # ensure consistent iterable handling when only one panel exists

    for ax, result in zip(axes, results):
        g, vmin, vmax = prepare_display_grid(result["plot_grid"])
        vals = g[np.isfinite(g)]
        if vals.size == 0:
            # skip panels with no valid data after masking
            continue

        cmap = plt.cm.viridis.copy()
        cmap.set_bad(MASKED_BACKGROUND_COLOR)

        im = ax.imshow(
            g.T,
            origin="lower",
            extent=[result["x_edges"][0], result["x_edges"][-1], result["y_edges"][0], result["y_edges"][-1]],
            aspect="auto",
            vmin=vmin,
            vmax=vmax,
            cmap=cmap,
        )
        # draw selected field for this slip case

        wheel_xy = result["wheel_xy"]
        if wheel_xy is not None and len(wheel_xy) > 1:
            ax.plot(wheel_xy[:, 0], wheel_xy[:, 1], "r-", linewidth=2.2, label="wheel center path")
            ax.scatter(wheel_xy[0, 0], wheel_xy[0, 1], s=30, marker="o", facecolors="white", edgecolors="black", label="start")
            ax.scatter(wheel_xy[-1, 0], wheel_xy[-1, 1], s=30, marker="x", color="white", label="end")
            # overlay wheel path to show correspondence between contact path and terrain-response field

        ax.set_title(f"{WHEEL_LABEL}\nSlip {result['slip_display']}")
        ax.set_xlabel("X [m]")
        ax.set_ylabel("Y [m]")
        ax.legend(loc="upper right", fontsize=7, framealpha=0.9)

        cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
        cbar.set_label(result["cbar_label"])
        # add colorbar for each subplot

    fig.suptitle(f"{WHEEL_LABEL}: {PLOT_FIELD.replace('_', ' ').title()} Across Slip Conditions", fontsize=14)
    fig.savefig(out_path, dpi=240)
    plt.close(fig)
    # save final comparison figure across all processed slip values


def parse_slip_value_from_dirname(dirname: str):
    m = re.search(r"^Slip\s+([0-9.]+)$", dirname.strip())
    if not m:
        # reject directory names that do not match the expected slip-format convention
        return None

    raw = m.group(1)
    try:
        return float(raw)
    except ValueError:
        # convert slip substring to float for sorting and reporting
        return None


def discover_slip_dirs(root: Path):
    dirs = []
    if not root.exists():
        # ensure the slip-output root exists before trying to scan it
        raise FileNotFoundError(f"Slip root directory not found: {root}")

    for trial_path in sorted(root.iterdir()):
        if not trial_path.is_dir():
            # skip files at the trial level
            continue

        for slip_path in sorted(trial_path.iterdir()):
            if not slip_path.is_dir():
                # skip non-directory entries inside each trial directory
                continue

            slip = parse_slip_value_from_dirname(slip_path.name)
            if slip is None:
                # skip folders that are not valid slip-case directories
                continue

            dirs.append((slip, slip_path))
            # collect pairs of (slip value, slip-case directory path)

    # sort slip runs by numerical slip value so outputs appear in physically meaningful order
    # FIXED: scan Trial X / Slip Y layout produced by slipsinkage.py
    return sorted(dirs, key=lambda x: x[0])


#----------------------------------------------------------------------------------------------------------------------------
# MAIN (load baseline terrain, process all discovered slip cases, compute compaction/settlement maps, and save outputs)
#----------------------------------------------------------------------------------------------------------------------------

def main():
    print("Loading settled terrain:", SETTLED_TERRAIN_CSV)
    df0 = load_xyz_csv(SETTLED_TERRAIN_CSV)
    # load settled reference terrain before any wheel motion occurs

    base_radius = get_base_radius()
    radius_map = build_radius_map(base_radius, base_radius / 100.0, N_TEMPLATES)
    r0 = infer_radii(df0, radius_map, base_radius)
    # reconstruct radius information for the baseline terrain
    # radius increment is chosen to match the template progression used in terrain generation

    slip_runs = discover_slip_dirs(SLIP_ROOT_DIR)
    if not slip_runs:
        # automatically discover all available slip cases inside the slip output directory
        raise RuntimeError(f"No slip trial directories found in {SLIP_ROOT_DIR}")

    all_cases_out_dir = OUTPUT_ROOT / "compaction_overlay_maps"
    all_cases_out_dir.mkdir(parents=True, exist_ok=True)
    # create root output directory for all per-slip compaction maps and summary products

    results = []
    summary_rows = []
    # containers for cross-slip comparison products

    for slip, run_dir in slip_runs:
        slip_display = f"{slip:.3f}".rstrip("0").rstrip(".")
        # format slip value for readable file names and plot labels

        print("=" * 80)
        print(f"Processing slip {slip_display} in {run_dir}")
        print("=" * 80)

        terrain_dir = run_dir / SLIP_TERRAIN_MOTION_SUBDIR
        wheel_dir = run_dir / SLIP_WHEEL_MOTION_SUBDIR
        # FIXED: terrain and wheel outputs live inside dedicated subdirectories in each slip folder

        if not terrain_dir.exists():
            print(f"Skipping {slip_display}: missing terrain directory {terrain_dir}")
            continue

        terrain_files = sorted(terrain_dir.glob(TERRAIN_GLOB), key=extract_frame_number)
        wheel_files = sorted(wheel_dir.glob(WHEEL_GLOB), key=extract_frame_number) if wheel_dir.exists() else []
        # retrieve time-ordered terrain and wheel files for this slip case

        if not terrain_files:
            print(f"Skipping {slip_display}: no terrain files found in {terrain_dir}")
            # skip empty or incomplete runs with no terrain snapshots
            continue

        x_edges, y_edges = make_grid(df0["X"].to_numpy(float), df0["Y"].to_numpy(float), DX, DY)
        # build common spatial analysis grid based on the initial terrain footprint

        z_bottom = float(np.min(df0["Z"].to_numpy(float) - r0))
        # estimate global terrain bottom elevation from lowest particle-bottom point in the reference terrain

        top0 = compute_top_surface_grid(df0, x_edges, y_edges, r0)
        phi0 = compute_phi_grid(df0, x_edges, y_edges, top0, z_bottom, r0)
        # compute baseline terrain top surface and baseline packing fraction field
        # these represent the undeformed reference against which later states are compared

        comp_stack = []
        settle_stack = []
        # per-frame storage for compaction and settlement fields

        for frame_file in terrain_files:
            print("Processing:", frame_file.name)

            df = load_xyz_csv(frame_file)
            r = infer_radii(df, radius_map, base_radius)
            # load current frame and determine particle radii

            top = compute_top_surface_grid(df, x_edges, y_edges, r)
            # compute current terrain surface elevation map

            fill_mask = np.isnan(top) & np.isfinite(top0)
            top[fill_mask] = top0[fill_mask]
            # backfill empty/undefined cells with reference surface values
            # helps suppress spurious holes caused by sparse occupancy in a given frame

            phi = compute_phi_grid(df, x_edges, y_edges, top, z_bottom, r)
            # compute current local packing-fraction field

            fill_phi = np.isnan(phi) & np.isfinite(phi0)
            phi[fill_phi] = phi0[fill_phi]
            # backfill undefined packing-fraction cells with baseline values

            comp_stack.append(phi - phi0)
            # compaction defined as increase in local solid volume fraction relative to the reference terrain

            settle_stack.append(top0 - top)
            # settlement defined as downward displacement of the terrain surface relative to the reference surface

        comp_stack = np.stack(comp_stack, axis=0)
        settle_stack = np.stack(settle_stack, axis=0)
        # convert list of 2D response maps into 3D arrays with dimensions [time, x, y]

        with np.errstate(all="ignore"):
            comp_mean = np.nanmean(comp_stack, axis=0)
            comp_max = np.nanmax(comp_stack, axis=0)
            settle_mean = np.nanmean(settle_stack, axis=0)
            settle_max = np.nanmax(settle_stack, axis=0)
            # collapse temporal dimension into summary fields:
            # mean -> average terrain response over the whole simulation
            # max  -> strongest terrain response achieved at any time

        comp_mean[np.isnan(comp_mean)] = 0.0
        comp_max[np.isnan(comp_max)] = 0.0
        settle_mean[np.isnan(settle_mean)] = 0.0
        settle_max[np.isnan(settle_max)] = 0.0
        # replace remaining NaNs with zero so smoothing and summary statistics can proceed robustly

        comp_mean_s = smooth_2d(comp_mean, SMOOTH_WIN_X, SMOOTH_WIN_Y)
        comp_max_s = smooth_2d(comp_max, SMOOTH_WIN_X, SMOOTH_WIN_Y)
        settle_mean_s = smooth_2d(settle_mean, SMOOTH_WIN_X, SMOOTH_WIN_Y)
        settle_max_s = smooth_2d(settle_max, SMOOTH_WIN_X, SMOOTH_WIN_Y)
        # apply spatial smoothing to reduce particle-scale/bin-scale noise in the aggregated maps

        wheel_centers = []
        for wheel_file in wheel_files:
            center = read_wheel_center_from_vtk(wheel_file)
            if center is not None and np.all(np.isfinite(center)):
                wheel_centers.append(center)
                # collect wheel-center coordinates from all wheel snapshots

        wheel_xy = None
        if wheel_centers:
            wheel_xy = np.array(wheel_centers, dtype=float)[:, :2]
            # retain horizontal wheel-center trajectory only for 2D map overlays

        case_out_dir = all_cases_out_dir / f"slip_{slip_display}"
        case_out_dir.mkdir(parents=True, exist_ok=True)
        # create output directory dedicated to this slip case

        out_csv = case_out_dir / f"compaction_all_frames_slip_{slip_display}.csv"
        out_png = case_out_dir / f"compaction_all_frames_overlay_slip_{slip_display}.png"
        # define output filenames for the aggregated data table and overlay map

        save_aggregate_csv(
            x_edges,
            y_edges,
            phi0,
            comp_mean_s,
            comp_max_s,
            settle_mean_s,
            settle_max_s,
            out_csv,
        )
        # save per-cell aggregated results to CSV for downstream analysis or plotting

        if PLOT_FIELD == "settlement_mean":
            plot_grid = settle_mean_s
            title = f"Slip {slip_display} Terrain Settlement Map - Mean Over All Frames"
            cbar_label = "Settlement [m]"
        elif PLOT_FIELD == "settlement_max":
            plot_grid = settle_max_s
            title = f"Slip {slip_display} Terrain Settlement Map - Maximum Over All Frames"
            cbar_label = "Settlement [m]"
        elif PLOT_FIELD == "compaction_mean":
            plot_grid = comp_mean_s
            title = f"{WHEEL_LABEL}: Compaction Mean Over All Frames (Slip {slip_display})"
            cbar_label = "Compaction above background"
        elif PLOT_FIELD == "compaction_max":
            plot_grid = comp_max_s
            title = f"{WHEEL_LABEL}: Compaction Max Over All Frames (Slip {slip_display})"
            cbar_label = "Compaction above background"
        else:
            # choose which terrain-response field to visualize based on user-selected plotting mode
            raise ValueError(f"Unknown PLOT_FIELD: {PLOT_FIELD}")

        save_overlay_png(
            plot_grid,
            x_edges,
            y_edges,
            wheel_xy,
            title,
            cbar_label,
            out_png,
        )
        # save overlay PNG showing selected field plus wheel path

        metrics = summarize_compaction_metrics(
            comp_mean_s,
            comp_max_s,
            settle_max_s,
            DX,
            DY,
            COMPACTION_THRESHOLD,
        )
        # compute scalar summary metrics for this slip case

        metrics["wheel_label"] = WHEEL_LABEL
        metrics["slip"] = slip
        metrics["terrain_frames"] = len(terrain_files)
        metrics["wheel_frames"] = len(wheel_files)
        metrics["run_directory"] = str(run_dir)
        # append identifying metadata to the metric dictionary

        print(f"\nSaved CSV : {out_csv}")
        print(f"Saved PNG : {out_png}")
        print(f"Peak compaction max : {metrics['peak_compaction_max']:.6e}")
        print(f"Integrated compaction max map : {metrics['integrated_compaction_max_map_m2']:.6e}")
        print(f"Compaction area above threshold : {metrics['compaction_area_above_threshold_m2']:.6e}")
        # print key outputs and headline quantitative results to terminal

        results.append(
            {
                "metrics": metrics,
                "plot_grid": plot_grid,
                "wheel_xy": wheel_xy,
                "x_edges": x_edges,
                "y_edges": y_edges,
                "cbar_label": cbar_label,
                "slip": slip,
                "slip_display": slip_display,
            }
        )
        summary_rows.append(metrics)
        # store outputs for final cross-slip comparison

    if not results:
        # guard against empty processing in case no valid trial directories exist
        raise RuntimeError("No valid slip runs were processed.")

    summary_df = pd.DataFrame(summary_rows).sort_values(by="slip")
    summary_csv = all_cases_out_dir / f"{WHEEL_LABEL.lower().replace(' ', '_')}_comparison_summary.csv"
    summary_df.to_csv(summary_csv, index=False)
    print(f"Saved summary CSV : {summary_csv}")
    # save one summary table containing metrics for all processed slip cases

    summary_png = all_cases_out_dir / f"{WHEEL_LABEL.lower().replace(' ', '_')}_comparison_summary.png"
    build_summary_figure(results, summary_png)
    print(f"Saved summary figure : {summary_png}")
    # save one multi-panel comparison figure across all slip conditions


if __name__ == "__main__":
    # execute the compaction-analysis workflow when the script is run directly
    main()
