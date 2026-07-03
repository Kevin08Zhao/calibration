#!/bin/bash
# 在项目根目录执行，将 zhang_calibration_app.py 打包成 Mac 上的 ZhangCalibration.app
# 用法：./build_mac_app.sh  或  bash build_mac_app.sh

set -e
cd "$(dirname "$0")"

# 应用图标：若存在 assets/app_icon.png 且尚无 .icns，则尝试生成
if [[ -f "assets/app_icon.png" && ! -f "ZhangCalibration.icns" ]]; then
    echo "生成应用图标 ZhangCalibration.icns ..."
    if ./make_icon.sh 2>/dev/null; then
        :
    elif [[ -x "venv/bin/python3" ]] && venv/bin/python3 make_icon.py 2>/dev/null; then
        :
    else
        echo "提示: 未生成 .icns。可先运行 ./make_icon.sh 或 pip install Pillow 后运行 python3 make_icon.py。"
    fi
fi

echo "检查 PyInstaller..."
if ! python3 -c "import PyInstaller" 2>/dev/null; then
    echo "正在安装 PyInstaller..."
    pip install pyinstaller
fi

echo "开始打包（请稍候）..."
pyinstaller --noconfirm ZhangCalibration.spec

# 若生成了 .app 且存在 .icns，将图标安装到 app 包内并设置 Info.plist
APP_PATH="dist/ZhangCalibration.app"
if [[ -d "$APP_PATH" && -f "ZhangCalibration.icns" ]]; then
    RESOURCES="${APP_PATH}/Contents/Resources"
    mkdir -p "$RESOURCES"
    cp ZhangCalibration.icns "$RESOURCES/"
    PLIST="${APP_PATH}/Contents/Info.plist"
    if [[ -f "$PLIST" ]]; then
        /usr/libexec/PlistBuddy -c "Set :CFBundleIconFile ZhangCalibration" "$PLIST" 2>/dev/null || true
    fi
    echo "已设置应用图标。"
fi

if [[ -d "dist/ZhangCalibration.app" ]]; then
    echo ""
    echo "打包完成。"
    echo "应用位置: $(pwd)/dist/ZhangCalibration.app"
    echo "可将 dist/ZhangCalibration.app 拖到「应用程序」或任意位置使用。"
elif [[ -d "dist/ZhangCalibration" ]]; then
    echo ""
    echo "已生成 dist/ZhangCalibration/（在 Mac 上可重命名为 ZhangCalibration.app）。"
else
    echo "未找到预期输出，请检查 dist/ 目录。"
    exit 1
fi
