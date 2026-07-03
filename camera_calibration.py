#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
张正友相机标定

功能说明：
  1. 标定模式（calibrate）：用棋盘格图片计算相机内参和畸变系数。
     - 角点检测统一使用「增强检测」（预处理 + findChessboardCornersSB，失败时退回经典方法）。
     - 每次标定都会自动生成检出图，保存到 train_result 下。
     - 标定结果（npz、txt）保存到 train_result/txt_result。
  2. 导出模式（export）：将已有 npz 标定结果导出为可读的 txt 文件。
  3. 检测模式（detect）：仅对指定目录做角点检测并保存检出图（不进行标定），同样使用增强检测。

输出路径（标定模式）：
  - 内参与畸变：train_result/txt_result/calibration_result_<pattern>_<图片目录名>.npz / .txt
  - 检出图：     train_result/output_<图片目录名>/*_corners.jpg
  可通过 --output_file、--output_dir 自定义路径。

使用示例：
  # 标定（必须指定图片目录与角点数，检出图自动输出到 train_result）
  python camera_calibration.py --mode calibrate --image_dir data/image4 --pattern 9 6

  # 导出最新 npz 为 txt（默认从 train_result/txt_result 找 npz）
  python camera_calibration.py --mode export

  # 仅做角点检测并保存检出图
  python camera_calibration.py --mode detect --image_dir data/image4 --pattern 9 6
"""

import os
import sys
import glob
import argparse
import numpy as np
import cv2


def read_image(path):
    """读取图片，支持 HEIC / JPG / PNG。返回 BGR 的 numpy 数组，失败返回 None。"""
    ext = os.path.splitext(path)[1].lower()
    if ext in ('.heic', '.heif'):
        try:
            import pillow_heif
            pillow_heif.register_heif_opener()
            from PIL import Image
            img = np.array(Image.open(path))
            if img.ndim == 2:
                return cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
            return cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
        except Exception as e:
            print(f"  [HEIC 读取失败] {path}: {e}")
            return None
    img = cv2.imread(path)
    if img is None:
        # OpenCV读取失败，尝试用PIL读取
        try:
            from PIL import Image
            pil_img = Image.open(path)
            img = np.array(pil_img)
            if img.ndim == 2:
                img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
            elif img.ndim == 3:
                img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
        except Exception as e:
            print(f"  [读取失败] {path}: {e}")
            return None
    return img


def find_corners(img, pattern_size):
    """
    在图像中查找棋盘格角点（仅使用增强检测）。
    预处理 + findChessboardCornersSB，失败时退回经典方法。
    pattern_size: (内角点列数, 内角点行数)
    返回 (ret, corners, gray)
    """
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # 预处理：轻微模糊 + 直方图均衡
    blur = cv2.GaussianBlur(gray, (3, 3), 0)
    eq = cv2.equalizeHist(blur)
    
    # 优先使用更鲁棒的 SB 方法
    ret, corners = cv2.findChessboardCornersSB(
        eq, pattern_size,
        flags=cv2.CALIB_CB_EXHAUSTIVE | cv2.CALIB_CB_ACCURACY
    )
    
    # 若 SB 失败，退回经典方法（同一预处理图）
    if not ret:
        ret, corners = cv2.findChessboardCorners(
            eq, pattern_size,
            cv2.CALIB_CB_ADAPTIVE_THRESH
            + cv2.CALIB_CB_FAST_CHECK
            + cv2.CALIB_CB_NORMALIZE_IMAGE,
        )
        if ret:
            criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 1e-3)
            corners = cv2.cornerSubPix(eq, corners, (5, 5), (-1, -1), criteria)
    
    return ret, corners, gray


def save_calibration_txt(npz_path, txt_path=None):
    """
    将 calibration_result.npz 的内容导出为可读的 txt 文件。
    txt_path 不指定时，默认与 npz 同路径、同主名，扩展名为 .txt。
    """
    if txt_path is None:
        txt_path = npz_path.rsplit(".", 1)[0] + ".txt"
    data = np.load(npz_path, allow_pickle=True)
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("========== 张正友相机标定结果 ==========\n\n")
        f.write("【相机内参矩阵 camera_matrix 3x3】\n")
        f.write(np.array2string(data["camera_matrix"], separator=", ", prefix="  ") + "\n\n")
        f.write("【畸变系数 dist_coeffs】(k1, k2, p1, p2, k3)\n")
        f.write(np.array2string(data["dist_coeffs"].ravel(), separator=", ") + "\n\n")
        f.write("【图像尺寸 image_size】(宽, 高)\n")
        f.write(str(data["image_size"]) + "\n\n")
        f.write("【平均重投影误差 mean_error】(像素)\n")
        f.write(str(float(data["mean_error"])) + "\n\n")
        f.write("【每张标定图的旋转向量 rvecs】\n")
        for i, r in enumerate(data["rvecs"]):
            f.write(f"  图{i+1}: {np.array2string(r.ravel(), separator=', ')}\n")
        f.write("\n【每张标定图的平移向量 tvecs】\n")
        for i, t in enumerate(data["tvecs"]):
            f.write(f"  图{i+1}: {np.array2string(t.ravel(), separator=', ')}\n")
    return txt_path


def run_calibration(
    image_dir,
    pattern_size=(11, 8),
    square_size_mm=5.0,
    extensions=("*.jpg", "*.JPG", "*.png", "*.PNG", "*.HEIC", "*.heic"),
    show_detection=False,
    output_file="calibration_result.npz",
    output_dir=None,  # 棋盘格检出图保存目录（save_output=True 时必传）
    log_callback=None,  # 可选：每行输出调用 callback(line)，用于 GUI 显示运行日志
    progress_callback=None,  # 可选：进度回调 callback(current, total)
    save_output=True,  # 为 False 时不写入任何文件（不保存 npz/txt/检出图），仅返回结果
):
    """
    执行张正友标定。标定与检出图均使用增强检测。
    - save_output=True: 写入 npz、txt、检出图到 output_file / output_dir
    - save_output=False: 不写入任何文件，仅返回结果（供 GUI 在用户点击「下载」时再保存）
    """
    def _log(s):
        if log_callback is not None:
            log_callback(s)
        else:
            print(s)
    # 标定板上的 3D 点（以第一个角点为原点，Z=0）
    objp = np.zeros((pattern_size[0] * pattern_size[1], 3), np.float32)
    objp[:, :2] = np.mgrid[
        0 : pattern_size[0],
        0 : pattern_size[1],
    ].T.reshape(-1, 2)
    objp *= square_size_mm  # 单位: mm

    obj_points = []  # 每张图的 3D 点
    img_points = []  # 每张图的 2D 角点
    success_paths = []
    image_size = None

    # 收集所有图片路径
    paths = []
    for ext in extensions:
        paths.extend(glob.glob(os.path.join(image_dir, ext)))
    paths = sorted(set(paths))

    if not paths:
        _log(f"在 {image_dir} 下未找到匹配的图片（{extensions}）")
        return None

    _log(f"找到 {len(paths)} 张候选图片，开始角点检测（增强检测）...")
    if save_output and not output_dir:
        raise ValueError("output_dir 必须指定，标定会输出检出图到该目录")
    if save_output and output_dir:
        os.makedirs(output_dir, exist_ok=True)

    total = len(paths)
    for idx, path in enumerate(paths):
        if progress_callback is not None:
            progress_callback(idx + 1, total)
        img = read_image(path)
        if img is None:
            continue
        if image_size is None:
            image_size = (img.shape[1], img.shape[0])

        ret, corners, gray = find_corners(img, pattern_size)
        if not ret:
            _log(f"  未检测到角点: {os.path.basename(path)}")
            continue

        obj_points.append(objp)
        img_points.append(corners)
        success_paths.append(path)

        if save_output and output_dir:
            vis = img.copy()
            cv2.drawChessboardCorners(vis, pattern_size, corners, ret)
            base_name = os.path.splitext(os.path.basename(path))[0]
            output_path = os.path.join(output_dir, f"{base_name}_corners.jpg")
            cv2.imwrite(output_path, vis)
            _log(f"  已保存检出图: {os.path.basename(output_path)}")

        if show_detection:
            vis = img.copy()
            cv2.drawChessboardCorners(vis, pattern_size, corners, ret)
            cv2.imshow("Corners", vis)
            cv2.waitKey(300)

    if show_detection:
        cv2.destroyAllWindows()

    n_ok = len(obj_points)
    _log(f"成功检测角点的图片: {n_ok} / {len(paths)}")

    if n_ok < 3:
        _log("至少需要 3 张有效图片才能标定。")
        return None

    # 标定
    ret, mtx, dist, rvecs, tvecs = cv2.calibrateCamera(
        obj_points,
        img_points,
        image_size,
        None,
        None,
    )

    if not ret:
        _log("标定失败。")
        return None

    # 重投影误差：RMS = sqrt(mean(d^2)) = sqrt(sum(d^2)/N) = norm_L2 / sqrt(N)
    total_error = 0
    for i in range(n_ok):
        img_pts2, _ = cv2.projectPoints(
            obj_points[i], rvecs[i], tvecs[i], mtx, dist
        )
        n_pts = len(img_pts2)
        err = cv2.norm(img_points[i], img_pts2, cv2.NORM_L2) / np.sqrt(n_pts) if n_pts > 0 else 0.0
        total_error += err
    mean_error = total_error / n_ok

    # 输出结果
    _log("\n" + "=" * 60)
    _log("相机内参矩阵 (3x3):")
    _log(str(mtx))
    _log("\n畸变系数 (k1, k2, p1, p2, k3):")
    _log(str(dist.ravel()))
    _log(f"\n平均重投影误差 (像素): {mean_error:.4f}")
    _log("=" * 60)

    if save_output and output_file:
        np.savez(
            output_file,
            ret=ret,
            camera_matrix=mtx,
            dist_coeffs=dist,
            rvecs=rvecs,
            tvecs=tvecs,
            image_size=image_size,
            mean_error=mean_error,
        )
        _log(f"\n结果已保存到: {output_file}")
        txt_file = output_file.rsplit(".", 1)[0] + ".txt"
        save_calibration_txt(output_file, txt_file)
        _log(f"文本版本已保存到: {txt_file}")
    else:
        _log("\n（未自动保存文件，可在应用中点击「下载 npz 到本地」保存）")

    return {
        "camera_matrix": mtx,
        "dist_coeffs": dist,
        "image_size": image_size,
        "mean_error": mean_error,
        "ret": ret,
        "rvecs": rvecs,
        "tvecs": tvecs,
    }


def run_enhanced_detection(image_dir, pattern_size, output_dir, extensions=None):
    """
    仅角点检测模式：对指定目录下图片做角点检测并保存检出图，不进行标定。
    与标定使用同一套增强检测（find_corners），检出图命名 <原图名>_corners_retry.jpg。
    """
    if extensions is None:
        extensions = ("*.jpg", "*.JPG", "*.png", "*.PNG", "*.HEIC", "*.heic")
    
    os.makedirs(output_dir, exist_ok=True)
    
    paths = []
    for ext in extensions:
        paths.extend(glob.glob(os.path.join(image_dir, ext)))
    paths = sorted(set(paths))
    
    if not paths:
        print(f"在 {image_dir} 下未找到匹配的图片")
        return
    
    print(f"发现 {len(paths)} 张图片，开始增强角点检测...")
    ok, fail = 0, 0
    
    for path in paths:
        img = read_image(path)
        if img is None:
            fail += 1
            print(f"  [FAIL] {os.path.basename(path)} (读取失败)")
            continue
        
        ret, corners, gray = find_corners(img, pattern_size)
        if not ret or corners is None:
            fail += 1
            print(f"  [FAIL] {os.path.basename(path)} (未检测到角点)")
            continue
        
        vis = img.copy()
        cv2.drawChessboardCorners(vis, pattern_size, corners, ret)
        
        base = os.path.splitext(os.path.basename(path))[0]
        out_path = os.path.join(output_dir, f"{base}_corners_retry.jpg")
        cv2.imwrite(out_path, vis)
        ok += 1
        print(f"  [OK] {os.path.basename(path)} -> {os.path.basename(out_path)}")
    
    print(f"\n完成：成功 {ok}，失败 {fail}。可视化保存在 {output_dir}")


def main():
    parser = argparse.ArgumentParser(
        description="张正友相机标定",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
输出说明（标定模式）：
  标定结果（npz、txt）默认保存到 train_result/txt_result/
  检出图默认保存到 train_result/output_<图片目录名>/  文件名格式：<原图名>_corners.jpg

使用示例：
  # 标定 data/image4，角点 9x6，结果与检出图自动写入 train_result
   python camera_calibration.py --mode calibrate --image_dir data/image4 --pattern 11 8

  # 导出最新标定结果为 txt（默认从 train_result/txt_result 查找 npz）
  python camera_calibration.py --mode export

  # 仅做角点检测并保存检出图到 train_result（不计算内参）
  python camera_calibration.py --mode detect --image_dir data/image4 --pattern 9 6
        """
    )
    
    parser.add_argument(
        "--mode",
        choices=["calibrate", "export", "detect"],
        default="calibrate",
        help="calibrate=标定并输出检出图, export=导出npz为txt, detect=仅角点检测并保存检出图"
    )
    
    # 标定/检测模式参数
    parser.add_argument("--image_dir", type=str, help="标定或检测的图片目录（如 data/image4）")
    parser.add_argument("--pattern", type=int, nargs=2, metavar=("COLS", "ROWS"), help="棋盘格内角点数，列 行（如 9 6）")
    parser.add_argument("--square_size", type=float, default=5.0, help="棋盘格格子边长（mm），默认 5.0")
    parser.add_argument("--output_file", type=str, help="标定结果 npz 保存路径（默认 train_result/txt_result/ 下自动命名）")
    parser.add_argument("--output_dir", type=str, help="检出图保存目录（默认 train_result/output_<图片目录名>）")
    parser.add_argument("--show", action="store_true", help="标定时弹窗显示每张图的角点检测结果")
    
    # 导出模式参数
    parser.add_argument("--npz", type=str, help="要导出的 npz 文件路径（不指定则用 train_result/txt_result 下最新）")
    parser.add_argument("--txt", type=str, help="导出 txt 的保存路径（可选，默认与 npz 同路径同主名.txt）")
    
    args = parser.parse_args()
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    if args.mode == "export":
        # 导出模式
        if not args.npz:
            # 默认查找 train_result/txt_result 目录下的 npz 文件
            result_dir = os.path.join(script_dir, "train_result", "txt_result")
            npz_files = glob.glob(os.path.join(result_dir, "*.npz"))
            if not npz_files:
                print("错误：未找到 npz 文件，请使用 --npz 指定文件路径")
                sys.exit(1)
            args.npz = sorted(npz_files)[-1]  # 使用最新的
            print(f"自动使用: {args.npz}")
        
        if not os.path.isfile(args.npz):
            print(f"错误：文件不存在: {args.npz}")
            sys.exit(1)
        
        txt_path = save_calibration_txt(args.npz, args.txt)
        print(f"已导出: {txt_path}")
    
    elif args.mode == "detect":
        # 增强检测模式
        if not args.image_dir:
            print("错误：--image_dir 参数必需")
            sys.exit(1)
        if not args.pattern:
            print("错误：--pattern 参数必需（格式：--pattern 11 8）")
            sys.exit(1)
        
        image_dir = args.image_dir if os.path.isabs(args.image_dir) else os.path.join(script_dir, args.image_dir)
        pattern_size = tuple(args.pattern)
        # 增强检测的检出图也放在 train_result 下
        train_result_dir = os.path.join(script_dir, "train_result")
        output_dir = args.output_dir if args.output_dir and os.path.isabs(args.output_dir) else os.path.join(train_result_dir, args.output_dir or "output_retry")
        
        run_enhanced_detection(image_dir, pattern_size, output_dir)
    
    else:
        # 标定模式（默认）
        if not args.image_dir:
            print("错误：--image_dir 参数必需")
            sys.exit(1)
        if not args.pattern:
            print("错误：--pattern 参数必需（格式：--pattern 11 8）")
            sys.exit(1)
        
        image_dir = args.image_dir if os.path.isabs(args.image_dir) else os.path.join(script_dir, args.image_dir)
        pattern_size = tuple(args.pattern)
        # 标定结果（npz、txt）统一保存到 train_result/txt_result
        result_dir = os.path.join(script_dir, "train_result", "txt_result")
        # 检出图统一保存到 train_result 下；未指定时用 train_result/output_<图片目录名>
        train_result_dir = os.path.join(script_dir, "train_result")
        if args.output_dir:
            output_dir = args.output_dir if os.path.isabs(args.output_dir) else os.path.join(train_result_dir, args.output_dir)
        else:
            output_dir = os.path.join(train_result_dir, "output_" + os.path.basename(image_dir.rstrip(os.sep)) if os.path.basename(image_dir.rstrip(os.sep)) else "output")
        
        os.makedirs(result_dir, exist_ok=True)
        os.makedirs(output_dir, exist_ok=True)
        
        if not args.output_file:
            # 自动生成文件名，保存到 train_result/txt_result
            base_name = f"calibration_result_{pattern_size[0]}x{pattern_size[1]}"
            if os.path.basename(image_dir):
                base_name += f"_{os.path.basename(image_dir)}"
            args.output_file = os.path.join(result_dir, f"{base_name}.npz")
        
        run_calibration(
            image_dir=image_dir,
            pattern_size=pattern_size,
            square_size_mm=args.square_size,
            show_detection=args.show,
            output_file=args.output_file,
            output_dir=output_dir,
        )


if __name__ == "__main__":
    main()
