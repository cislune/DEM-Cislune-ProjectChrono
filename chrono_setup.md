# Setup Instructions for PyChrono and PyDEME (Ubuntu)

This document explains how to install the required software, prepare the environment, and verify required assets for this project.

---

**1. Notes**

**Removing a conda environment**  
Use the following command to remove a conda environment:

```
conda env remove --name myenv
```

Replace `myenv` with the name of the environment to remove.

---

**Listing conda environments**  
Use:

```
conda env list
```

This displays all existing conda environments. The currently active environment is marked with an asterisk (*).

---

**2. Pre-Requisites**

**Check NVIDIA driver**  
Run:

```
nvidia-smi
```

The CUDA version shown in the top-right corner should be **12.8 or higher**. If the version is lower, update the NVIDIA driver before proceeding.

Resources:

- NVIDIA Driver Downloads: https://www.nvidia.com/Download/index.aspx  
- Linux Installation Guide: https://docs.nvidia.com/datacenter/tesla/driver-installation-guide/index.html  

---

**Install Miniconda3**  
Download the Miniconda shell installer:

https://www.anaconda.com/download/success  

Miniconda is a lightweight Python distribution that includes Conda for environment management.

Installation steps:

Make the installer executable:

```
sudo chmod +x shell_script_name.sh
```

Run the installer:

```
./shell_script_name.sh
```

Replace `shell_script_name.sh` with the actual filename you downloaded.

If issues occur, verify system requirements:

https://www.anaconda.com/docs/getting-started/miniconda/system-requirements

---

**3. Create Environment and Install Dependencies**

**Create and activate environment**  
Use:

```
conda create -n myenv python=3.12 -c conda-forge -y
conda activate myenv
```

`myenv` can be replaced with any preferred environment name. The `-y` flag skips confirmation prompts.

---

**Install PyChrono, PyDEME, and all required dependencies**  
Ensure the environment is activated before running:

```
conda install bochengzou::pychrono bochengzou::pydeme -c bochengzou -c conda-forge

conda install -c conda-forge imageio-ffmpeg pandas numpy matplotlib pyvista

conda install typing_extensions
```

The required PyChrono/PyDEME versions are not yet available through standard conda-forge alone, so the `bochengzou` channel is used.

---

**4. Required Assets**

**Purpose:**  
Mesh files are required for wheel and pressure-plate geometry in the simulations.

**Wheel meshes**  
Multiple custom wheel meshes are available in:

```
reference wheel meshes/
```

You can switch between different wheel geometries by updating the mesh path in `config.py`.

---

**Required files:**

- `mesh/rover_wheels/viper_wheel_right.obj` (default demo wheel)  
- `TREAD_Assembly.obj` (example custom wheel)  
- `reference wheel meshes/pressureplate.obj` (pressure plate mesh)  

If these files are missing or located elsewhere, update their paths in `config.py` before running any scripts.

---

**5. Configuration File**

`config.py` is the central configuration file for the project.

It defines:
- output directories  
- solver settings  
- terrain parameters  
- material properties  
- wheel configuration (demo or custom)  
- pressure plate settings  
- slip test parameters  

All scripts depend on this file, so it should be reviewed before running simulations.
