# Zhang Calibration · Camera Calibration and Distortion Validation

A desktop application based on **Zhang's checkerboard calibration method** for estimating camera intrinsics, correcting image distortion, validating physical measurements, and exporting Excel reports.

The application interface and detailed user manual are currently in Chinese. This README provides the project overview and setup instructions in English.

## Features

- **Camera calibration**: Detect checkerboard corners in a batch of images, estimate the camera matrix and distortion coefficients (`k1`, `k2`, `p1`, `p2`, `k3`), and export `.npz` or `.txt` results.
- **Distortion validation**: Load calibration parameters, undistort validation images, detect checkerboard corners within a fixed crop, and check measured square sizes against a tolerance.
- **Graphical interface**: PyQt5 with Fluent styling and support for JPG, PNG, and HEIC images.
- **Command-line tools**: Run `camera_calibration.py` and `image_undistort.py` independently.

## Requirements

- Python 3.8+
- macOS or Windows

## Installation

```bash
cd calibration

python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Run the graphical application

```bash
python zhang_calibration_app.py
```

### GUI workflow

**Tab 1: Calibration and results**

1. Select the calibration image folder containing multiple checkerboard photographs.
2. Set the inner corner columns and rows, such as 9×6, and the square size in millimeters.
3. Start calibration and review the camera matrix, distortion coefficients, and reprojection error.
4. Export the calibration results as an `.npz` file.

**Tab 2: Distortion validation**

1. Load the `.npz` calibration file created in the previous step. The command-line tool also supports `.txt` files.
2. Select the validation image folder.
3. Set the square size and tolerance in millimeters. The application automatically corrects the selected image and detects corners.
4. Compare the images before and after correction, then export an Excel validation report.

For detailed interface documentation, see the [user manual (Chinese)](%E8%BD%AF%E4%BB%B6%E6%89%8B%E5%86%8C.md).

## Run the command-line tools

### Calibration

```bash
python camera_calibration.py \
  --mode calibrate \
  --image_dir cali_data/data/image0 \
  --pattern 9 6 \
  --square_size 5.0
```

Outputs are saved under `train_result/` in the project root. This directory is created automatically.

### Export readable text

```bash
python camera_calibration.py --mode export
```

### Undistortion and validation

```bash
python image_undistort.py \
  --image cali_data/data/test_image/IMG_4757.jpg \
  --calib train_result/txt_result/calibration_result_9x6_image0.npz \
  --square_size 5.0
```

## Sample data

The repository includes a small sample dataset for trying the workflow:

- `cali_data/data/image0/` — 15 checkerboard photographs for calibration.
- `cali_data/data/test_image/` — Sample validation images.

## Package as a macOS application

```bash
chmod +x build_mac_app.sh
./build_mac_app.sh
# Expected output: dist/ZhangCalibration.app
```

## Project structure

```text
calibration/
├── zhang_calibration_app.py   # GUI entry point
├── camera_calibration.py      # Calibration core and CLI
├── image_undistort.py         # Undistortion, validation, and CLI
├── requirements.txt
├── build_mac_app.sh           # macOS packaging script
├── ZhangCalibration.spec      # PyInstaller configuration
└── cali_data/data/            # Sample images
```
