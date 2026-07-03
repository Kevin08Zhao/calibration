#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
图片去畸变并验证：标定系数来自一组特定规格棋盘格；验证时在矫正前/矫正后
图像上按横纵 1/5 与 4/5 确定同一裁剪区域，在该区域内检测格点、计算格子
实际长度，并统计最小/最大格子长度、差值、差值/标准百分比。

截取方法：横轴 1/5 与 4/5 处两条竖线、纵轴 1/5 与 4/5 处两条横线，四条
线两两交点围成的矩形即为裁剪区域，矫正前与矫正后使用相同位置、相同大小。

使用：
  python image_undistort.py --image 图片路径 --calib 标定.npz或.txt --square_size 格子边长mm
  --pattern 可选，裁剪区域内格点规格（列 行），不填则自动尝试多种规格。
"""

import os
import sys
import argparse
import numpy as np
import cv2


def _apply_exif_orientation(pil_img):
    try:
        from PIL import ImageOps
        return ImageOps.exif_transpose(pil_img)
    except Exception:
        return pil_img


def _heic_to_jpg_and_read(path):
    try:
        import pillow_heif
        pillow_heif.register_heif_opener()
        from PIL import Image
        pil_img = Image.open(path)
        pil_img = _apply_exif_orientation(pil_img)
        if pil_img.mode != "RGB":
            pil_img = pil_img.convert("RGB")
        dirname = os.path.dirname(path)
        base_name = os.path.splitext(os.path.basename(path))[0]
        jpg_path = os.path.join(dirname, base_name + ".jpg")
        pil_img.save(jpg_path, "JPEG", quality=95)
        img = cv2.imread(jpg_path)
        if img is not None:
            print(f"  [HEIC→JPG] 已保存: {jpg_path}")
        return img
    except ImportError:
        print(f"  [HEIC 读取失败] 需要安装 pillow-heif：pip install pillow-heif")
        return None
    except Exception as e:
        print(f"  [HEIC 读取失败] {path}: {e}")
        return None


def read_image(path):
    ext = os.path.splitext(path)[1].lower()
    if ext in ('.heic', '.heif'):
        return _heic_to_jpg_and_read(path)
    img = cv2.imread(path)
    if img is None:
        try:
            from PIL import Image
            pil_img = Image.open(path)
            pil_img = _apply_exif_orientation(pil_img)
            img = np.array(pil_img)
            if img.ndim == 2:
                img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
            elif img.ndim == 3:
                img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
        except Exception as e:
            print(f"  [读取失败] {path}: {e}")
            return None
    return img


def load_calibration_from_txt(txt_path):
    import ast
    if not os.path.isfile(txt_path):
        raise FileNotFoundError(f"标定文件不存在: {txt_path}")
    with open(txt_path, "r", encoding="utf-8") as f:
        content = f.read()
    camera_matrix = dist_coeffs = image_size = None
    if "【相机内参矩阵" in content:
        idx = content.index("【相机内参矩阵")
        rest = content[idx:]
        start, end = rest.index("[["), rest.index("]]", rest.index("[[")) + 2
        camera_matrix = np.array(ast.literal_eval(rest[start:end]), dtype=np.float64)
    if "【畸变系数" in content:
        idx = content.index("【畸变系数")
        rest = content[idx:]
        start, end = rest.index("["), rest.index("]", start) + 1
        arr = np.array(ast.literal_eval(rest[start:end]), dtype=np.float64)
        dist_coeffs = arr.reshape(1, -1) if arr.ndim == 1 else arr
    if "【图像尺寸" in content:
        idx = content.index("【图像尺寸")
        rest = content[idx:]
        start, end = rest.index("["), rest.index("]", start) + 1
        parts = rest[start:end].strip("[]").split()
        image_size = tuple(int(x) for x in parts)
    if camera_matrix is None or dist_coeffs is None:
        raise ValueError("txt 中未解析到内参或畸变系数")
    return camera_matrix, dist_coeffs, image_size


def load_calibration(npz_path):
    if not os.path.isfile(npz_path):
        raise FileNotFoundError(f"标定文件不存在: {npz_path}")
    data = np.load(npz_path, allow_pickle=True)
    camera_matrix = data["camera_matrix"]
    dist_coeffs = data["dist_coeffs"]
    image_size = tuple(data["image_size"]) if "image_size" in data else None
    return camera_matrix, dist_coeffs, image_size


def load_calibration_any(calib_path):
    calib_path = os.path.abspath(calib_path)
    if not os.path.isfile(calib_path):
        raise FileNotFoundError(f"标定文件不存在: {calib_path}")
    ext = os.path.splitext(calib_path)[1].lower()
    if ext == ".txt":
        return load_calibration_from_txt(calib_path)
    if ext == ".npz":
        return load_calibration(calib_path)
    raise ValueError(f"不支持的标定格式: {ext}，请使用 .npz 或 .txt")


def undistort_image(img, camera_matrix, dist_coeffs, alpha=1):
    h, w = img.shape[:2]
    new_camera_matrix, roi = cv2.getOptimalNewCameraMatrix(
        camera_matrix, dist_coeffs, (w, h), alpha, (w, h)
    )
    undistorted_img = cv2.undistort(
        img, camera_matrix, dist_coeffs, None, new_camera_matrix
    )
    if alpha < 1:
        x, y, w_roi, h_roi = roi
        undistorted_img = undistorted_img[y:y+h_roi, x:x+w_roi]
    return undistorted_img, new_camera_matrix


# 自动检测棋盘格时尝试的规格（列,行），从大到小；含方形规格以应对圆形视场/黑边遮挡
# 扩展更多候选规格以提高检测能力
PATTERN_CANDIDATES = [
    (15, 11), (14, 10), (13, 9), (12, 9), (12, 8), (11, 11), (11, 9), (11, 8), (11, 7),
    (10, 10), (10, 9), (10, 8), (10, 7), (10, 6), (9, 9), (9, 8), (9, 7), (9, 6), (9, 5),
    (8, 8), (8, 7), (8, 6), (8, 5), (8, 4), (7, 7), (7, 6), (7, 5), (7, 4),
    (6, 6), (6, 5), (6, 4), (6, 3), (5, 5), (5, 4), (5, 3), (4, 4), (4, 3), (3, 3),
]


def _fifth_crop_bbox(h, w):
    """横纵 1/5 与 4/5 处四条线围成的矩形：左 x=w/5, 右 x=4w/5, 上 y=h/5, 下 y=4h/5。返回 (x, y, w_crop, h_crop)。"""
    x = w // 5
    y = h // 5
    w_crop = (4 * w) // 5 - x
    h_crop = (4 * h) // 5 - y
    return (x, y, w_crop, h_crop)


def find_checkerboard(gray, pattern_size, use_fast_check=True):
    """
    在图像上检测棋盘格角点（CLAHE + AdaptiveThreshOnly），确保所有标记的点都是真正的角点。
    pattern_size=(列,行) 为内角点数。
    使用 CLAHE 预处理 + AdaptiveThreshOnly 标志，提高角点检测精度。
    对于裁剪图，会尝试多种预处理方法以提高检测成功率。
    """
    # 预处理：CLAHE（对比度受限的自适应直方图均衡化）
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    clahe_img = clahe.apply(gray)
    
    # 尝试多种预处理图像
    preprocessed_images = [
        ("clahe", clahe_img),
        ("original", gray),  # 也尝试原始图像
    ]
    
    # 添加直方图均衡化版本
    eq_img = cv2.equalizeHist(gray)
    preprocessed_images.append(("equalized", eq_img))
    
    # 添加轻微模糊版本（有助于检测）
    blur = cv2.GaussianBlur(gray, (3, 3), 0)
    preprocessed_images.append(("blur", blur))
    
    # 使用 AdaptiveThreshOnly 标志（不使用 NORMALIZE_IMAGE，避免误检）
    flags = cv2.CALIB_CB_ADAPTIVE_THRESH
    if use_fast_check:
        flags += cv2.CALIB_CB_FAST_CHECK
    
    # 优先使用更鲁棒的 SB 方法（OpenCV 4.5+）
    for prep_name, prep_img in preprocessed_images:
        try:
            ret, corners = cv2.findChessboardCornersSB(
                prep_img, pattern_size,
                flags=cv2.CALIB_CB_EXHAUSTIVE | cv2.CALIB_CB_ACCURACY
            )
            if ret and corners is not None:
                # 使用原始灰度图进行角点亚像素精化（预处理图用于检测，原图用于精化）
                criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 50, 0.001)
                corners = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), criteria)
                return True, corners
        except AttributeError:
            # OpenCV 版本不支持 findChessboardCornersSB
            break
        except Exception:
            # 其他错误，继续尝试
            continue
    
    # SB 方法不可用或失败，使用经典方法
    for prep_name, prep_img in preprocessed_images:
        # 先尝试带 FAST_CHECK
        ret, corners = cv2.findChessboardCorners(prep_img, pattern_size, flags)
        if ret and corners is not None:
            criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 50, 0.001)
            corners = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), criteria)
            return True, corners
        
        # 如果失败且使用了 FAST_CHECK，去掉 FAST_CHECK 再试一次
        if use_fast_check:
            ret, corners = cv2.findChessboardCorners(
                prep_img, pattern_size,
                cv2.CALIB_CB_ADAPTIVE_THRESH,
            )
            if ret and corners is not None:
                criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 50, 0.001)
                corners = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), criteria)
                return True, corners
    
    return False, None


def detect_checkerboard_auto(gray_undist, gray_orig, pattern_hint=None, prefer_small=False, status_callback=None):
    """
    在矫正图或原图中自动检测棋盘格（增强检测，可应对不同规格、边缘被遮挡）。
    pattern_hint: 可选 (cols, rows)，若提供则优先尝试该规格及更小的规格。
    当指定规格检测失败时，会自动尝试缩小一列或一行，直到找到完整的格点图。
    prefer_small: True 时优先尝试小规格（适合裁剪后圆形区域内仅含小块格点）。
    status_callback: 可选，回调 str -> None，用于报告当前尝试的规格（如 "检测格点 7×7…"）。
    返回: (pattern_size, corners, from_undist) 或 (None, None, None)。
    """
    def try_pattern(gray_img, pattern_size, use_fast_check=True):
        """尝试检测指定规格的棋盘格"""
        ret, corners = find_checkerboard(gray_img, pattern_size, use_fast_check=use_fast_check)
        if ret and corners is not None:
            return True, corners
        return False, None
    
    def generate_shrunk_patterns(start_cols, start_rows):
        """
        生成缩小后的模式列表：优先尝试最接近原始规格的缩小版本。
        策略：按总减少量（曼哈顿距离）排序，优先尝试减少量最小的版本。
        例如：(7,7) -> (6,7), (7,6) -> (6,6), (5,7), (7,5), (5,6), (6,5) -> ...
        """
        patterns = []
        visited = set()
        min_size = 3  # 最小规格限制（至少3x3）
        
        # 按总减少量分组生成模式
        max_total_reduction = (start_cols - min_size) + (start_rows - min_size)
        
        for total_reduction in range(max_total_reduction + 1):
            # 对于每个总减少量，尝试所有可能的列和行组合
            for col_reduction in range(total_reduction + 1):
                row_reduction = total_reduction - col_reduction
                cols = start_cols - col_reduction
                rows = start_rows - row_reduction
                
                if cols >= min_size and rows >= min_size:
                    pattern = (cols, rows)
                    if pattern not in visited:
                        patterns.append(pattern)
                        visited.add(pattern)
        
        return patterns
    
    # 如果提供了pattern_hint，优先尝试该规格及缩小版本
    if pattern_hint is not None:
        c, r = pattern_hint
        # 生成缩小模式列表（从指定规格开始，逐步缩小）
        candidates = generate_shrunk_patterns(c, r)
        # 添加其他候选规格中更小的规格
        other_candidates = [p for p in PATTERN_CANDIDATES if p != pattern_hint and p[0] <= c and p[1] <= r]
        # 去重并合并
        for p in other_candidates:
            if p not in candidates:
                candidates.append(p)
    else:
        # 没有pattern_hint时，从PATTERN_CANDIDATES中最大的规格开始，限制数量以加快验证
        candidates = list(PATTERN_CANDIDATES)
        candidates.sort(key=lambda x: x[0] * x[1], reverse=True)
        candidates = candidates[:30]  # 最多尝试 30 种规格，兼顾速度与检出率
    
    if prefer_small:
        candidates = list(reversed(candidates))

    # 策略：对于每个候选模式，同时尝试矫正前和矫正后的图
    # 优先返回两个图都能检测到的模式，如果只有一个能检测到也返回
    for pattern_size in candidates:
        if status_callback:
            status_callback("检测格点 {}×{}…".format(pattern_size[0], pattern_size[1]))
        # 先尝试使用 fast_check（快速）
        ret_u, corners_u = try_pattern(gray_undist, pattern_size, use_fast_check=True)
        ret_o, corners_o = try_pattern(gray_orig, pattern_size, use_fast_check=True)
        
        # 如果两个图都能检测到，优先返回矫正后的图（通常质量更好）
        if ret_u and ret_o:
            return pattern_size, corners_u, True
        # 如果只有矫正后的图能检测到
        if ret_u:
            return pattern_size, corners_u, True
        # 如果只有矫正前的图能检测到
        if ret_o:
            return pattern_size, corners_o, False
        
        # fast_check 失败，尝试不使用 fast_check（更全面但更慢）
        ret_u, corners_u = try_pattern(gray_undist, pattern_size, use_fast_check=False)
        ret_o, corners_o = try_pattern(gray_orig, pattern_size, use_fast_check=False)
        
        # 如果两个图都能检测到，优先返回矫正后的图
        if ret_u and ret_o:
            return pattern_size, corners_u, True
        # 如果只有矫正后的图能检测到
        if ret_u:
            return pattern_size, corners_u, True
        # 如果只有矫正前的图能检测到
        if ret_o:
            return pattern_size, corners_o, False
    
    return None, None, None


def _compute_mm_per_pix_stats(pts_2d, inner_cols, inner_rows, square_size_mm):
    """pts_2d: (inner_rows, inner_cols, 2)。返回 min, max, diff, diff_pct_min。"""
    mm_list = []
    for r in range(inner_rows):
        for c in range(inner_cols - 1):
            d = np.linalg.norm(pts_2d[r, c + 1] - pts_2d[r, c])
            if d > 1e-6:
                mm_list.append(square_size_mm / d)
    for r in range(inner_rows - 1):
        for c in range(inner_cols):
            d = np.linalg.norm(pts_2d[r + 1, c] - pts_2d[r, c])
            if d > 1e-6:
                mm_list.append(square_size_mm / d)
    if not mm_list:
        return None, None, None, None
    min_mp = float(np.min(mm_list))
    max_mp = float(np.max(mm_list))
    diff = max_mp - min_mp
    pct = (diff / min_mp) * 100.0 if min_mp > 1e-9 else 0.0
    return min_mp, max_mp, diff, pct


def _draw_verify_panel(img, title, res, color_bgr, conclusion_line=None, no_result_msg=None, w_panel=360):
    """在图像左上角绘制半透明背景 + 多行验证文字（英文，避免 OpenCV 中文乱码）。"""
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 0.5
    thickness = 1
    line_h = 22
    margin = 8
    lines = [title]
    if res is not None:
        lines.append("min length: {:.4f}mm".format(res["min_length_mm"]))
        lines.append("max length: {:.4f}mm".format(res["max_length_mm"]))
        lines.append("diff: {:.4f}mm".format(res["diff_mm"]))
        lines.append("diff/std: {:.2f}%".format(res["diff_pct"]))
    elif no_result_msg:
        lines.append(no_result_msg)
    if conclusion_line:
        lines.append(conclusion_line)
    n = len(lines)
    h_panel = margin * 2 + n * line_h
    overlay = img.copy()
    cv2.rectangle(overlay, (0, 0), (w_panel, h_panel), (40, 40, 40), -1)
    cv2.addWeighted(overlay, 0.75, img, 0.25, 0, img)
    for i, s in enumerate(lines):
        y_pos = margin + (i + 1) * line_h
        cv2.putText(img, s, (margin, y_pos), font, font_scale, color_bgr, thickness, cv2.LINE_AA)


def verify_crop_draw_segments(img_crop, corners, pattern_size, square_size_mm, title, color_bgr, tolerance_mm=0.1):
    """
    在裁剪图上绘制格点角点，计算格子实际长度（mm），并统计最小/最大格子长度、差值、差值/标准百分比。
    验证方法：找到最短的格子边长（像素）作为标准，用标准换算其他格子的实际长度，计算差值百分比。
    边长标注：字体放大；若 边长 > 格子边长+容差 显示红色，在容差范围内显示绿色。
    仅对检测到的格点连线标注，不标记非格点。
    返回 (annotated_img, result_dict 或 None)。
    """
    cols, rows = pattern_size
    pts = corners.reshape(rows, cols, 2)
    annotated = img_crop.copy()
    annotated = cv2.drawChessboardCorners(annotated, pattern_size, corners, True)

    # 放大边长标注的字体与线宽
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 0.9
    thickness = 2
    pixel_lengths = []  # 所有相邻点之间的距离（像素）

    # 仅收集格点之间相邻点距离（不引入非格点）
    for r in range(rows):
        for c in range(cols - 1):
            p1, p2 = pts[r, c], pts[r, c + 1]
            d = np.linalg.norm(p2 - p1)
            if d > 1e-6:
                pixel_lengths.append(d)
    for r in range(rows - 1):
        for c in range(cols):
            p1, p2 = pts[r, c], pts[r + 1, c]
            d = np.linalg.norm(p2 - p1)
            if d > 1e-6:
                pixel_lengths.append(d)

    if not pixel_lengths:
        _draw_verify_panel(annotated, title, None, color_bgr, no_result_msg="No valid segments")
        return annotated, None

    # 找到最短的格子边长（像素）作为标准
    min_pixel_length = float(np.min(pixel_lengths))
    scale = square_size_mm / min_pixel_length if min_pixel_length > 1e-6 else 0.0
    
    # 用比例换算所有格子的实际长度（mm）
    actual_lengths = [p * scale for p in pixel_lengths]
    
    min_actual = float(np.min(actual_lengths))
    max_actual = float(np.max(actual_lengths))
    diff_actual = max_actual - min_actual
    diff_pct = (diff_actual / min_actual) * 100.0 if min_actual > 1e-9 else 0.0

    # 根据容差决定颜色：大于 格子边长+容差 → 红色；在 [格子边长-容差, 格子边长+容差] 内 → 绿色
    # BGR: 红=(0,0,255), 绿=(0,255,0)
    def _segment_color(actual_mm):
        if actual_mm > square_size_mm + tolerance_mm:
            return (0, 0, 255)   # 红色：偏大
        if actual_mm < square_size_mm - tolerance_mm:
            return (0, 0, 255)   # 红色：偏小（超出容差）
        return (0, 255, 0)       # 绿色：在容差范围内

    def _draw_segment_label(p1, p2, actual_mm):
        mid = ((p1[0] + p2[0]) * 0.5, (p1[1] + p2[1]) * 0.5)
        tx = int(mid[0]) - 40
        ty = int(mid[1]) - 8
        seg_color = _segment_color(actual_mm)
        # 描边一次提高可读性
        cv2.putText(annotated, "{:.2f}mm".format(actual_mm), (tx, ty), font, font_scale, (0, 0, 0), thickness + 1, cv2.LINE_AA)
        cv2.putText(annotated, "{:.2f}mm".format(actual_mm), (tx, ty), font, font_scale, seg_color, thickness, cv2.LINE_AA)

    idx = 0
    for r in range(rows):
        for c in range(cols - 1):
            p1, p2 = pts[r, c], pts[r, c + 1]
            d = np.linalg.norm(p2 - p1)
            if d > 1e-6:
                _draw_segment_label(p1, p2, actual_lengths[idx])
                idx += 1
    for r in range(rows - 1):
        for c in range(cols):
            p1, p2 = pts[r, c], pts[r + 1, c]
            d = np.linalg.norm(p2 - p1)
            if d > 1e-6:
                _draw_segment_label(p1, p2, actual_lengths[idx])
                idx += 1

    res = {
        "min_length_mm": min_actual,
        "max_length_mm": max_actual,
        "diff_mm": diff_actual,
        "diff_pct": diff_pct
    }
    conclusion = "OK: correction effective" if diff_pct < 5.0 else "Check calibration or pattern"
    _draw_verify_panel(annotated, title, res, color_bgr, conclusion_line=conclusion)
    return annotated, res


def run_undistort_and_verify(image_path, calib_path, pattern_hint=None, square_size_mm=5.0, tolerance_mm=0.1, output_dir=None, alpha=1.0, status_callback=None):
    """
    供 GUI 等调用：读图、矫正、按横纵 1/5 与 4/5 裁剪并做格点验证，返回矫正图与验证结果。
    - image_path: 输入图片路径
    - calib_path: 标定文件 .npz 或 .txt
    - pattern_hint: 可选 (cols, rows)，裁剪区域内格点规格
    - square_size_mm: 格子边长 mm
    - tolerance_mm: 容差 mm，用于裁剪验证图中边长颜色（超出为红、在容差内为绿）
    - output_dir: 若提供则写入矫正图与裁剪验证图
    - alpha: 去畸变裁剪参数
    - status_callback: 可选，回调 str -> None，用于报告当前步骤（如 GUI 显示“正在加载标定…”）
    返回 dict:
      - undistorted: 矫正后整图 (ndarray)
      - crop_orig_annot, crop_undist_annot: 裁剪验证图（带角点与标注），未检测到格点时仍为裁剪图
      - result_orig, result_undist: 矫正前/后截取区域格子长度统计，或 None
      - cols, rows: 检测到的格点尺寸
      - summary_text: 与终端输出一致的格点验证结果文本（含最小/最大格子长度、差值、差值/标准%、结论、较矫正前改善）
      - base_name: 文件名主名，便于保存
      - error: 若某步失败则为该错误信息，其余键可能为 None
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    if not os.path.isabs(image_path):
        image_path = os.path.normpath(os.path.join(script_dir, image_path))
    if not os.path.isabs(calib_path):
        calib_path = os.path.normpath(os.path.join(script_dir, calib_path))
    out = {
        "undistorted": None,
        "crop_orig_annot": None,
        "crop_undist_annot": None,
        "result_orig": None,
        "result_undist": None,
        "cols": None,
        "rows": None,
        "summary_text": "",
        "base_name": os.path.splitext(os.path.basename(image_path))[0],
        "error": None,
    }
    def _status(msg):
        if status_callback:
            status_callback(msg)

    try:
        _status("正在加载标定…")
        camera_matrix, dist_coeffs, _ = load_calibration_any(calib_path)
    except Exception as e:
        out["error"] = str(e)
        return out
    _status("正在读取图片…")
    img = read_image(image_path)
    if img is None:
        out["error"] = "无法读取图片"
        return out
    _status("正在去畸变…")
    undistorted, _ = undistort_image(img, camera_matrix, dist_coeffs, alpha)
    out["undistorted"] = undistorted
    H, W = img.shape[0], img.shape[1]
    _status("正在裁剪区域 (1/5–4/5)…")
    x, y, w, h = _fifth_crop_bbox(H, W)
    crop_orig = img[y:y + h, x:x + w]
    crop_undist = undistorted[y:y + h, x:x + w]
    gray_crop_orig = cv2.cvtColor(crop_orig, cv2.COLOR_BGR2GRAY)
    gray_crop_undist = cv2.cvtColor(crop_undist, cv2.COLOR_BGR2GRAY)
    _status("正在检测格点（矫正前/后）…")
    pattern_size, corners_detected, from_undist = detect_checkerboard_auto(
        gray_crop_undist, gray_crop_orig, pattern_hint, status_callback=_status
    )
    if pattern_size is None or corners_detected is None:
        crop_orig_annot = crop_orig.copy()
        crop_undist_annot = crop_undist.copy()
        _draw_verify_panel(crop_orig_annot, "[Before] 1/5-4/5 crop", None, (0, 0, 255), no_result_msg="No checkerboard")
        _draw_verify_panel(crop_undist_annot, "[After] 1/5-4/5 crop", None, (0, 180, 0), no_result_msg="No checkerboard")
        cv2.rectangle(crop_orig_annot, (0, 0), (crop_orig_annot.shape[1] - 1, crop_orig_annot.shape[0] - 1), (0, 0, 255), 3)
        cv2.rectangle(crop_undist_annot, (0, 0), (crop_undist_annot.shape[1] - 1, crop_undist_annot.shape[0] - 1), (0, 180, 0), 3)
        out["crop_orig_annot"] = crop_orig_annot
        out["crop_undist_annot"] = crop_undist_annot
        _status("未检测到格点，已生成裁剪图。")
        out["summary_text"] = "在裁剪区域（横纵 1/5 与 4/5 围成）内未检测到完整棋盘格。"
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
            cv2.imwrite(os.path.join(output_dir, f"{out['base_name']}_crop_original_verify.jpg"), crop_orig_annot)
            cv2.imwrite(os.path.join(output_dir, f"{out['base_name']}_crop_undistorted_verify.jpg"), crop_undist_annot)
        return out
    
    cols, rows = pattern_size
    
    # 根据检测来源，分别检测两个图的角点
    if from_undist:
        corners_undist = corners_detected
        _status("正在检测矫正前裁剪图角点…")
        ret_orig, corners_orig = find_checkerboard(gray_crop_orig, pattern_size)
        if not ret_orig or corners_orig is None:
            corners_orig = None
    else:
        corners_orig = corners_detected
        _status("正在检测矫正后裁剪图角点…")
        ret_undist, corners_undist = find_checkerboard(gray_crop_undist, pattern_size)
        if not ret_undist or corners_undist is None:
            corners_undist = None

    _status("正在生成矫正前验证图…")
    # 处理矫正前的图
    if corners_orig is not None:
        crop_orig_annot, result_orig = verify_crop_draw_segments(
            crop_orig, corners_orig, pattern_size, square_size_mm,
            "[Before] 1/5-4/5 crop", (0, 0, 255), tolerance_mm=tolerance_mm
        )
        out["result_orig"] = result_orig
    else:
        crop_orig_annot = crop_orig.copy()
        _draw_verify_panel(crop_orig_annot, "[Before] 1/5-4/5 crop", None, (0, 0, 255), no_result_msg="No checkerboard")
        result_orig = None
    cv2.rectangle(crop_orig_annot, (0, 0), (crop_orig_annot.shape[1] - 1, crop_orig_annot.shape[0] - 1), (0, 0, 255), 3)

    _status("正在生成矫正后验证图…")
    # 处理矫正后的图
    if corners_undist is not None:
        crop_undist_annot, result_undist = verify_crop_draw_segments(
            crop_undist, corners_undist, pattern_size, square_size_mm,
            "[After] 1/5-4/5 crop", (0, 180, 0), tolerance_mm=tolerance_mm
        )
        out["result_undist"] = result_undist
    else:
        crop_undist_annot = crop_undist.copy()
        _draw_verify_panel(crop_undist_annot, "[After] 1/5-4/5 crop", None, (0, 180, 0), no_result_msg="No checkerboard")
        result_undist = None
    
    cv2.rectangle(crop_undist_annot, (0, 0), (crop_undist_annot.shape[1] - 1, crop_undist_annot.shape[0] - 1), (0, 180, 0), 3)
    out["crop_orig_annot"] = crop_orig_annot
    out["crop_undist_annot"] = crop_undist_annot
    out["result_undist"] = result_undist
    out["cols"] = cols
    out["rows"] = rows
    _status("验证完成。")
    lines = [
        f"【格点验证结果】裁剪区域格点尺寸: {cols}x{rows}，标准格子边长: {square_size_mm} mm",
        "  [矫正前]",
    ]
    if result_orig is None:
        lines.append("    未检测到格点或无有效线段")
    else:
        r = result_orig
        lines.append(f"    最小格子长度 (mm): {r['min_length_mm']:.4f}")
        lines.append(f"    最大格子长度 (mm): {r['max_length_mm']:.4f}")
        lines.append(f"    差值 (最大 - 最小): {r['diff_mm']:.4f} mm")
        lines.append(f"    差值/标准百分比: {r['diff_pct']:.2f}%")
    lines.append("  [矫正后]")
    if result_undist is None:
        lines.append("    未检测到格点或无有效线段")
    else:
        r = result_undist
        lines.append(f"    最小格子长度 (mm): {r['min_length_mm']:.4f}")
        lines.append(f"    最大格子长度 (mm): {r['max_length_mm']:.4f}")
        lines.append(f"    差值 (最大 - 最小): {r['diff_mm']:.4f} mm")
        lines.append(f"    差值/标准百分比: {r['diff_pct']:.2f}%")
    if result_undist is not None:
        pct = result_undist["diff_pct"]
        if pct < 5.0:
            lines.append("  结论: 矫正后格子长度更均匀，差值百分比小，矫正有效。")
        else:
            lines.append("  结论: 矫正后差值百分比偏大，可检查标定或格点参数。")
    if result_orig is not None and result_undist is not None and result_orig["diff_pct"] > result_undist["diff_pct"]:
        lines.append(f"  较矫正前改善: {result_orig['diff_pct'] - result_undist['diff_pct']:.2f}%")
    out["summary_text"] = "\n".join(lines)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
        cv2.imwrite(os.path.join(output_dir, f"{out['base_name']}_undistorted.jpg"), undistorted)
        cv2.imwrite(os.path.join(output_dir, f"{out['base_name']}_crop_original_verify.jpg"), crop_orig_annot)
        cv2.imwrite(os.path.join(output_dir, f"{out['base_name']}_crop_undistorted_verify.jpg"), crop_undist_annot)
    return out


def main():
    parser = argparse.ArgumentParser(
        description="图片去畸变并在矫正图上做格点验证（格子长度均匀性）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
验证：在横纵 1/5 与 4/5 围成的裁剪区域内检测格点，计算格子实际长度（mm），
统计最小/最大格子长度、差值、差值/标准百分比；差值百分比越小表示矫正越有效。
        """
    )
    parser.add_argument("--image", type=str, required=True, help="输入图片路径（支持 HEIC/JPG/PNG）")
    parser.add_argument("--calib", type=str, required=True, help="标定文件路径（.npz 或 .txt）")
    parser.add_argument("--output", type=str, default="test_result", help="输出目录，默认 test_result")
    parser.add_argument("--pattern", type=int, nargs=2, metavar=("COLS", "ROWS"), default=None, help="可选。裁剪区域（横纵1/5与4/5）内格点规格 列 行，不填则自动尝试多种规格")
    parser.add_argument("--square_size", type=float, default=5.0, help="图中棋盘格格子边长（mm），默认 5.0")
    parser.add_argument("--tolerance", type=float, default=0.1, help="容差（mm），裁剪验证图中边长超出为红、在容差内为绿，默认 0.1")
    parser.add_argument("--alpha", type=float, default=1.0, help="去畸变裁剪参数 0~1，默认 1.0")

    args = parser.parse_args()
    script_dir = os.path.dirname(os.path.abspath(__file__))

    # 路径
    image_path = args.image if os.path.isabs(args.image) else os.path.join(script_dir, args.image)
    calib_path = args.calib if os.path.isabs(args.calib) else os.path.join(script_dir, args.calib)
    output_dir = args.output if os.path.isabs(args.output) else os.path.join(script_dir, args.output)
    os.makedirs(output_dir, exist_ok=True)

    if not os.path.isfile(image_path):
        print(f"错误：图片不存在 {image_path}")
        sys.exit(1)

    # 加载标定
    try:
        camera_matrix, dist_coeffs, _ = load_calibration_any(calib_path)
    except Exception as e:
        print(f"错误：{e}")
        sys.exit(1)
    print(f"已加载标定: {os.path.basename(calib_path)}")

    # 读取并矫正
    img = read_image(image_path)
    if img is None:
        print("错误：无法读取图片")
        sys.exit(1)
    undistorted, _ = undistort_image(img, camera_matrix, dist_coeffs, args.alpha)

    base_name = os.path.splitext(os.path.basename(image_path))[0]
    out_undist = os.path.join(output_dir, f"{base_name}_undistorted.jpg")
    cv2.imwrite(out_undist, undistorted)
    print(f"矫正图已保存: {out_undist}")

    # 验证：横纵 1/5 与 4/5 确定裁剪区域（矫正前/矫正后相同位置、相同大小），在裁剪内检测格点、计算格子长度并统计
    H, W = img.shape[0], img.shape[1]
    x, y, w, h = _fifth_crop_bbox(H, W)
    crop_orig = img[y:y + h, x:x + w]
    crop_undist = undistorted[y:y + h, x:x + w]
    gray_crop_orig = cv2.cvtColor(crop_orig, cv2.COLOR_BGR2GRAY)
    gray_crop_undist = cv2.cvtColor(crop_undist, cv2.COLOR_BGR2GRAY)

    pattern_hint = tuple(args.pattern) if args.pattern is not None else None
    pattern_size, corners_undist, _ = detect_checkerboard_auto(gray_crop_undist, gray_crop_orig, pattern_hint)

    if pattern_size is None or corners_undist is None:
        print("验证：在裁剪区域（横纵 1/5 与 4/5 围成）内未检测到完整棋盘格。")
        print("  可尝试指定 --pattern 列 行（裁剪区域内格点规格）。")
        # 仍输出仅裁剪图（无格点）
        out_crop_orig = os.path.join(output_dir, f"{base_name}_crop_original_verify.jpg")
        out_crop_undist = os.path.join(output_dir, f"{base_name}_crop_undistorted_verify.jpg")
        crop_orig_annot = crop_orig.copy()
        crop_undist_annot = crop_undist.copy()
        _draw_verify_panel(crop_orig_annot, "[Before] 1/5-4/5 crop", None, (0, 0, 255), no_result_msg="No checkerboard")
        _draw_verify_panel(crop_undist_annot, "[After] 1/5-4/5 crop", None, (0, 180, 0), no_result_msg="No checkerboard")
        cv2.rectangle(crop_orig_annot, (0, 0), (crop_orig_annot.shape[1] - 1, crop_orig_annot.shape[0] - 1), (0, 0, 255), 3)
        cv2.rectangle(crop_undist_annot, (0, 0), (crop_undist_annot.shape[1] - 1, crop_undist_annot.shape[0] - 1), (0, 180, 0), 3)
        cv2.imwrite(out_crop_orig, crop_orig_annot)
        cv2.imwrite(out_crop_undist, crop_undist_annot)
        print(f"裁剪区域: 位置=({x},{y}) 大小={w}x{h}")
        return

    cols, rows = pattern_size
    print(f"裁剪区域: 位置=({x},{y}) 大小={w}x{h}（横纵 1/5 与 4/5 围成，矫正前/矫正后相同）")
    print(f"检测到棋盘格: {cols}×{rows} 内角点")

    ret_orig, corners_orig = find_checkerboard(gray_crop_orig, pattern_size)
    if ret_orig and corners_orig is not None:
        crop_orig_annot, result_orig = verify_crop_draw_segments(
            crop_orig, corners_orig, pattern_size, args.square_size,
            "[Before] 1/5-4/5 crop", (0, 0, 255), tolerance_mm=args.tolerance
        )
    else:
        crop_orig_annot = crop_orig.copy()
        _draw_verify_panel(crop_orig_annot, "[Before] 1/5-4/5 crop", None, (0, 0, 255), no_result_msg="No checkerboard")
        result_orig = None
    cv2.rectangle(crop_orig_annot, (0, 0), (crop_orig_annot.shape[1] - 1, crop_orig_annot.shape[0] - 1), (0, 0, 255), 3)

    crop_undist_annot, result_undist = verify_crop_draw_segments(
        crop_undist, corners_undist, pattern_size, args.square_size,
        "[After] 1/5-4/5 crop", (0, 180, 0), tolerance_mm=args.tolerance
    )
    cv2.rectangle(crop_undist_annot, (0, 0), (crop_undist_annot.shape[1] - 1, crop_undist_annot.shape[0] - 1), (0, 180, 0), 3)

    out_crop_orig = os.path.join(output_dir, f"{base_name}_crop_original_verify.jpg")
    out_crop_undist = os.path.join(output_dir, f"{base_name}_crop_undistorted_verify.jpg")
    cv2.imwrite(out_crop_orig, crop_orig_annot)
    cv2.imwrite(out_crop_undist, crop_undist_annot)
    print(f"裁剪验证图（矫正前）已保存: {out_crop_orig}")
    print(f"裁剪验证图（矫正后）已保存: {out_crop_undist}")

    def _print_result(label, res):
        if res is None:
            print(f"  [{label}] 未检测到格点或无有效线段")
            return
        min_len = res["min_length_mm"]
        max_len = res["max_length_mm"]
        diff = res["diff_mm"]
        pct = res["diff_pct"]
        print(f"  [{label}]")
        print(f"    最小格子长度 (mm): {min_len:.4f}")
        print(f"    最大格子长度 (mm): {max_len:.4f}")
        print(f"    差值 (最大 - 最小): {diff:.4f} mm")
        print(f"    差值/标准百分比: {pct:.2f}%")

    print("\n" + "=" * 50)
    print("【格点验证结果】裁剪区域格点尺寸: {}x{}，标准格子边长: {} mm".format(cols, rows, args.square_size))
    _print_result("矫正前", result_orig)
    _print_result("矫正后", result_undist)
    print("=" * 50)
    if result_undist is not None:
        pct = result_undist["diff_pct"]
        if pct < 5.0:
            print("  结论: 矫正后格子长度更均匀，差值百分比小，矫正有效。")
        else:
            print("  结论: 矫正后差值百分比偏大，可检查标定或格点参数。")
    if result_orig is not None and result_undist is not None and result_orig["diff_pct"] > result_undist["diff_pct"]:
        print("  较矫正前改善: {:.2f}%".format(result_orig["diff_pct"] - result_undist["diff_pct"]))


if __name__ == "__main__":
    main()
