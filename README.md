# Zhang Calibration · 张氏相机标定与畸变校正验证

基于**张正友棋盘格标定法**的桌面软件，用于相机内参标定、图像去畸变，以及标定结果的物理尺寸验证与 Excel 报告导出。

## 功能概览

- **相机标定**：批量读取棋盘格照片，检测角点，求解内参矩阵与畸变系数（k1, k2, p1, p2, k3），输出 `.npz` / `.txt`
- **畸变校正验证**：加载标定文件，对验证图去畸变，在固定裁剪区域内自动检测棋盘格，测量格子物理长度并判定是否在容差内
- **图形界面**：PyQt5 + Fluent 风格 UI，支持 JPG / PNG / HEIC
- **命令行**：`camera_calibration.py` 与 `image_undistort.py` 可独立运行

## 环境要求

- Python 3.8+
- macOS 或 Windows

## 安装

```bash
cd calibration

python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## 运行（图形界面，推荐）

```bash
python zhang_calibration_app.py
```

### GUI 使用流程

**标签页 1：标定与结果**

1. 点击「选择标定图片目录」，选择包含多张棋盘格照片的文件夹
2. 设置内角点列数、行数（例如 9×6）与格子边长（mm）
3. 点击「开始标定」，查看内参、畸变系数与重投影误差
4. 导出 `.npz` 标定文件

**标签页 2：畸变校正验证**

1. 加载上一步生成的 `.npz`（或 `.txt`）标定文件
2. 选择验证图片目录
3. 设置格子边长与容差（mm），系统自动去畸变并检测
4. 查看矫正前/后对比图，导出 Excel 验证报告

更详细的界面说明见 [`软件手册.md`](软件手册.md)。

## 运行（命令行）

### 标定

```bash
python camera_calibration.py \
  --mode calibrate \
  --image_dir cali_data/data/image0 \
  --pattern 9 6 \
  --square_size 5.0
```

输出写入项目根目录下的 `train_result/`（运行时自动创建）。

### 导出可读 txt

```bash
python camera_calibration.py --mode export
```

### 去畸变与验证

```bash
python image_undistort.py \
  --image cali_data/data/test_image/IMG_4757.jpg \
  --calib train_result/txt_result/calibration_result_9x6.npz \
  --square_size 5.0
```

## 示例数据

仓库包含最小示例集，可直接用于试跑：

- `cali_data/data/image0/` — 标定用棋盘格照片（15 张）
- `cali_data/data/test_image/` — 验证用样例图

## 打包为 macOS 应用（可选）

```bash
chmod +x build_mac_app.sh
./build_mac_app.sh
# 成功后：dist/ZhangCalibration.app
```

## 项目结构

```
calibration/
├── zhang_calibration_app.py   # GUI 入口
├── camera_calibration.py      # 标定核心 + CLI
├── image_undistort.py         # 去畸变验证 + CLI
├── requirements.txt
├── build_mac_app.sh           # macOS 打包脚本
├── ZhangCalibration.spec      # PyInstaller 配置
├── cali_data/data/            # 示例图片
└── 软件手册.md                 # 详细用户手册
```
