import config as c
import DEME
from DEME import PDSampler
import csv
import numpy as np
import random
import os
import json

# ----------------------------------------------------------------------------------------------------------------------------
# PREPROCESSING (prepare output directories, select terrain particle scale, initialize setup)
# ----------------------------------------------------------------------------------------------------------------------------

os.makedirs(c.SPHERE_TERRAIN_GEN_OUT_DIR, exist_ok=True)
# create terrain-generation output directory if it does not already exist

motion_dir = os.path.join(c.SPHERE_TERRAIN_GEN_OUT_DIR, "settling terrain motion")
settled_dir = os.path.join(c.SPHERE_TERRAIN_GEN_OUT_DIR, "settled terrain data")
# dedicated subdirectories for time-resolved settling motion and final settled terrain state

os.makedirs(motion_dir, exist_ok=True)
os.makedirs(settled_dir, exist_ok=True)

SEED = int(getattr(c, "TERRAIN_RANDOM_SEED_st", 77))
# random seed for reproducible terrain generation

if c.USE_DEMO_WHEEL_st:
    BASE_TERRAIN_RAD = c.BASE_TERRAIN_RAD_DEMO_st
else:
    BASE_TERRAIN_RAD = c.BASE_TERRAIN_RAD_st
# terrain particle scale follows the active wheel configuration

CURR_TERRAIN_RAD = BASE_TERRAIN_RAD
# current particle radius, incremented during template creation to introduce mild polydispersity


# ----------------------------------------------------------------------------------------------------------------------------
# SOLVER SETUP
# ----------------------------------------------------------------------------------------------------------------------------

solver = DEME.DEMSolver()

solver.SetMaxTriangleInBin(int(getattr(c, "MAX_TRIANGLES_IN_BIN_st", 100000)))
solver.SetErrorOutAvgContacts(float(getattr(c, "ERROR_OUT_AVG_CONTACTS_st", 100.0)))
solver.SetVerbosity("INFO")
solver.SetOutputFormat("CSV")
solver.SetOutputContent(["XYZ"])
solver.SetMaxVelocity(c.MAX_VELOCITY_st)
solver.SetErrorOutVelocity(c.ERROR_OUT_VELOCITY_st)
solver.SetInitTimeStep(c.STEP_SIZE_st)
solver.SetGravitationalAcceleration(c.GRAVITATIONAL_ACCELERATION_st)


# ----------------------------------------------------------------------------------------------------------------------------
# MATERIAL DEFINITION
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


# ----------------------------------------------------------------------------------------------------------------------------
# PARTICLE TEMPLATES / SIZE DISTRIBUTION
# ----------------------------------------------------------------------------------------------------------------------------

templates_terrain = []
template_masses = []
template_radii = []

for i in range(12):
    m = (CURR_TERRAIN_RAD**3) * c.TERRAIN_DENSITY_st * (4.0 / 3.0) * np.pi
    curr_template = solver.LoadSphereType(m, CURR_TERRAIN_RAD, mat_type_terrain)
    curr_template.AssignName(f"t{i}")
    templates_terrain.append(curr_template)
    template_masses.append(m)
    template_radii.append(CURR_TERRAIN_RAD)

    CURR_TERRAIN_RAD += BASE_TERRAIN_RAD / 100.0
    # narrow particle-size distribution for more realistic packing

# after this loop, CURR_TERRAIN_RAD is slightly larger than the largest created template radius


# ----------------------------------------------------------------------------------------------------------------------------
# INITIAL PARTICLE PLACEMENT
# ----------------------------------------------------------------------------------------------------------------------------

rng = random.Random(SEED)

sampler = PDSampler(2.01 * CURR_TERRAIN_RAD)
# Poisson-disk-style spacing to reduce severe initial overlap

sample_halfwidth_x = (c.WIDTH_st / 2.0) - 2.0 * CURR_TERRAIN_RAD
sample_halfwidth_y = (c.LENGTH_st / 2.0) - 2.0 * CURR_TERRAIN_RAD

sample_z = (-c.DEPTH_st / 2.0) + 2.0 * CURR_TERRAIN_RAD
# begin slightly above the floor

num_particle = 0
generated_mass = 0.0
target_mass = getattr(c, "TERRAIN_TARGET_PARTICLE_MASS_KG_st", None)

while sample_z < c.FULL_HEIGHT_st or (target_mass is not None and generated_mass < target_mass):
    sample_center = np.array([0.0, 0.0, sample_z], dtype=float)
    sample_region = np.array([sample_halfwidth_x, sample_halfwidth_y, 1e-6], dtype=float)
    # very thin layer, effectively sampling one horizontal slice at a time

    particle_xyz = sampler.SampleBox(sample_center, sample_region)

    selected_indices = [rng.randrange(len(templates_terrain)) for _ in range(len(particle_xyz))]
    if target_mass is not None:
        retained = 0
        retained_mass = 0.0
        remaining_mass = target_mass - generated_mass
        if remaining_mass > 0:
            for index in selected_indices:
                retained += 1
                retained_mass += template_masses[index]
                if retained_mass >= remaining_mass:
                    break
        particle_xyz = particle_xyz[:retained]
        selected_indices = selected_indices[:retained]
    selected_templates = [templates_terrain[index] for index in selected_indices]
    if selected_templates:
        solver.AddClumps(selected_templates, particle_xyz)

    num_particle += len(particle_xyz)
    generated_mass += sum(template_masses[index] for index in selected_indices)
    sample_z += 2.01 * CURR_TERRAIN_RAD
    # advance to next layer

print(f"total num of particles: {num_particle}")
print(f"generated particle mass: {generated_mass:.6g} kg")


# ----------------------------------------------------------------------------------------------------------------------------
# DOMAIN AND BOUNDARY CONDITIONS
# ----------------------------------------------------------------------------------------------------------------------------

bin_floor_z_loc = -c.DEPTH_st / 2.0
domain_upper_z = max(c.DEPTH_st / 2.0 + 20.0 * CURR_TERRAIN_RAD, sample_z + 8.0 * CURR_TERRAIN_RAD)

solver.InstructBoxDomainDimension(
    [-c.WIDTH_st / 2, c.WIDTH_st / 2],
    [-c.LENGTH_st / 2, c.LENGTH_st / 2],
    [bin_floor_z_loc, domain_upper_z],
)

solver.InstructBoxDomainBoundingBC("top_open", mat_type_terrain)
solver.AddBCPlane([0, 0, bin_floor_z_loc], [0, 0, 1], mat_type_terrain)
print(f"terrain domain z: {bin_floor_z_loc:.6g} to {domain_upper_z:.6g} m")


# Optional density-controlled sample preparation follows the DEME cone-penetration demo.
target_bulk_density = getattr(c, "TERRAIN_TARGET_BULK_DENSITY_KG_M3_st", None)
compressor = None
compressor_tracker = None
if target_bulk_density is not None:
    compressor = solver.AddExternalObject()
    compressor.AddPlane([0, 0, 0], [0, 0, -1], mat_type_terrain)
    compressor.SetFamily(10)
    compressor.SetInitPos([0, 0, sample_z + 4.0 * CURR_TERRAIN_RAD])
    solver.SetFamilyFixed(10)
    compressor_tracker = solver.Track(compressor)


# ----------------------------------------------------------------------------------------------------------------------------
# SOLVER INITIALIZATION
# ----------------------------------------------------------------------------------------------------------------------------

solver.Initialize()


# ----------------------------------------------------------------------------------------------------------------------------
# TERRAIN SETTLING / DYNAMIC RELAXATION
# ----------------------------------------------------------------------------------------------------------------------------

settle_time = float(getattr(c, "TERRAIN_SETTLE_TIME_S_st", 1.0))
frame_time = float(getattr(c, "TERRAIN_FRAME_TIME_S_st", 1e-3))
write_every = int(getattr(c, "TERRAIN_WRITE_EVERY_N_FRAMES_st", 100))
write_motion = bool(getattr(c, "TERRAIN_WRITE_MOTION_st", False))

t = 0.0
frame = 0

while t < settle_time:
    if frame % write_every == 0:
        print(f"Frame: {frame}")

        if write_motion:
            solver.WriteSphereFile(
                os.path.join(
                    motion_dir,
                    f"{c.SPHERE_TERRAIN_GENERATION_MOTION_FILE_NAME}_{frame:04d}.csv"
                )
            )
        # fixed: use _0000 naming convention for consistency with the rest of the project

    solver.DoDynamics(frame_time)

    t += frame_time
    frame += 1


# Compress to the measured bulk density, then remove the preparation plane and relax.
preparation = {
    "generated_particle_count": num_particle,
    "generated_particle_mass_kg": generated_mass,
    "target_bulk_density_kg_m3": target_bulk_density,
}
settled_path = os.path.join(
    settled_dir,
    f"{c.SPHERE_TERRAIN_GENERATION_SETTLED_DATA_FILE_NAME}.csv",
)
settled_written = False


def surface_from_clump_csv(path):
    surface = None
    with open(path, newline="") as stream:
        for row in csv.DictReader(stream):
            label = str(row["clump_type"]).strip().lower()
            if label.startswith("t"):
                label = label[1:]
            radius = template_radii[int(label)]
            candidate = float(row["Z"]) + radius
            surface = candidate if surface is None else max(surface, candidate)
    if surface is None or not np.isfinite(surface):
        raise RuntimeError(f"Cannot measure a finite terrain surface from {path}")
    return surface


if target_bulk_density is not None:
    area = c.WIDTH_st * c.LENGTH_st
    frame_time = float(getattr(c, "TERRAIN_COMPRESSION_FRAME_TIME_S_st", 2e-3))
    compressor_speed = float(getattr(c, "TERRAIN_COMPRESSION_SPEED_M_S_st", 0.02))
    release_speed = float(
        getattr(c, "TERRAIN_COMPRESSION_RELEASE_SPEED_M_S_st", max(0.05, compressor_speed))
    )
    max_time = float(getattr(c, "TERRAIN_COMPRESSION_MAX_TIME_S_st", 10.0))
    release_margin = float(getattr(c, "TERRAIN_COMPRESSION_RELEASE_MARGIN_st", 0.02))
    # The generated template masses are exact and avoid a pyDEME clump_mass
    # inspector failure observed with mixed sphere templates. Surface heights
    # are likewise measured from synchronized CSV state rather than the unstable
    # pyDEME clump_max_z inspector.
    terrain_mass = generated_mass
    solver.DoDynamicsThenSync(0)
    precompression_path = os.path.join(c.SPHERE_TERRAIN_GEN_OUT_DIR, "precompression_state.csv")
    solver.WriteClumpFile(precompression_path)
    terrain_surface = surface_from_clump_csv(precompression_path)
    compressor_z = terrain_surface + 0.25 * CURR_TERRAIN_RAD
    compressor_release_z = compressor_z
    compressor_tracker.SetPos([0, 0, compressor_z])
    solver.DoDynamicsThenSync(0)
    bulk_density = terrain_mass / (area * (terrain_surface - bin_floor_z_loc))
    compression_time = 0.0
    target_compressor_z = bin_floor_z_loc + terrain_mass / (
        area * target_bulk_density * (1.0 + release_margin)
    )
    while compressor_z > target_compressor_z:
        compressor_z = max(target_compressor_z, compressor_z - compressor_speed * frame_time)
        compressor_tracker.SetPos([0, 0, compressor_z])
        solver.DoDynamicsThenSync(frame_time)
        compression_time += frame_time
        bulk_density = terrain_mass / (area * (compressor_z - bin_floor_z_loc))
        if int(compression_time / frame_time) % 100 == 0:
            print(f"compression density: {bulk_density:.6g} kg/m3")
        if compression_time >= max_time:
            raise RuntimeError(
                f"Terrain compression did not reach {target_bulk_density:g} kg/m3 within {max_time:g} s"
            )

    # Follow the DEME cone-penetration preparation: withdraw the plate at the
    # compression speed so stored elastic energy is released under control.
    release_time = 0.0
    release_steps = 0
    while compressor_z < compressor_release_z:
        compressor_z = min(compressor_release_z, compressor_z + release_speed * frame_time)
        compressor_tracker.SetPos([0, 0, compressor_z])
        solver.DoDynamicsThenSync(frame_time)
        release_time += frame_time
        release_steps += 1
        if release_steps % 100 == 0:
            print(f"controlled-release plate z: {compressor_z:.6g} m")

    solver.DoDynamicsThenSync(0)
    solver.DisableContactBetweenFamilies(0, 10)
    solver.DoDynamicsThenSync(float(getattr(c, "TERRAIN_POST_COMPRESSION_RELAX_S_st", 0.2)))
    solver.DoDynamicsThenSync(0)
    solver.WriteClumpFile(settled_path)
    settled_written = True
    terrain_surface = surface_from_clump_csv(settled_path)
    achieved_density = terrain_mass / (area * (terrain_surface - bin_floor_z_loc))
    preparation.update(
        {
            "compression_time_s": compression_time,
            "controlled_release_time_s": release_time,
            "compressed_to_density_kg_m3": bulk_density,
            "post_release_bulk_density_kg_m3": achieved_density,
            "post_release_bed_height_m": terrain_surface - bin_floor_z_loc,
        }
    )
    print(f"post-release bulk density: {achieved_density:.6g} kg/m3")


# ----------------------------------------------------------------------------------------------------------------------------
# FINAL SETTLED TERRAIN OUTPUT
# ----------------------------------------------------------------------------------------------------------------------------

if not settled_written:
    solver.WriteClumpFile(settled_path)
# final settled terrain used as the initial condition for later simulations

with open(os.path.join(c.SPHERE_TERRAIN_GEN_OUT_DIR, "terrain_preparation.json"), "w") as stream:
    json.dump(preparation, stream, indent=2, sort_keys=True)
    stream.write("\n")
