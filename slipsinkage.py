import config as c
import DEME
from DEME import PDSampler
import numpy as np
import random
import os
import pandas as pd


def slip_label(value):
    return f"{float(value):.6f}".rstrip("0").rstrip(".")

# ----------------------------------------------------------------------------------------------------------------------------
# PREPROCESSING (select wheel/terrain configuration, prepare output directory, define reference kinematics)
# ----------------------------------------------------------------------------------------------------------------------------

if c.USE_DEMO_WHEEL_st:
    WHEEL_RAD = c.WHEEL_RAD_DEMO_st
    WHEEL_WIDTH = c.WHEEL_WIDTH_DEMO_st
    WHEEL_WEIGHT = c.WHEEL_WEIGHT_DEMO_st
    WHEEL_MASS = c.WHEEL_MASS_DEMO_st
    BASE_TERRAIN_RAD = c.BASE_TERRAIN_RAD_DEMO_st
    WHEEL_IYY = c.WHEEL_IYY_DEMO_st
    WHEEL_IXX = c.WHEEL_IXX_DEMO_st
    WHEEL_OBJ_FILE = c.WHEEL_OBJ_FILE_DEMO_st
    TARGET_NORMAL_FORCE = c.TARGET_NORMAL_FORCE_DEMO_st
    SUPPLEMENTARY_FORCE = c.SUPPLEMENTARY_FORCE_DEMO_st
else:
    WHEEL_RAD = c.WHEEL_RAD_st
    WHEEL_WIDTH = c.WHEEL_WIDTH_st
    WHEEL_WEIGHT = c.WHEEL_WEIGHT_st
    WHEEL_MASS = c.WHEEL_MASS_st
    BASE_TERRAIN_RAD = c.BASE_TERRAIN_RAD_st
    WHEEL_IYY = c.WHEEL_IYY_st
    WHEEL_IXX = c.WHEEL_IXX_st
    WHEEL_OBJ_FILE = c.WHEEL_OBJ_FILE_st
    TARGET_NORMAL_FORCE = c.TARGET_NORMAL_FORCE_st
    SUPPLEMENTARY_FORCE = c.SUPPLEMENTARY_FORCE_st
# select wheel and terrain parameters (demo vs user-defined)

os.makedirs(c.SLIP_SINKAGE_OUT_DIR, exist_ok=True)
# create root directory for slip-sinkage outputs

WHEEL_ROLLING_RADIUS = getattr(c, "WHEEL_ROLLING_RADIUS_st", WHEEL_RAD)
WHEEL_ENVELOPE_RADIUS = getattr(c, "WHEEL_ENVELOPE_RADIUS_st", WHEEL_RAD)
WHEEL_REF_LINEAR_VEL = c.WHEEL_ANG_VEL_st * WHEEL_ROLLING_RADIUS
# reference rolling velocity (v = omega * R)

NUM_TRIALS = 1
# number of independent repeated trial groups


# ----------------------------------------------------------------------------------------------------------------------------
# OPTIONAL CONFIG FALLBACKS (support both old and updated config.py)
# ----------------------------------------------------------------------------------------------------------------------------

SPHERE_SETTLED_SUBDIR = getattr(c, "SPHERE_TERRAIN_GEN_SETTLED_SUBDIR", "settled data")
SLIP_TERRAIN_MOTION_SUBDIR = getattr(c, "SLIP_SINKAGE_TERRAIN_MOTION_SUBDIR", "terrain motion")
SLIP_WHEEL_MOTION_SUBDIR = getattr(c, "SLIP_SINKAGE_WHEEL_MOTION_SUBDIR", "wheel motion")
SLIP_CONTACT_FORCES_SUBDIR = getattr(c, "SLIP_SINKAGE_CONTACT_FORCES_SUBDIR", "contact forces")
SLIP_SETTLED_SUBDIR = getattr(c, "SLIP_SINKAGE_SETTLED_SUBDIR", "settled data")


# ----------------------------------------------------------------------------------------------------------------------------
# TRIAL LOOP (runs independent trial groups; each trial contains all prescribed slip cases)
# ----------------------------------------------------------------------------------------------------------------------------

for trial_num in range(NUM_TRIALS):

    # ------------------------------------------------------------------------------------------------------------------------
    # SLIP CASE LOOP (runs one simulation per slip value within the current trial)
    # ------------------------------------------------------------------------------------------------------------------------

    for slip_value in c.SLIP_VALUES_st:

        CURR_TERRAIN_RAD = BASE_TERRAIN_RAD
        # reset terrain particle radius for template reconstruction

        # --------------------------------------------------------------------------------------------------------------------
        # SOLVER SETUP
        # --------------------------------------------------------------------------------------------------------------------

        solver = DEME.DEMSolver()

        solver.SetMaxTriangleInBin(int(getattr(c, "MAX_TRIANGLES_IN_BIN_st", 100000)))
        solver.SetErrorOutAvgContacts(float(getattr(c, "ERROR_OUT_AVG_CONTACTS_st", 100.0)))
        solver.SetVerbosity("INFO")
        solver.SetOutputFormat("CSV")
        solver.SetOutputContent(["XYZ"])
        solver.SetContactOutputContent(["OWNER", "FORCE", "POINT"])
        solver.SetMaxVelocity(c.MAX_VELOCITY_st)
        solver.SetErrorOutVelocity(c.ERROR_OUT_VELOCITY_st)
        solver.SetInitTimeStep(c.STEP_SIZE_st)
        solver.SetGravitationalAcceleration(c.GRAVITATIONAL_ACCELERATION_st)

        # --------------------------------------------------------------------------------------------------------------------
        # MATERIAL + CONTACT MODEL
        # --------------------------------------------------------------------------------------------------------------------

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

        mat_type_wheel = solver.LoadMaterial(
            {
                "E": c.E_st,
                "nu": c.NU_st,
                "CoR": c.COR_st,
                "mu": c.MU_st,
                "Crr": c.CRR_st,
            }
        )

        solver.SetMaterialPropertyPair("mu", mat_type_wheel, mat_type_terrain, c.MU_contact_wheel_st)
        solver.SetMaterialPropertyPair("CoR", mat_type_wheel, mat_type_terrain, c.COR_contact_wheel_st)
        solver.SetMaterialPropertyPair("Cohesion", mat_type_wheel, mat_type_terrain, c.COHESION_contact_wheel_st)

        # --------------------------------------------------------------------------------------------------------------------
        # DOMAIN + WHEEL INITIALIZATION
        # --------------------------------------------------------------------------------------------------------------------

        bin_floor_z_loc = -c.DEPTH_st / 2.0

        solver.InstructBoxDomainDimension(
            [-c.WIDTH_st / 2, c.WIDTH_st / 2],
            [-c.LENGTH_st / 2, c.LENGTH_st / 2],
            [-c.DEPTH_st / 2, c.DEPTH_st / 2 + 10 * WHEEL_ENVELOPE_RADIUS],
        )

        solver.InstructBoxDomainBoundingBC("top_open", mat_type_terrain)
        solver.AddBCPlane([0, 0, bin_floor_z_loc], [0, 0, 1], mat_type_terrain)

        if c.USE_DEMO_WHEEL_st:
            wheel = solver.AddWavefrontMeshObject(DEME.GetDEMEDataFile(WHEEL_OBJ_FILE), mat_type_wheel, True, False)
        else:
            wheel = solver.AddWavefrontMeshObject(WHEEL_OBJ_FILE, mat_type_wheel, True, False)

        wheel.SetMass(WHEEL_MASS)
        wheel.SetMOI([WHEEL_IXX, WHEEL_IYY, WHEEL_IXX])
        wheel.SetFamily(1)
        wheel_tracker = solver.Track(wheel)

        # --------------------------------------------------------------------------------------------------------------------
        # MOTION PRESCRIPTION + SLIP CONTROL
        # --------------------------------------------------------------------------------------------------------------------

        kinematics_mode = getattr(c, "WHEEL_KINEMATICS_MODE_st", "fixed_angular_speed")
        if kinematics_mode == "fixed_linear_speed":
            slip_vel = float(c.WHEEL_LINEAR_VEL_st)
            wheel_ang_vel = slip_vel / ((1.0 - slip_value) * WHEEL_ROLLING_RADIUS)
        elif kinematics_mode == "fixed_angular_speed":
            wheel_ang_vel = float(c.WHEEL_ANG_VEL_st)
            slip_vel = wheel_ang_vel * WHEEL_ROLLING_RADIUS * (1.0 - slip_value)
        else:
            raise ValueError(f"Unknown wheel kinematics mode: {kinematics_mode}")

        solver.SetFamilyPrescribedAngVel(1, "0", f"{wheel_ang_vel}", "0", False)
        solver.AddFamilyPrescribedAcc(1, "none", "none", f"{(-SUPPLEMENTARY_FORCE / WHEEL_MASS)}")

        solver.SetFamilyPrescribedAngVel(2, "0", f"{wheel_ang_vel}", "0", False)
        solver.AddFamilyPrescribedAcc(2, "none", "none", f"{(-SUPPLEMENTARY_FORCE / WHEEL_MASS)}")
        # family 2 becomes active after initialization

        solver.SetFamilyPrescribedLinVel(2, f"{slip_vel}", "0", "none", False)

        # --------------------------------------------------------------------------------------------------------------------
        # TERRAIN RECONSTRUCTION
        # --------------------------------------------------------------------------------------------------------------------

        template_dict = {}

        for i in range(12):
            m = (CURR_TERRAIN_RAD**3) * c.TERRAIN_DENSITY_st * (4.0 / 3.0) * np.pi
            curr_template = solver.LoadSphereType(m, CURR_TERRAIN_RAD, mat_type_terrain)
            template_dict[f"{i:02d}"] = curr_template
            template_dict[f"t{i}"] = curr_template
            template_dict[f"t{i:02d}"] = curr_template
            CURR_TERRAIN_RAD += BASE_TERRAIN_RAD / 100.0
        # support multiple clump_type formats found in CSVs

        settled_terrain_csv = os.path.join(
            c.SPHERE_TERRAIN_GEN_OUT_DIR,
            SPHERE_SETTLED_SUBDIR,
            f"{c.SPHERE_TERRAIN_GENERATION_SETTLED_DATA_FILE_NAME}.csv",
        )

        df = pd.read_csv(settled_terrain_csv)
        # load settled terrain state produced by terraingeneration.py

        df["clump_type"] = df["clump_type"].astype(str).str.strip()

        def template_for_label(clump_type):
            key = clump_type
            if key not in template_dict:
                key = clump_type.zfill(2)
            if key not in template_dict:
                key = f"t{int(clump_type)}" if clump_type.isdigit() else clump_type.lower()
            if key not in template_dict:
                raise KeyError(f"Unknown clump_type in CSV: {clump_type}")
            return template_dict[key]

        xyz = df[["X", "Y", "Z"]].to_numpy(dtype=float)
        templates = [template_for_label(value) for value in df["clump_type"]]
        batch = solver.AddClumps(templates, xyz)
        batch.SetFamilies([0] * xyz.shape[0])
        # The mixed-template overload mirrors terrain generation and avoids a
        # PyDEME ambiguity when a single-template batch happens to contain three rows.
        if getattr(c, "TERRAIN_PARTICLE_SHAPE_st", "sphere") != "sphere":
            quat = df[["Qx", "Qy", "Qz", "Qw"]].to_numpy(dtype=float)
            batch.SetOriQ(quat.tolist())
        # reconstruct terrain as generated

        wheel.SetInitPos([0, 0, df["Z"].max() + CURR_TERRAIN_RAD + WHEEL_ENVELOPE_RADIUS + 0.1e-3])
        # place wheel just above terrain surface

        # --------------------------------------------------------------------------------------------------------------------
        # OUTPUT DIRECTORY SETUP
        # --------------------------------------------------------------------------------------------------------------------

        slip_name = slip_label(slip_value)
        folder_name = os.path.join(f"Trial {trial_num + 1}", f"Slip {slip_name}")
        out_dir = os.path.join(c.SLIP_SINKAGE_OUT_DIR, folder_name)

        terrain_motion_dir = os.path.join(out_dir, SLIP_TERRAIN_MOTION_SUBDIR)
        wheel_motion_dir = os.path.join(out_dir, SLIP_WHEEL_MOTION_SUBDIR)
        contact_forces_dir = os.path.join(out_dir, SLIP_CONTACT_FORCES_SUBDIR)
        settled_data_dir = os.path.join(out_dir, SLIP_SETTLED_SUBDIR)

        write_every = int(getattr(c, "SLIP_WRITE_EVERY_N_FRAMES_st", 100))
        write_terrain = bool(getattr(c, "SLIP_WRITE_TERRAIN_st", True))
        write_wheel = bool(getattr(c, "SLIP_WRITE_WHEEL_st", True))
        write_contact = bool(getattr(c, "SLIP_WRITE_CONTACT_st", True))

        if write_terrain:
            os.makedirs(terrain_motion_dir, exist_ok=True)
        if write_wheel:
            os.makedirs(wheel_motion_dir, exist_ok=True)
        if write_contact:
            os.makedirs(contact_forces_dir, exist_ok=True)
        os.makedirs(settled_data_dir, exist_ok=True)

        # --------------------------------------------------------------------------------------------------------------------
        # SIMULATION EXECUTION
        # --------------------------------------------------------------------------------------------------------------------

        solver.Initialize()

        frame_time = float(getattr(c, "SLIP_FRAME_TIME_S_st", 1e-3))
        t = 0.0
        frame = 0

        solver.DoDynamicsThenSync(0)
        solver.ChangeFamily(1, 2)
        # activate prescribed translational motion after initialization

        while t < c.TRIAL_RUN_TIME_SLIP_SINKAGE_st:

            if frame % write_every == 0:
                print(f"Frame: {frame}, Trial: {trial_num + 1}, Slip: {slip_value}")

                if write_terrain:
                    solver.WriteSphereFile(
                        os.path.join(
                            terrain_motion_dir,
                            f"{c.SLIP_SINKAGE_TRIALS_MOTION_TERRAIN_FILE_NAME}_{frame:04d}.csv",
                        )
                    )

                if write_wheel:
                    solver.WriteMeshFile(
                        os.path.join(
                            wheel_motion_dir,
                            f"{c.SLIP_SINKAGE_TRIALS_MOTION_WHEEL_FILE_NAME}_{frame:04d}.vtk",
                        )
                    )

                if write_contact:
                    solver.WriteContactFile(
                        os.path.join(
                            contact_forces_dir,
                            f"{c.SLIP_SINKAGE_TRIALS_CONTACT_FORCE_FILE_NAME}_{frame:04d}.csv",
                        )
                    )

            solver.DoDynamics(frame_time)
            t += frame_time
            frame += 1

        solver.WriteClumpFile(
            os.path.join(
                settled_data_dir,
                f"{c.SLIP_SINKAGE_TRIALS_SETTLED_DATA_FILE_NAME}_slip_{slip_name}.csv",
            )
        )
        # final terrain state after this slip case
