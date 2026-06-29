import config as c
import DEME
import numpy as np
import pandas as pd
import os
from pathlib import Path

# ----------------------------------------------------------------------------------------------------------------------------
# BUCKET DRUM EXCAVATION WITH ROBUST OBJ-BOTTOM PLACEMENT + VTK OUTPUT
# ----------------------------------------------------------------------------------------------------------------------------
# Required run order:
#   1) python terraingeneration.py
#   2) python bucketdrum_excavation_surface_vtk.py
#
# What this script does:
#   - Loads the settled DEM terrain from terraingeneration.py.
#   - Loads bucketdrum.obj as a rigid DEME mesh.
#   - Computes the true local bottom of the OBJ from the OBJ vertices.
#   - Places that true mesh bottom at terrain_top_z - BUCKET_DRUM_CUT_DEPTH.
#       * BUCKET_DRUM_CUT_DEPTH = 0.0  -> just touching the terrain surface.
#       * BUCKET_DRUM_CUT_DEPTH > 0.0  -> starts embedded/cutting into the bed.
#   - Rotates the drum at adjustable RPM and translates it forward.
#   - Writes:
#       * terrain CSV frames
#       * terrain VTK point-cloud frames
#       * bucket drum VTK mesh frames
#       * contact-force CSV frames
#       * response CSV
#       * per-revolution capture/drop CSV
#       * ParaView .pvd collection files for terrain and drum animation
# ----------------------------------------------------------------------------------------------------------------------------


# ----------------------------------------------------------------------------------------------------------------------------
# USER-ADJUSTABLE SETTINGS
# ----------------------------------------------------------------------------------------------------------------------------

# Motion controls.
BUCKET_DRUM_RPM = getattr(c, "BUCKET_DRUM_RPM_st", 20.0)                    # rev/min
BUCKET_DRUM_TRAVEL_SPEED = getattr(c, "BUCKET_DRUM_TRAVEL_SPEED_st", 0.05)  # m/s, +X direction
ROTATION_SIGN = getattr(c, "BUCKET_DRUM_ROTATION_SIGN_st", 1.0)             # use -1 if it rotates the wrong way

# Placement control.
# For exact surface contact, set to 0.0.
# For actual excavation/cutting, use a positive value like 0.02 to 0.05 m.
BUCKET_DRUM_CUT_DEPTH = getattr(c, "BUCKET_DRUM_CUT_DEPTH_st", 0.05)         # m below terrain surface
BUCKET_DRUM_EXTRA_Z_OFFSET = getattr(c, "BUCKET_DRUM_Z_OFFSET_st", 0.0)      # optional manual correction, m

# Mesh and physical properties.
BUCKET_DRUM_OBJ_FILE = getattr(c, "BUCKET_DRUM_OBJ_FILE_st", "bucketdrum.obj")
BUCKET_DRUM_RADIUS = getattr(c, "BUCKET_DRUM_RADIUS_st", 0.15)              # used for inertia/capture estimate only
BUCKET_DRUM_WIDTH = getattr(c, "BUCKET_DRUM_WIDTH_st", 0.25)                # used for inertia/capture estimate only
BUCKET_DRUM_MASS = getattr(c, "BUCKET_DRUM_MASS_st", 12.0)                  # kg

BUCKET_DRUM_IYY = getattr(c, "BUCKET_DRUM_IYY_st", BUCKET_DRUM_MASS * BUCKET_DRUM_RADIUS**2 / 2.0)
BUCKET_DRUM_IXX = getattr(
    c,
    "BUCKET_DRUM_IXX_st",
    (BUCKET_DRUM_MASS / 12.0) * (3.0 * BUCKET_DRUM_RADIUS**2 + BUCKET_DRUM_WIDTH**2),
)

# Start location in the bin.
BUCKET_DRUM_START_X = getattr(c, "BUCKET_DRUM_START_X_st", -0.8)
BUCKET_DRUM_START_Y = getattr(c, "BUCKET_DRUM_START_Y_st", 0.0)

# Timing/output controls.
TRIAL_RUN_TIME = getattr(c, "TRIAL_RUN_TIME_BUCKET_DRUM_st", 8.0)
FRAME_TIME = getattr(c, "BUCKET_DRUM_FRAME_TIME_st", 1e-3)
WRITE_EVERY_N_FRAMES = getattr(c, "BUCKET_DRUM_WRITE_EVERY_N_FRAMES_st", 5)

# Geometric capture-estimate controls.
# This estimates material retained near/in the drum region. It is not exact bucket-cavity segmentation.
CAPTURE_RADIUS_FACTOR = getattr(c, "BUCKET_DRUM_CAPTURE_RADIUS_FACTOR_st", 0.95)
CAPTURE_WIDTH_FACTOR = getattr(c, "BUCKET_DRUM_CAPTURE_WIDTH_FACTOR_st", 0.95)


# ----------------------------------------------------------------------------------------------------------------------------
# OUTPUT PATHS
# ----------------------------------------------------------------------------------------------------------------------------

BUCKET_DRUM_OUT_DIR = getattr(c, "BUCKET_DRUM_OUT_DIR", "./bucket drum excavation output")
RUN_NAME = getattr(c, "BUCKET_DRUM_RUN_NAME_st", "surface_contact_vtk_run")
OUT_DIR = os.path.join(BUCKET_DRUM_OUT_DIR, RUN_NAME)

TERRAIN_MOTION_DIR = os.path.join(OUT_DIR, "terrain motion csv")
TERRAIN_VTK_DIR = os.path.join(OUT_DIR, "terrain vtk")
DRUM_MOTION_DIR = os.path.join(OUT_DIR, "bucket drum vtk")
CONTACT_FORCES_DIR = os.path.join(OUT_DIR, "contact forces")
SETTLED_DATA_DIR = os.path.join(OUT_DIR, "settled data")

for directory in [OUT_DIR, TERRAIN_MOTION_DIR, TERRAIN_VTK_DIR, DRUM_MOTION_DIR, CONTACT_FORCES_DIR, SETTLED_DATA_DIR]:
    os.makedirs(directory, exist_ok=True)

TERRAIN_FILE_NAME = getattr(c, "BUCKET_DRUM_TERRAIN_FILE_NAME", "bucket_drum_terrain_motion")
TERRAIN_VTK_FILE_NAME = "bucket_drum_terrain_particles"
DRUM_FILE_NAME = getattr(c, "BUCKET_DRUM_MOTION_FILE_NAME", "bucket_drum_motion")
CONTACT_FILE_NAME = getattr(c, "BUCKET_DRUM_CONTACT_FILE_NAME", "bucket_drum_contact_data")
RESPONSE_FILE_NAME = getattr(c, "BUCKET_DRUM_RESPONSE_FILE_NAME", "bucket_drum_response_data")
SETTLED_FILE_NAME = getattr(c, "BUCKET_DRUM_SETTLED_FILE_NAME", "bucket_drum_settled_data")
PER_REV_FILE_NAME = "bucket_drum_per_revolution_capture_drop"


# ----------------------------------------------------------------------------------------------------------------------------
# TERRAIN CONFIG FALLBACKS
# ----------------------------------------------------------------------------------------------------------------------------

SPHERE_SETTLED_SUBDIR = getattr(c, "SPHERE_TERRAIN_GEN_SETTLED_SUBDIR", "settled terrain data")

if c.USE_DEMO_WHEEL_st:
    BASE_TERRAIN_RAD = c.BASE_TERRAIN_RAD_DEMO_st
else:
    BASE_TERRAIN_RAD = c.BASE_TERRAIN_RAD_st


# ----------------------------------------------------------------------------------------------------------------------------
# HELPER FUNCTIONS
# ----------------------------------------------------------------------------------------------------------------------------

def make_terrain_templates(solver, mat_type_terrain, base_radius):
    template_dict = {}
    curr_radius = base_radius

    for i in range(12):
        mass = (curr_radius**3) * c.TERRAIN_DENSITY_st * (4.0 / 3.0) * np.pi
        curr_template = solver.LoadSphereType(mass, curr_radius, mat_type_terrain)

        template_dict[f"{i:02d}"] = curr_template
        template_dict[f"{i}"] = curr_template
        template_dict[f"t{i}"] = curr_template
        template_dict[f"t{i:02d}"] = curr_template

        curr_radius += base_radius / 100.0

    return template_dict


def template_for_clump_type(template_dict, clump_type):
    raw = str(clump_type).strip()
    keys_to_try = [raw, raw.zfill(2)]

    if raw.isdigit():
        keys_to_try.extend([f"t{int(raw)}", f"t{int(raw):02d}"])
    else:
        keys_to_try.append(raw.lower())

    for key in keys_to_try:
        if key in template_dict:
            return template_dict[key]

    raise KeyError(f"Unknown clump_type in settled terrain CSV: {clump_type}")


def radius_from_clump_type(clump_type, base_radius):
    raw = str(clump_type).strip().lower().replace("t", "")
    try:
        idx = int(raw)
    except ValueError:
        idx = 0
    return base_radius + idx * (base_radius / 100.0)


def infer_particle_mass_from_clump_type(clump_type, base_radius):
    radius = radius_from_clump_type(clump_type, base_radius)
    return (radius**3) * c.TERRAIN_DENSITY_st * (4.0 / 3.0) * np.pi


def terrain_top_surface_z(df_particles, base_radius):
    if "clump_type" in df_particles.columns:
        radii = np.array([radius_from_clump_type(v, base_radius) for v in df_particles["clump_type"].to_numpy()], dtype=float)
    elif "r" in df_particles.columns:
        radii = df_particles["r"].to_numpy(dtype=float)
    else:
        radii = np.full(len(df_particles), base_radius, dtype=float)
    return float(np.max(df_particles["Z"].to_numpy(dtype=float) + radii))


def get_settled_terrain_csv():
    candidates = [
        os.path.join(
            c.SPHERE_TERRAIN_GEN_OUT_DIR,
            SPHERE_SETTLED_SUBDIR,
            f"{c.SPHERE_TERRAIN_GENERATION_SETTLED_DATA_FILE_NAME}.csv",
        ),
        os.path.join(
            c.SPHERE_TERRAIN_GEN_OUT_DIR,
            "settled terrain data",
            f"{c.SPHERE_TERRAIN_GENERATION_SETTLED_DATA_FILE_NAME}.csv",
        ),
        os.path.join(
            c.SPHERE_TERRAIN_GEN_OUT_DIR,
            "settled data",
            f"{c.SPHERE_TERRAIN_GENERATION_SETTLED_DATA_FILE_NAME}.csv",
        ),
    ]

    for path in candidates:
        if os.path.exists(path):
            return path

    raise FileNotFoundError(
        "Could not find settled terrain CSV. Run python terraingeneration.py first. Tried:\n"
        + "\n".join(candidates)
    )


def read_obj_local_bounds(obj_path):
    vertices = []
    with open(obj_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if line.startswith("v "):
                parts = line.split()
                if len(parts) >= 4:
                    vertices.append([float(parts[1]), float(parts[2]), float(parts[3])])

    if not vertices:
        raise ValueError(f"No vertex lines beginning with 'v ' were found in OBJ file: {obj_path}")

    arr = np.asarray(vertices, dtype=float)
    return arr.min(axis=0), arr.max(axis=0)


def particles_inside_capture_zone(df_particles, drum_pos):
    """Approximate retained material as particles within a cylinder centered on the drum.

    Assumptions:
      - Drum axis is approximately Y.
      - Forward travel is X.
      - Vertical is Z.
    """
    x = df_particles["X"].to_numpy(dtype=float)
    y = df_particles["Y"].to_numpy(dtype=float)
    z = df_particles["Z"].to_numpy(dtype=float)

    dx = x - drum_pos[0]
    dy = y - drum_pos[1]
    dz = z - drum_pos[2]

    radial_dist = np.sqrt(dx**2 + dz**2)
    half_width = 0.5 * BUCKET_DRUM_WIDTH * CAPTURE_WIDTH_FACTOR
    capture_radius = BUCKET_DRUM_RADIUS * CAPTURE_RADIUS_FACTOR

    inside = (radial_dist <= capture_radius) & (np.abs(dy) <= half_width)
    return inside


def estimate_retained_mass(df_particles, drum_pos, base_radius):
    inside = particles_inside_capture_zone(df_particles, drum_pos)

    if "mass" in df_particles.columns:
        masses = df_particles["mass"].to_numpy(dtype=float)
    elif "Mass" in df_particles.columns:
        masses = df_particles["Mass"].to_numpy(dtype=float)
    elif "clump_type" in df_particles.columns:
        masses = np.array(
            [infer_particle_mass_from_clump_type(v, base_radius) for v in df_particles["clump_type"].to_numpy()],
            dtype=float,
        )
    else:
        masses = np.full(len(df_particles), infer_particle_mass_from_clump_type(0, base_radius), dtype=float)

    return float(np.sum(masses[inside])), int(np.sum(inside))


def csv_particles_to_legacy_vtk(csv_path, vtk_path, base_radius):
    """Write a simple VTK point-cloud file for ParaView.

    The particles are saved as vertices. In ParaView, use Glyph -> Sphere to visualize them as spheres.
    """
    df = pd.read_csv(csv_path)
    pts = df[["X", "Y", "Z"]].to_numpy(dtype=float)
    n = pts.shape[0]

    if "clump_type" in df.columns:
        type_ids = []
        radii = []
        for val in df["clump_type"].to_numpy():
            raw = str(val).strip().lower().replace("t", "")
            try:
                idx = int(raw)
            except ValueError:
                idx = 0
            type_ids.append(idx)
            radii.append(radius_from_clump_type(val, base_radius))
    else:
        type_ids = [0] * n
        radii = [base_radius] * n

    with open(vtk_path, "w", encoding="utf-8") as f:
        f.write("# vtk DataFile Version 3.0\n")
        f.write("DEME terrain particle centers\n")
        f.write("ASCII\n")
        f.write("DATASET POLYDATA\n")
        f.write(f"POINTS {n} float\n")
        for x, y, z in pts:
            f.write(f"{x:.9e} {y:.9e} {z:.9e}\n")

        f.write(f"VERTICES {n} {2*n}\n")
        for i in range(n):
            f.write(f"1 {i}\n")

        f.write(f"POINT_DATA {n}\n")
        f.write("SCALARS clump_type int 1\n")
        f.write("LOOKUP_TABLE default\n")
        for tid in type_ids:
            f.write(f"{tid}\n")

        f.write("SCALARS radius float 1\n")
        f.write("LOOKUP_TABLE default\n")
        for r in radii:
            f.write(f"{r:.9e}\n")


def write_pvd_collection(pvd_path, entries):
    """Create a ParaView time-series collection file.

    entries: list of (time, relative_file_path)
    """
    pvd_path = Path(pvd_path)
    with open(pvd_path, "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0"?>\n')
        f.write('<VTKFile type="Collection" version="0.1" byte_order="LittleEndian">\n')
        f.write('  <Collection>\n')
        for time_value, rel_file in entries:
            rel_file = str(rel_file).replace(os.sep, "/")
            f.write(f'    <DataSet timestep="{time_value:.9f}" group="" part="0" file="{rel_file}"/>\n')
        f.write('  </Collection>\n')
        f.write('</VTKFile>\n')


# ----------------------------------------------------------------------------------------------------------------------------
# SOLVER SETUP
# ----------------------------------------------------------------------------------------------------------------------------

solver = DEME.DEMSolver()

solver.SetVerbosity("INFO")
solver.SetOutputFormat("CSV")
solver.SetOutputContent(["XYZ"])
solver.SetContactOutputContent(["OWNER", "FORCE", "POINT"])
solver.SetMaxVelocity(c.MAX_VELOCITY_st)
solver.SetErrorOutVelocity(c.ERROR_OUT_VELOCITY_st)
solver.SetInitTimeStep(c.STEP_SIZE_st)
solver.SetGravitationalAcceleration(c.GRAVITATIONAL_ACCELERATION_st)


# ----------------------------------------------------------------------------------------------------------------------------
# MATERIALS
# ----------------------------------------------------------------------------------------------------------------------------

mat_type_terrain = solver.LoadMaterial(
    {
        "E": c.E_st,
        "nu": c.NU_st,
        "CoR": c.COR_st,
        "mu": c.MU_st,
        "Crr": c.CRR_st,
        "Cohesion": c.COHESION_st,
    }
)

mat_type_drum = solver.LoadMaterial(
    {
        "E": c.E_st,
        "nu": c.NU_st,
        "CoR": c.COR_st,
        "mu": c.MU_st,
        "Crr": c.CRR_st,
    }
)

solver.SetMaterialPropertyPair(
    "mu",
    mat_type_drum,
    mat_type_terrain,
    getattr(c, "MU_contact_bucket_drum_st", getattr(c, "MU_contact_wheel_st", 0.8)),
)
solver.SetMaterialPropertyPair(
    "CoR",
    mat_type_drum,
    mat_type_terrain,
    getattr(c, "COR_contact_bucket_drum_st", getattr(c, "COR_contact_wheel_st", 0.6)),
)
solver.SetMaterialPropertyPair(
    "Cohesion",
    mat_type_drum,
    mat_type_terrain,
    getattr(c, "COHESION_contact_bucket_drum_st", getattr(c, "COHESION_contact_wheel_st", 50.0)),
)


# ----------------------------------------------------------------------------------------------------------------------------
# DOMAIN
# ----------------------------------------------------------------------------------------------------------------------------

bin_floor_z_loc = -c.DEPTH_st / 2.0

solver.InstructBoxDomainDimension(
    [-c.WIDTH_st / 2.0, c.WIDTH_st / 2.0],
    [-c.LENGTH_st / 2.0, c.LENGTH_st / 2.0],
    [-c.DEPTH_st / 2.0, c.DEPTH_st / 2.0 + 10.0 * max(BUCKET_DRUM_RADIUS, BASE_TERRAIN_RAD)],
)

solver.InstructBoxDomainBoundingBC("top_open", mat_type_terrain)
solver.AddBCPlane([0, 0, bin_floor_z_loc], [0, 0, 1], mat_type_terrain)


# ----------------------------------------------------------------------------------------------------------------------------
# TERRAIN RECONSTRUCTION
# ----------------------------------------------------------------------------------------------------------------------------

template_dict = make_terrain_templates(solver, mat_type_terrain, BASE_TERRAIN_RAD)

settled_terrain_csv = get_settled_terrain_csv()
print("Loading settled terrain:", settled_terrain_csv)

df0 = pd.read_csv(settled_terrain_csv)
df0["clump_type"] = df0["clump_type"].astype(str).str.strip()

for clump_type, group in df0.groupby("clump_type"):
    template = template_for_clump_type(template_dict, clump_type)

    xyz = group[["X", "Y", "Z"]].to_numpy(dtype=float)
    quat = group[["Qw", "Qx", "Qy", "Qz"]].to_numpy(dtype=float)

    batch = solver.AddClumps(template, xyz)
    batch.SetFamilies([0] * xyz.shape[0])
    batch.SetOriQ(quat)

terrain_top_z = terrain_top_surface_z(df0, BASE_TERRAIN_RAD)
terrain_center_top_z = float(df0["Z"].max())


# ----------------------------------------------------------------------------------------------------------------------------
# BUCKET DRUM INITIALIZATION WITH TRUE OBJ-BOTTOM PLACEMENT
# ----------------------------------------------------------------------------------------------------------------------------

if not os.path.exists(BUCKET_DRUM_OBJ_FILE):
    raise FileNotFoundError(
        f"Bucket drum OBJ not found: {BUCKET_DRUM_OBJ_FILE}\n"
        "Put the OBJ in this folder or set BUCKET_DRUM_OBJ_FILE_st in config.py."
    )

obj_min, obj_max = read_obj_local_bounds(BUCKET_DRUM_OBJ_FILE)
obj_local_bottom_z = float(obj_min[2])
obj_local_top_z = float(obj_max[2])
obj_height = obj_local_top_z - obj_local_bottom_z

target_mesh_bottom_z = terrain_top_z - BUCKET_DRUM_CUT_DEPTH
# This is the key robust placement equation:
# world_bottom = origin_z + obj_local_bottom_z
# origin_z = target_world_bottom - obj_local_bottom_z
drum_start_z = target_mesh_bottom_z - obj_local_bottom_z + BUCKET_DRUM_EXTRA_Z_OFFSET

drum_start_pos = [BUCKET_DRUM_START_X, BUCKET_DRUM_START_Y, drum_start_z]

bucket_drum = solver.AddWavefrontMeshObject(BUCKET_DRUM_OBJ_FILE, mat_type_drum, True, False)
bucket_drum.SetMass(BUCKET_DRUM_MASS)
bucket_drum.SetMOI([BUCKET_DRUM_IXX, BUCKET_DRUM_IYY, BUCKET_DRUM_IXX])
bucket_drum.SetFamily(20)
bucket_drum.SetInitPos(drum_start_pos)

drum_tracker = solver.Track(bucket_drum)

actual_mesh_bottom_world_z = drum_start_z + obj_local_bottom_z
actual_mesh_top_world_z = drum_start_z + obj_local_top_z
actual_cut_depth = terrain_top_z - actual_mesh_bottom_world_z

print("-" * 96)
print("BUCKET DRUM PLACEMENT CHECK")
print(f"settled terrain CSV             : {settled_terrain_csv}")
print(f"terrain top center Z            : {terrain_center_top_z:.6f} m")
print(f"terrain top surface Z           : {terrain_top_z:.6f} m")
print(f"OBJ file                        : {BUCKET_DRUM_OBJ_FILE}")
print(f"OBJ local min xyz               : {obj_min}")
print(f"OBJ local max xyz               : {obj_max}")
print(f"OBJ local bottom Z              : {obj_local_bottom_z:.6f} m")
print(f"OBJ height                      : {obj_height:.6f} m")
print(f"requested cut depth             : {BUCKET_DRUM_CUT_DEPTH:.6f} m")
print(f"drum origin/start Z             : {drum_start_z:.6f} m")
print(f"actual mesh bottom world Z      : {actual_mesh_bottom_world_z:.6f} m")
print(f"actual mesh top world Z         : {actual_mesh_top_world_z:.6f} m")
print(f"actual cut depth                : {actual_cut_depth:.6f} m")
print("Interpretation:")
print("  actual cut depth = 0      -> just touching the top of the granular bed")
print("  actual cut depth > 0      -> starts inside the bed and should excavate")
print("  actual cut depth < 0      -> still floating above the bed")
print("-" * 96)


# ----------------------------------------------------------------------------------------------------------------------------
# PRESCRIBED MOTION
# ----------------------------------------------------------------------------------------------------------------------------

omega = ROTATION_SIGN * (2.0 * np.pi * BUCKET_DRUM_RPM / 60.0)

# Assumption: drum axis is Y, so angular velocity is about Y.
solver.SetFamilyPrescribedAngVel(20, "0", f"{omega}", "0", False)

# Forward excavation is along +X.
solver.SetFamilyPrescribedLinVel(20, f"{BUCKET_DRUM_TRAVEL_SPEED}", "0", "0", False)


# ----------------------------------------------------------------------------------------------------------------------------
# INSPECTORS / LOGGING
# ----------------------------------------------------------------------------------------------------------------------------

max_z_finder = solver.CreateInspector("clump_max_z")
mass_finder = solver.CreateInspector("clump_mass")

solver.Initialize()

response_rows = []
per_rev_rows = []
terrain_pvd_entries = []
drum_pvd_entries = []

last_spin_retained_mass = 0.0
last_spin_number = 0
revolutions_per_second = abs(BUCKET_DRUM_RPM) / 60.0


# ----------------------------------------------------------------------------------------------------------------------------
# SIMULATION LOOP
# ----------------------------------------------------------------------------------------------------------------------------

t = 0.0
frame = 0

while t < TRIAL_RUN_TIME:
    drum_pos = np.array(drum_tracker.Pos(), dtype=float)
    contact_acc = np.array(drum_tracker.ContactAcc(), dtype=float)
    contact_force = contact_acc * BUCKET_DRUM_MASS
    contact_force_mag = float(np.linalg.norm(contact_force))

    terrain_max_z = float(max_z_finder.GetValue())
    terrain_mass = float(mass_finder.GetValue())

    retained_mass = np.nan
    retained_count = -1

    if frame % WRITE_EVERY_N_FRAMES == 0:
        print(
            f"Frame {frame:06d} | t={t:.4f} s | "
            f"x={drum_pos[0]:.4f} z={drum_pos[2]:.4f} | "
            f"|F|={contact_force_mag:.6e} N"
        )

        terrain_csv = os.path.join(TERRAIN_MOTION_DIR, f"{TERRAIN_FILE_NAME}_{frame:04d}.csv")
        terrain_vtk = os.path.join(TERRAIN_VTK_DIR, f"{TERRAIN_VTK_FILE_NAME}_{frame:04d}.vtk")
        drum_vtk = os.path.join(DRUM_MOTION_DIR, f"{DRUM_FILE_NAME}_{frame:04d}.vtk")
        contact_csv = os.path.join(CONTACT_FORCES_DIR, f"{CONTACT_FILE_NAME}_{frame:04d}.csv")

        solver.WriteSphereFile(terrain_csv)
        solver.WriteMeshFile(drum_vtk)
        solver.WriteContactFile(contact_csv)

        try:
            csv_particles_to_legacy_vtk(terrain_csv, terrain_vtk, BASE_TERRAIN_RAD)
            terrain_pvd_entries.append((t, os.path.relpath(terrain_vtk, OUT_DIR)))
        except Exception as exc:
            print("Terrain VTK conversion skipped for frame", frame, "because:", exc)

        drum_pvd_entries.append((t, os.path.relpath(drum_vtk, OUT_DIR)))

        try:
            df_particles = pd.read_csv(terrain_csv)
            retained_mass, retained_count = estimate_retained_mass(df_particles, drum_pos, BASE_TERRAIN_RAD)
        except Exception as exc:
            print("Capture estimate skipped for frame", frame, "because:", exc)
            retained_mass, retained_count = np.nan, -1

    spin_number = int(np.floor(t * revolutions_per_second)) if revolutions_per_second > 0 else 0

    if spin_number > last_spin_number and np.isfinite(retained_mass):
        caught = max(0.0, retained_mass - last_spin_retained_mass)
        dropped = max(0.0, last_spin_retained_mass - retained_mass)

        per_rev_rows.append(
            {
                "spin_number": spin_number,
                "time_s": t,
                "drum_x": drum_pos[0],
                "drum_y": drum_pos[1],
                "drum_z": drum_pos[2],
                "retained_mass_kg": retained_mass,
                "caught_mass_since_last_spin_kg": caught,
                "dropped_mass_since_last_spin_kg": dropped,
                "retained_particle_count": retained_count,
                "rpm": BUCKET_DRUM_RPM,
                "travel_speed_m_per_s": BUCKET_DRUM_TRAVEL_SPEED,
                "cut_depth_m": BUCKET_DRUM_CUT_DEPTH,
            }
        )

        last_spin_retained_mass = retained_mass
        last_spin_number = spin_number

    response_rows.append(
        {
            "time_s": t,
            "frame": frame,
            "drum_x": drum_pos[0],
            "drum_y": drum_pos[1],
            "drum_z": drum_pos[2],
            "contact_fx": contact_force[0],
            "contact_fy": contact_force[1],
            "contact_fz": contact_force[2],
            "contact_force_mag": contact_force_mag,
            "terrain_max_z": terrain_max_z,
            "terrain_mass": terrain_mass,
            "retained_mass_kg": retained_mass,
            "retained_particle_count": retained_count,
            "rpm": BUCKET_DRUM_RPM,
            "omega_rad_per_s": omega,
            "travel_speed_m_per_s": BUCKET_DRUM_TRAVEL_SPEED,
            "cut_depth_m": BUCKET_DRUM_CUT_DEPTH,
            "obj_local_bottom_z": obj_local_bottom_z,
            "mesh_bottom_world_z_initial": actual_mesh_bottom_world_z,
            "terrain_top_surface_z_initial": terrain_top_z,
        }
    )

    solver.DoDynamics(FRAME_TIME)
    t += FRAME_TIME
    frame += 1


# ----------------------------------------------------------------------------------------------------------------------------
# FINAL OUTPUTS
# ----------------------------------------------------------------------------------------------------------------------------

response_csv = os.path.join(OUT_DIR, f"{RESPONSE_FILE_NAME}.csv")
pd.DataFrame(response_rows).to_csv(response_csv, index=False)
print(f"Saved response CSV with {len(response_rows)} rows: {response_csv}")

per_rev_csv = os.path.join(OUT_DIR, f"{PER_REV_FILE_NAME}.csv")
pd.DataFrame(per_rev_rows).to_csv(per_rev_csv, index=False)
print(f"Saved per-revolution capture/drop CSV: {per_rev_csv}")

settled_csv = os.path.join(SETTLED_DATA_DIR, f"{SETTLED_FILE_NAME}.csv")
solver.WriteClumpFile(settled_csv)
print(f"Saved final settled terrain CSV: {settled_csv}")

terrain_pvd = os.path.join(OUT_DIR, "terrain_particles_animation.pvd")
drum_pvd = os.path.join(OUT_DIR, "bucket_drum_animation.pvd")
combined_info = os.path.join(OUT_DIR, "README_visualization.txt")

write_pvd_collection(terrain_pvd, terrain_pvd_entries)
write_pvd_collection(drum_pvd, drum_pvd_entries)

with open(combined_info, "w", encoding="utf-8") as f:
    f.write("Open these files in ParaView:\n")
    f.write("  terrain_particles_animation.pvd\n")
    f.write("  bucket_drum_animation.pvd\n\n")
    f.write("For terrain particles:\n")
    f.write("  1. Select terrain_particles_animation.pvd.\n")
    f.write("  2. Apply.\n")
    f.write("  3. Add Filter -> Glyph.\n")
    f.write("  4. Glyph Type = Sphere.\n")
    f.write("  5. Scale Array = radius, or use a constant small scale if preferred.\n\n")
    f.write("For the bucket drum:\n")
    f.write("  1. Open bucket_drum_animation.pvd.\n")
    f.write("  2. Apply.\n")
    f.write("  3. Press Play in ParaView.\n")

print(f"Saved terrain ParaView animation collection: {terrain_pvd}")
print(f"Saved bucket drum ParaView animation collection: {drum_pvd}")
print(f"Saved visualization instructions: {combined_info}")
