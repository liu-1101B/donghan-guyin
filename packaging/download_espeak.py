# -*- coding: utf-8 -*-
"""
download_espeak.py
下载 espeak-ng MSI 安装包并提取文件到 espeak-ng\ 目录

用法:
    python download_espeak.py

这会在当前目录创建 espeak-ng\ 文件夹，内含:
    espeak-ng.exe
    espeak-ng-data\  (语言数据)
    *.dll           (运行时依赖)
"""
import os
import sys
import subprocess
import urllib.request
import shutil
import tempfile
import glob
import fnmatch

# eSpeak-ng 1.52.0 官方 MSI（唯一发布的 Windows 格式）
MSI_URL = "https://github.com/espeak-ng/espeak-ng/releases/download/1.52.0/espeak-ng.msi"
MSI_FILENAME = "espeak-ng.msi"

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "espeak-ng")


# 如果你需要通过代理下载，可以在这里填写代理地址
# 格式: PROXY = "http://127.0.0.1:端口"
PROXY = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY") or ""


def download(url, dest):
    """带进度提示的下载（支持代理）"""
    print(f"正在从 GitHub 下载 eSpeak-ng ...")
    print(f"  {url}")
    try:
        if PROXY:
            print(f"  走代理: {PROXY}")
            proxy_handler = urllib.request.ProxyHandler({
                "http": PROXY,
                "https": PROXY
            })
            opener = urllib.request.build_opener(proxy_handler)
            urllib.request.install_opener(opener)

        urllib.request.urlretrieve(url, dest)
        size_mb = os.path.getsize(dest) / 1024 / 1024
        print(f"  下载完成 ({size_mb:.1f} MB)")
        return True
    except Exception as e:
        print(f"  下载失败: {e}")
        return False


def extract_msi(msi_path, target_dir):
    """使用 msiexec /a 解压 MSI（不安装，只提取文件）"""
    os.makedirs(target_dir, exist_ok=True)
    tmp_extract = os.path.join(SCRIPT_DIR, "_espeak_temp_extract")

    # 清理上次提取
    if os.path.exists(tmp_extract):
        shutil.rmtree(tmp_extract)
    os.makedirs(tmp_extract, exist_ok=True)

    print(f"正在提取 MSI 文件...")
    # msiexec /a 做"管理安装" = 只解压文件，不写注册表
    cmd = [
        "msiexec", "/a", msi_path,
        "/qn",  # 静默模式
        f"TARGETDIR={tmp_extract}"
    ]
    try:
        subprocess.run(cmd, check=True, timeout=60)
    except subprocess.CalledProcessError as e:
        print(f"  msiexec 提取失败: {e}")
        print(f"  尝试备选方案...")
        return False
    except FileNotFoundError:
        print(f"  错误: 找不到 msiexec.exe，请在 Windows 上运行此脚本")
        return False

    # MSI 提取后的文件结构通常是:
    #   _espeak_temp_extract/
    #     PFiles/
    #       eSpeak NG/
    #         espeak-ng.exe
    #         espeak-ng-data/
    #         ...
    # 或直接:
    #   _espeak_temp_extract/
    #     eSpeak NG/
    #       ...
    # 或更直接的:
    #   _espeak_temp_extract/
    #     espeak-ng.exe
    #     ...

    # 查找 espeak-ng.exe
    found_exe = None
    for root, dirs, files in os.walk(tmp_extract):
        if "espeak-ng.exe" in files:
            found_exe = os.path.join(root, "espeak-ng.exe")
            break

    if not found_exe:
        print(f"  ⚠️ 在提取的文件中找不到 espeak-ng.exe")
        print(f"  提取目录内容:")
        for root, dirs, files in os.walk(tmp_extract):
            for f in files[:20]:
                print(f"    {os.path.relpath(os.path.join(root, f), tmp_extract)}")
        return False

    # 找到包含 espeak-ng.exe 的目录，复制其中所有文件
    espeak_root = os.path.dirname(found_exe)
    print(f"  找到: {espeak_root}")

    # 递归复制所有文件到目标目录
    for root, dirs, files in os.walk(espeak_root):
        rel = os.path.relpath(root, espeak_root)
        if rel == ".":
            dest_sub = target_dir
        else:
            dest_sub = os.path.join(target_dir, rel)
        os.makedirs(dest_sub, exist_ok=True)
        for f in files:
            src_path = os.path.join(root, f)
            dst_path = os.path.join(dest_sub, f)
            shutil.copy2(src_path, dst_path)

    # 清理临时目录
    shutil.rmtree(tmp_extract, ignore_errors=True)

    # 验证结果
    expected = os.path.join(target_dir, "espeak-ng.exe")
    if os.path.exists(expected):
        print(f"  ✅ 提取成功: {expected}")
        return True
    else:
        print(f"  ❌ 提取后找不到 {expected}")
        return False


def manual_instructions():
    """手动安装指引"""
    print()
    print("=" * 60)
    print("  自动下载/提取失败，请手动操作：")
    print("=" * 60)
    print()
    print("  方法一（推荐）: 安装后复制文件")
    print("  1. 从 https://github.com/espeak-ng/espeak-ng/releases")
    print("     下载 espeak-ng.msi 并双击安装")
    print(f"  2. 复制 C:\\Program Files\\eSpeak NG\\ 中的所有文件到:")
    print(f"     {OUTPUT_DIR}")
    print()
    print("  方法二: 用 winget 安装后复制")
    print("  1. 在 PowerShell 中运行:")
    print("     winget install -e --id eSpeak-NG.eSpeak-NG")
    print(f"  2. 复制 C:\\Program Files\\eSpeak NG\\ 中的所有文件到:")
    print(f"     {OUTPUT_DIR}")
    print()
    print("  确保 {0} 目录中存在:".format(OUTPUT_DIR))
    print("    - espeak-ng.exe")
    print("    - espeak-ng-data\\  (整个文件夹)")
    print()
    sys.exit(1)


def main():
    print("=" * 60)
    print("  下载 eSpeak-ng 并准备打包")
    print("=" * 60)

    # 如果已存在，跳过
    espeak_exe = os.path.join(OUTPUT_DIR, "espeak-ng.exe")
    espeak_data = os.path.join(OUTPUT_DIR, "espeak-ng-data")
    if os.path.exists(espeak_exe) and os.path.exists(espeak_data):
        # 数一下 data 目录下的文件数
        file_count = sum(1 for _ in glob.iglob(
            os.path.join(espeak_data, "**", "*"), recursive=True))
        if file_count > 10:  # 确保 data 目录不是空的
            print(f"✅ eSpeak-ng 已就绪:")
            print(f"   {espeak_exe}")
            print(f"   {espeak_data}/ ({file_count} 个文件)")
            return
        else:
            print(f"⚠️ espeak-ng-data 目录文件异常少 ({file_count} 个)，重新下载...")

    msi_path = os.path.join(SCRIPT_DIR, MSI_FILENAME)

    # 步骤 1: 下载
    if not os.path.exists(msi_path) or os.path.getsize(msi_path) < 1024 * 1024:
        if not download(MSI_URL, msi_path):
            manual_instructions()
    else:
        size_mb = os.path.getsize(msi_path) / 1024 / 1024
        print(f"使用已缓存的 {MSI_FILENAME} ({size_mb:.1f} MB)")

    # 步骤 2: 用 msiexec /a 提取（Windows 上可用）
    if not extract_msi(msi_path, OUTPUT_DIR):
        manual_instructions()

    # 步骤 3: 清理 MSI 文件（可选，节省空间）
    os.remove(msi_path)
    print(f"  已清理 {MSI_FILENAME}")

    print()
    print("✅ eSpeak-ng 准备完成！现在可以运行 build.bat 构建安装包。")


if __name__ == "__main__":
    main()
