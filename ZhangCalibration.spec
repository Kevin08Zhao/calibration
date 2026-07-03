# -*- mode: python ; coding: utf-8 -*-
# Mac .app 打包配置：张氏相机标定桌面应用
# 使用方式：在项目根目录执行  pyinstaller ZhangCalibration.spec

import sys
from PyInstaller.utils.hooks import collect_all

block_cipher = None

# 确保打包时能找到同目录下的 camera_calibration、image_undistort
added_imports = ['camera_calibration', 'image_undistort', 'pillow_heif', 'PIL', 'PIL.Image', 'openpyxl']
extra_datas = []
extra_binaries = []
extra_hidden = []

try:
    import qfluentwidgets
    added_imports.append('qfluentwidgets')
    _qfw = collect_all('qfluentwidgets')
    extra_datas += _qfw[0]
    extra_binaries += _qfw[1]
    extra_hidden += _qfw[2]
except ImportError:
    pass

# PyQt5 插件与资源（platforms 等），否则打包后可能无法启动 GUI
_qt = collect_all('PyQt5')
extra_datas += _qt[0]
extra_binaries += _qt[1]
extra_hidden += _qt[2]

# 应用图标（使用项目根目录下的 icon.icns）
import os as _os
_icon_path = _os.path.join(_os.path.dirname(SPEC), 'icon.icns')
if _os.path.isfile(_icon_path):
    extra_datas.append((_icon_path, '.'))

a = Analysis(
    ['zhang_calibration_app.py'],
    pathex=[],
    binaries=extra_binaries,
    datas=extra_datas,
    hiddenimports=added_imports + extra_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# onedir 模式：在 Mac 上生成标准 .app 包（dist/ZhangCalibration.app）
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ZhangCalibration',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=True,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=_icon_path if _os.path.isfile(_icon_path) else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='ZhangCalibration',
)
