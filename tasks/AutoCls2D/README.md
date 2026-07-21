# AutoCls2D

Image classification task based on Wide ResNet-28-10, evaluated on CIFAR-100.

---

## Dataset

This task uses the **CIFAR-100** dataset.

### Download

Download the pre-packaged archive from [Google Drive](https://drive.google.com/file/d/1ZtwOfsamIXq9DLtLJHTcRfA7dyh5bHn5/view?usp=sharing)


Extract the archive:

```bash
unzip cifar100.zip
```

### Directory Structure

Place the extracted data under `/datasets/cifar100`, following this structure:

```
/datasets/
└── cifar100/
    └── cifar-100-python/
        ├── meta
        ├── train
        └── test
```

---

## Environment Setup

### 1. Create a conda environment

```bash
conda create -n autocls2d python=3.10 -y
conda activate autocls2d
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
               # /path/to/conda/envs/autocls2d/bin/python
```

Then edit `launcher.sh`:

```bash
/path/to/conda/envs/autocls2d/bin/python experiment.py \
  --num_workers 4 \
  --out_dir $1 \
  --in_channels 3 \
  --data_root /datasets/cifar100 \
  --val_per_epoch 5
```
