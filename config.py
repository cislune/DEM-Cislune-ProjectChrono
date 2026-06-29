import numpy as np

# ----------------------------------------------------------------------------------------------------------------------------
# SIMULATION MODE CONFIGURATION
# ----------------------------------------------------------------------------------------------------------------------------

MOVIE_TYPES_LIST = ["generation", "slip", "pressure plate"]
# generation -> settle particles to form terrain
# slip -> wheel slip/sinkage test
# pressure plate -> plate penetration test

TERRAIN_TYPES_LIST = ["sphere"]
# particle-based terrain (discrete spheres)

MOVIE_TYPE = MOVIE_TYPES_LIST[0]
# select experiment type (default: terrain generation)
# [1] -> slip
# [2] -> plate penetration

TERRAIN_TYPE = TERRAIN_TYPES_LIST[0]
# terrain representation (sphere-based)

DEFAULT_FRAMERATE = 60
# output visualization frame rate (frames per second, fps)

MOVIE_OUT_DIR = "./movies"
# directory for rendered simulation outputs


# ----------------------------------------------------------------------------------------------------------------------------
# SPHERE TERRAIN OUTPUT PATHS
# ----------------------------------------------------------------------------------------------------------------------------

SPHERE_TERRAIN_GEN_OUT_DIR = "./terrain generation output"
# root directory where terrain generation outputs are written

SPHERE_TERRAIN_GEN_MOTION_SUBDIR = "settling terrain motion"
# subdirectory for time-resolved terrain-settling motion

SPHERE_TERRAIN_GEN_SETTLED_SUBDIR = "settled terrain data"
# subdirectory for final settled terrain state

SPHERE_TERRAIN_GENERATION_MOTION_FILE_NAME = "terrain_settling_motion"
# time-resolved particle motion during terrain settling

SPHERE_TERRAIN_GENERATION_SETTLED_DATA_FILE_NAME = "settled_terrain_data"
# final settled particle state after generation


# ----------------------------------------------------------------------------------------------------------------------------
# SLIP-SINKAGE EXPERIMENT OUTPUT PATHS
# ----------------------------------------------------------------------------------------------------------------------------

SLIP_SINKAGE_OUT_DIR = "./slip sinkage output"
# root directory where slip-sinkage simulation outputs are written

SLIP_SINKAGE_TERRAIN_MOTION_SUBDIR = "terrain motion"
SLIP_SINKAGE_WHEEL_MOTION_SUBDIR = "wheel motion"
SLIP_SINKAGE_CONTACT_FORCES_SUBDIR = "contact forces"
SLIP_SINKAGE_SETTLED_SUBDIR = "settled data"
# standard subdirectory names inside each slip case folder

SLIP_SINKAGE_TRIALS_MOTION_TERRAIN_FILE_NAME = "slip_sinkage_terrain_motion"
# time-resolved terrain particle positions during slip-sinkage trials

SLIP_SINKAGE_TRIALS_MOTION_WHEEL_FILE_NAME = "slip_sinkage_wheel_motion"
# time-resolved wheel kinematics and mesh motion

SLIP_SINKAGE_TRIALS_CONTACT_FORCE_FILE_NAME = "slip_sinkage_contact_data"
# contact forces between wheel and terrain over time

SLIP_SINKAGE_TRIALS_SETTLED_DATA_FILE_NAME = "slip_sinkage_settled_data"
# settled terrain state at the end of slip-sinkage trials


# ----------------------------------------------------------------------------------------------------------------------------
# PRESSURE PLATE EXPERIMENT OUTPUT PATHS
# ----------------------------------------------------------------------------------------------------------------------------

PRESSURE_PLATE_OUT_DIR = "./pressure plate output"
# directory where pressure-plate simulation outputs are written

PRESSURE_PLATE_MOTION_TERRAIN_FILE_NAME = "pressure_plate_terrain_motion"
# time-resolved terrain particle positions written per frame as CSV

PRESSURE_PLATE_CONTACT_FORCE_FILE_NAME = "pressure_plate_contact_data"
# time-resolved plate-terrain contact data written per frame

PRESSURE_PLATE_RESPONSE_FILE_NAME = "pressure_plate_response_data"
# processed pressure-plate response data

PRESSURE_PLATE_SETTLED_DATA_FILE_NAME = "pressure_plate_settled_data"
# final terrain state at the end of the pressure-plate simulation

PRESSURE_PLATE_MOTION_PLATE_FILE_NAME = "pressure_plate_motion"
# time-resolved plate mesh output written per frame as VTK


# ----------------------------------------------------------------------------------------------------------------------------
# SOLVER / NUMERICAL INTEGRATION SETTINGS
# ----------------------------------------------------------------------------------------------------------------------------

MAX_VELOCITY_st = 30
# velocity cap to maintain numerical stability and avoid missed contacts

ERROR_OUT_VELOCITY_st = 30
# hard cutoff: abort simulation if exceeded (indicates instability)

G_MAG_st = 9.81
# gravitational acceleration magnitude (m/s^2)

GRAVITATIONAL_ACCELERATION_st = [0, 0, -G_MAG_st]
# gravity vector (z-down convention)

STEP_SIZE_st = 5e-6
# time step size (s)

TRIAL_RUN_TIME_SLIP_SINKAGE_st = 5.0
# duration for each slip-sinkage experiment (s)

TRIAL_RUN_TIME_PRESSURE_PLATE_st = 5.0
# duration for each pressure-plate experiment (s)

DOMAIN_EXPANSION_FACTOR_st = 4.0
# expands computational domain to mitigate boundary effects


# ----------------------------------------------------------------------------------------------------------------------------
# MATERIAL PROPERTIES: PARTICLE TERRAIN
# ----------------------------------------------------------------------------------------------------------------------------

E_st = 1e5
# Young's Modulus (Pa)

NU_st = 0.24
# Poisson's Ratio

COR_st = 0.9
# Coefficient of Restitution

MU_st = 0.3
# Static Friction Coefficient

CRR_st = 0.1
# Rolling Resistance Coefficient

COHESION_st = 50.0
# Cohesive strength

TERRAIN_DENSITY_st = 2.5e3
# Bulk density (kg/m^3)


# ----------------------------------------------------------------------------------------------------------------------------
# OBJECT-SPECIFIC CONTACT PARAMETERS
# ----------------------------------------------------------------------------------------------------------------------------

MU_contact_wheel_st = 0.8
# wheel-terrain friction coefficient

COR_contact_wheel_st = 0.6
# wheel-terrain coefficient of restitution

COHESION_contact_wheel_st = 50.0
# wheel-terrain cohesive strength

MU_contact_plate_st = 0.5
# plate-terrain friction coefficient


# ----------------------------------------------------------------------------------------------------------------------------
# WHEEL CONFIGURATION
# ----------------------------------------------------------------------------------------------------------------------------

USE_DEMO_WHEEL_st = True
# if True, use predefined demo wheel configuration
# if False, use user-defined wheel parameters below


# DEMO WHEEL

WHEEL_RAD_DEMO_st = 0.25
# demo wheel radius (m)

WHEEL_WIDTH_DEMO_st = 0.2
# demo wheel width (m)

WHEEL_WEIGHT_DEMO_st = 100.0
# demo wheel weight (N)

WHEEL_MASS_DEMO_st = WHEEL_WEIGHT_DEMO_st / G_MAG_st
# demo wheel mass (kg)

WHEEL_IYY_DEMO_st = WHEEL_MASS_DEMO_st * ((WHEEL_RAD_DEMO_st ** 2) / 2)
# spin-axis inertia

WHEEL_IXX_DEMO_st = (WHEEL_MASS_DEMO_st / 12) * ((3 * (WHEEL_RAD_DEMO_st ** 2)) + (WHEEL_WIDTH_DEMO_st ** 2))
# transverse inertia

WHEEL_OBJ_FILE_DEMO_st = "mesh/rover_wheels/viper_wheel_right.obj"
# demo wheel mesh

BASE_TERRAIN_RAD_DEMO_st = (((1344.3720907681325) / 1000) / 55) * 0.69
# base terrain particle radius for demo wheel case

TARGET_NORMAL_FORCE_DEMO_st = 200.0
# target total normal load (N)

SUPPLEMENTARY_FORCE_DEMO_st = TARGET_NORMAL_FORCE_DEMO_st - WHEEL_WEIGHT_DEMO_st
# additional downward force (N)


# ----------------------------------------------------------------------------------------------------------------------------
# USER-DEFINED WHEEL CONFIGURATION
# ----------------------------------------------------------------------------------------------------------------------------

WHEEL_RAD_st = 0.201
# wheel radius (m)

WHEEL_WIDTH_st = 0.08
# wheel width (m)

LOADS = [10.0, 40.0, 60.0]
# set of test masses (kg)

WHEEL_MASS_st = LOADS[0]
# selected wheel mass (kg)

WHEEL_WEIGHT_st = WHEEL_MASS_st * G_MAG_st
# wheel weight (N)

WHEEL_IYY_st = WHEEL_MASS_st * ((WHEEL_RAD_st ** 2) / 2)
# spin-axis inertia

WHEEL_IXX_st = (WHEEL_MASS_st / 12) * ((3 * (WHEEL_RAD_st ** 2)) + (WHEEL_WIDTH_st ** 2))
# transverse inertia

WHEEL_OBJ_FILE_st = "TREAD_Assembly.obj"
# custom wheel mesh

BASE_TERRAIN_RAD_st = ((1344.3720907681325) / 1000) / 50
# base particle radius for the terrain

TARGET_NORMAL_FORCE_st = WHEEL_WEIGHT_st
# target normal load (N)

SUPPLEMENTARY_FORCE_st = 0
# additional downward force (N)


# ----------------------------------------------------------------------------------------------------------------------------
# PRESSURE PLATE CONFIGURATION
# ----------------------------------------------------------------------------------------------------------------------------

PLATE_X_st = 1.4
# plate length in x (m)

PLATE_Y_st = 1.4
# plate width in y (m)

PLATE_THICK_st = 0.05
# plate thickness (m)

PLATE_MASS_st = 200.0
# plate mass (kg)

PLATE_VEL_st = 1e-3
# downward penetration velocity (m/s)

PLATE_OBJ_FILE_st = "pressureplate.obj"
# plate mesh file


# ----------------------------------------------------------------------------------------------------------------------------
# CONTAINER (BIN) GEOMETRY
# ----------------------------------------------------------------------------------------------------------------------------

WIDTH_st = 3.5
# bin width in x (m)

LENGTH_st = 3.5
# bin length in y (m)

DEPTH_st = 0.5
# bin depth in z (m)

FULL_HEIGHT_st = DEPTH_st / 2.0
# mid-depth reference height


# ----------------------------------------------------------------------------------------------------------------------------
# SLIP-SINKAGE TEST PARAMETERS
# ----------------------------------------------------------------------------------------------------------------------------

SLIP_VALUES_st = np.linspace(0.0, 0.6, 3)
# evaluated slip ratios

WHEEL_ANG_VEL_st = np.pi / 2
# prescribed wheel angular velocity (rad/s)


# ----------------------------------------------------------------------------------------------------------------------------
# BUCKET DRUM EXCAVATION OUTPUT PATHS
# ----------------------------------------------------------------------------------------------------------------------------

BUCKET_DRUM_OUT_DIR = "./bucket drum excavation output"
# root directory where bucket drum excavation outputs are written

BUCKET_DRUM_TERRAIN_FILE_NAME = "bucket_drum_terrain_motion"
# time-resolved terrain particle positions during bucket drum excavation

BUCKET_DRUM_MOTION_FILE_NAME = "bucket_drum_motion"
# time-resolved bucket drum mesh motion written as VTK

BUCKET_DRUM_CONTACT_FILE_NAME = "bucket_drum_contact_data"
# time-resolved bucket drum-terrain contact data

BUCKET_DRUM_RESPONSE_FILE_NAME = "bucket_drum_response_data"
# processed bucket drum response data, including position, velocity, force, torque proxy, and power proxy

BUCKET_DRUM_SETTLED_FILE_NAME = "bucket_drum_settled_data"
# final terrain state after bucket drum excavation


# ----------------------------------------------------------------------------------------------------------------------------
# BUCKET DRUM EXCAVATION CONFIGURATION
# ----------------------------------------------------------------------------------------------------------------------------

BUCKET_DRUM_OBJ_FILE_st = "bucketdrum.obj"
# bucket drum mesh file; put this OBJ in the project folder or replace with a relative path

BUCKET_DRUM_RADIUS_st = 0.15
# approximate bucket drum radius (m)

BUCKET_DRUM_WIDTH_st = 0.25
# approximate bucket drum width (m)

BUCKET_DRUM_MASS_st = 12.0
# bucket drum mass (kg)

BUCKET_DRUM_IYY_st = BUCKET_DRUM_MASS_st * ((BUCKET_DRUM_RADIUS_st ** 2) / 2.0)
# approximate spin-axis inertia for the bucket drum

BUCKET_DRUM_IXX_st = (BUCKET_DRUM_MASS_st / 12.0) * ((3.0 * (BUCKET_DRUM_RADIUS_st ** 2)) + (BUCKET_DRUM_WIDTH_st ** 2))
# approximate transverse inertia for the bucket drum

BUCKET_DRUM_ANG_VEL_st = 2.0 * np.pi * 20.0 / 60.0
# bucket drum angular velocity (rad/s); currently equivalent to 20 rpm

BUCKET_DRUM_TRAVEL_SPEED_st = 0.05
# forward excavation speed (m/s)

BUCKET_DRUM_CUT_DEPTH_st = 0.05
# initial embedment / cutting depth below the settled terrain surface (m)

TRIAL_RUN_TIME_BUCKET_DRUM_st = 8.0
# duration of bucket drum excavation simulation (s)

MU_contact_bucket_drum_st = 0.8
# bucket drum-terrain friction coefficient

COR_contact_bucket_drum_st = 0.6
# bucket drum-terrain coefficient of restitution

COHESION_contact_bucket_drum_st = 50.0
# bucket drum-terrain cohesive contact strength
