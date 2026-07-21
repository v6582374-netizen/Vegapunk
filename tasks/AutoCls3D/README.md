# AutoCls3D

3D point cloud classification task based on PointNet, evaluated on ModelNet40.

---

## Dataset

This task uses the **ModelNet40** dataset (pre-sampled to 1024 points per shape).

### Download

Download the pre-packaged archive from [Google Drive](https://drive.google.com/file/d/10bQj4ypO3Mhebn0su-sVI9x-4TyS2Kyx/view?usp=sharing)
Extract the archive:

```bash
unzip modelnet40.zip
```

### Directory Structure

Place the extracted data under `/datasets/modelnet40`, following this structure:

```
/datasets/
└── modelnet40/
    ├── modelnet40_shape_names.txt
    ├── modelnet40_train.txt
    ├── modelnet40_test.txt
    ├── modelnet40_train_1024pts.dat
    ├── modelnet40_train_1024pts_fps.dat
    ├── modelnet40_test_1024pts.dat
    └── modelnet40_test_1024pts_fps.dat
```

---

## Environment Setup

### 1. Create a conda environment

```bash
conda create -n autocls3d python=3.10 -y
conda activate autocls3d
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

The `requirements.txt` is consistent with [Vegapunk/requirements.txt](https://github.com/v6582374-netizen/Vegapunk/blob/main/requirements.txt).

### 3. Configure the Python path in launcher.sh

Open `launcher.sh` and replace `python` with the full path to the conda environment's Python interpreter:

```bash
# Find the path
which python   # run after activating the conda env, e.g. outputs:
               # /path/to/conda/envs/autocls3d/bin/python
```

Then edit `launcher.sh`:

```bash
/path/to/conda/envs/autocls3d/bin/python experiment.py \
  --out_dir $1 \
  --data_root /datasets/modelnet40 \
  --max_epoch 200 \
  --val_per_epoch 5
```
