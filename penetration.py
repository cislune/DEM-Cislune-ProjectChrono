"""PyDEME cone-penetrometer simulation driven by cpt_case_runner.py."""

import csv
import math
import os

import DEME
import numpy as np
import pandas as pd

import config as c


os.makedirs(c.PENETROMETER_OUT_DIR, exist_ok=True)
contact_dir = os.path.join(c.PENETROMETER_OUT_DIR, "contact forces")
mesh_dir = os.path.join(c.PENETROMETER_OUT_DIR, "probe motion")
os.makedirs(contact_dir, exist_ok=True)
if c.PENETROMETER_WRITE_MESH_st:
    os.makedirs(mesh_dir, exist_ok=True)

solver = DEME.DEMSolver()
solver.SetMaxTriangleInBin(c.MAX_TRIANGLES_IN_BIN_st)
solver.SetErrorOutAvgContacts(c.ERROR_OUT_AVG_CONTACTS_st)
solver.SetVerbosity("INFO")
solver.SetOutputFormat("CSV")
solver.SetOutputContent(["XYZ"])
solver.SetContactOutputContent(["OWNER", "FORCE", "POINT"])
solver.SetMaxVelocity(c.MAX_VELOCITY_st)
solver.SetErrorOutVelocity(c.ERROR_OUT_VELOCITY_st)
solver.SetInitTimeStep(c.STEP_SIZE_st)
solver.SetGravitationalAcceleration(c.GRAVITATIONAL_ACCELERATION_st)

terrain_material = solver.LoadMaterial(
    {
        "E": c.E_st,
        "nu": c.NU_st,
        "CoR": c.COR_st,
        "mu": c.MU_st,
        "Crr": c.CRR_st,
        "Cohesion": c.COHESION_st,
    }
)
probe_material = solver.LoadMaterial(
    {
        "E": c.E_st,
        "nu": c.NU_st,
        "CoR": c.COR_st,
        "mu": c.MU_st,
        "Crr": c.CRR_st,
        "Cohesion": 0.0,
    }
)
solver.SetMaterialPropertyPair(
    "mu", probe_material, terrain_material, c.MU_contact_probe_st
)
solver.SetMaterialPropertyPair(
    "CoR", probe_material, terrain_material, c.COR_contact_probe_st
)
solver.SetMaterialPropertyPair(
    "Cohesion", probe_material, terrain_material, c.COHESION_contact_probe_st
)

floor_z = -c.DEPTH_st / 2.0
solver.InstructBoxDomainDimension(
    [-c.WIDTH_st / 2.0, c.WIDTH_st / 2.0],
    [-c.LENGTH_st / 2.0, c.LENGTH_st / 2.0],
    [floor_z, c.DEPTH_st / 2.0 + c.PENETROMETER_SHAFT_LENGTH_st + 0.1],
)
solver.InstructBoxDomainBoundingBC("top_open", terrain_material)
solver.AddBCPlane([0, 0, floor_z], [0, 0, 1], terrain_material)

base_radius = c.BASE_TERRAIN_RAD_st
current_radius = base_radius
templates = {}
template_radii = {}
for index in range(12):
    mass = current_radius**3 * c.TERRAIN_DENSITY_st * (4.0 / 3.0) * math.pi
    template = solver.LoadSphereType(mass, current_radius, terrain_material)
    templates[f"{index:02d}"] = template
    templates[f"t{index}"] = template
    templates[f"t{index:02d}"] = template
    template_radii[f"{index:02d}"] = current_radius
    template_radii[f"t{index}"] = current_radius
    template_radii[f"t{index:02d}"] = current_radius
    current_radius += base_radius / 100.0

settled_csv = os.path.join(
    c.SPHERE_TERRAIN_GEN_OUT_DIR,
    c.SPHERE_TERRAIN_GEN_SETTLED_SUBDIR,
    f"{c.SPHERE_TERRAIN_GENERATION_SETTLED_DATA_FILE_NAME}.csv",
)
terrain = pd.read_csv(settled_csv)
terrain["clump_type"] = terrain["clump_type"].astype(str).str.strip()


def template_for_label(label):
    key = label
    if key not in templates:
        key = label.zfill(2)
    if key not in templates:
        key = f"t{int(label)}" if label.isdigit() else label.lower()
    if key not in templates:
        raise KeyError(f"Unknown clump_type in CSV: {label}")
    return templates[key]


xyz = terrain[["X", "Y", "Z"]].to_numpy(dtype=float)
particle_templates = [template_for_label(value) for value in terrain["clump_type"]]
batch = solver.AddClumps(particle_templates, xyz)
batch.SetFamilies([0] * xyz.shape[0])


def radius_for_label(label):
    key = str(label).strip().lower()
    if key not in template_radii:
        key = key.zfill(2)
    if key not in template_radii and key.isdigit():
        key = f"t{int(key)}"
    return template_radii[key]


def terrain_top_from_frame(frame):
    return max(
        float(row.Z) + radius_for_label(row.clump_type)
        for row in frame.itertuples(index=False)
    )

probe = solver.AddWavefrontMeshObject(
    c.PENETROMETER_OBJ_FILE_st, probe_material, True, False
)
probe.SetMass(c.PENETROMETER_MASS_st)
probe.SetMOI([c.PENETROMETER_MASS_st * 0.01] * 3)
probe.SetFamily(11)
probe_tracker = solver.Track(probe)
terrain_top = terrain_top_from_frame(terrain)
probe_tip_z0 = terrain_top + c.PENETROMETER_CLEARANCE_st
probe.SetInitPos([0, 0, probe_tip_z0])
solver.SetFamilyFixed(11)
solver.DisableContactBetweenFamilies(0, 11)
solver.SetFamilyPrescribedLinVel(
    10, "0", "0", f"-{c.PENETROMETER_SPEED_st}", False
)
solver.SetFamilyPrescribedAngVel(10, "0", "0", "0", False)

solver.Initialize()
pre_relax = float(getattr(c, "PENETROMETER_PRE_RELAX_S_st", 0.0))
if pre_relax > 0:
    solver.DoDynamicsThenSync(pre_relax)
    relaxed_path = os.path.join(c.PENETROMETER_OUT_DIR, "prepenetration_relaxed_terrain.csv")
    solver.WriteClumpFile(relaxed_path)
    terrain_top = terrain_top_from_frame(pd.read_csv(relaxed_path))
probe_tip_z0 = terrain_top + c.PENETROMETER_CLEARANCE_st
probe_tracker.SetPos([0, 0, probe_tip_z0])
solver.DoDynamicsThenSync(0)
solver.ChangeFamily(11, 10)

frame_time = c.PENETROMETER_FRAME_TIME_S_st
write_every = c.PENETROMETER_WRITE_EVERY_N_FRAMES_st
run_time = (
    c.PENETROMETER_CLEARANCE_st + c.PENETROMETER_TARGET_DEPTH_st
) / c.PENETROMETER_SPEED_st
records = []
t = 0.0
frame = 0

while t < run_time:
    solver.DoDynamics(frame_time)
    t += frame_time
    frame += 1
    if frame % 100 == 0:
        print(
            f"penetration frame {frame}: commanded depth "
            f"{max(0.0, c.PENETROMETER_SPEED_st * t - c.PENETROMETER_CLEARANCE_st):.6g} m"
        )
    if frame % write_every:
        continue
    commanded_depth = max(0.0, c.PENETROMETER_SPEED_st * t - c.PENETROMETER_CLEARANCE_st)
    tip_z = probe_tip_z0 - c.PENETROMETER_SPEED_st * t
    contact_acceleration = np.asarray(probe_tracker.ContactAcc(), dtype=float)
    contact_force = contact_acceleration * c.PENETROMETER_MASS_st
    records.append(
        [
            frame,
            t,
            commanded_depth,
            tip_z,
            terrain_top,
            contact_force[0],
            contact_force[1],
            contact_force[2],
        ]
    )
    if c.PENETROMETER_WRITE_CONTACT_st:
        solver.WriteContactFile(
            os.path.join(contact_dir, f"cpt_contact_{frame:06d}.csv")
        )
    if c.PENETROMETER_WRITE_MESH_st:
        solver.WriteMeshFile(
            os.path.join(mesh_dir, f"cpt_probe_{frame:06d}.vtk")
        )

with open(os.path.join(c.PENETROMETER_OUT_DIR, "penetration_kinematics.csv"), "w", newline="") as stream:
    writer = csv.writer(stream)
    writer.writerow(
        [
            "frame",
            "time_s",
            "tip_depth_m",
            "tip_z_m",
            "initial_terrain_top_z_m",
            "contact_force_x_n",
            "contact_force_y_n",
            "contact_force_z_n",
        ]
    )
    writer.writerows(records)

solver.WriteClumpFile(
    os.path.join(c.PENETROMETER_OUT_DIR, "post_penetration_terrain.csv")
)
