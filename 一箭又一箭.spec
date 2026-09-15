# -*- mode: python ; coding: utf-8 -*-
# ============================================================
# “一箭又一箭” PyInstaller 打包配置（单文件 / 图形界面）
#
# 用法：
#     pyinstaller 一箭又一箭.spec
#
# 生成物：
#     dist/一箭又一箭.exe   ← 可直接双击运行的游戏程序
#     build/               ← 打包中间文件，可随时删除
#
# 说明：
# - console=False 等价于命令行参数 --windowed，运行时不显示黑色控制台。
# - 不使用 COLLECT，所有内容打入单个 EXE，等价于 --onefile。
# - datas 为空：游戏界面全部由 Pygame 绘图生成，不读取外部图片/音频；
#   images/ 目录只是 README 截图，不属于运行时资源，因此无需打包。
# - 中文字体优先读取 Windows 系统字体（微软雅黑等），缺失时自动回退到
#   Pygame 默认字体，所以目标机器无需额外安装字体文件。
# ============================================================

block_cipher = None


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[],
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

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='一箭又一箭',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # 不显示控制台窗口（图形界面程序）
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
