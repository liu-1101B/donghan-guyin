# -*- coding: utf-8 -*-
"""download_models.py — 下载本地语音识别模型到 models/ 目录。

用法:
    python scripts/download_models.py              # 只装 SenseVoice（推荐）
    python scripts/download_models.py --with-vosk  # 同时装 Vosk 兜底模型
    python scripts/download_models.py --force      # 已存在也重新下

模型不进仓库（体积原因，models/ 已被 .gitignore 忽略），但下载方式必须可复现，
这是 v5 的验收项之一（见 docs/v5-goal.md）。

目录约定（与 services/asr_client.py 一致）:
    models/sense-voice/model.int8.onnx + tokens.txt   ← 首选后端
    models/vosk-small-cn/am/final.mdl                 ← 兜底后端
"""
import argparse
import io
import os
import sys
import tarfile
import time
import urllib.request
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS_DIR = os.path.join(ROOT, "models")

SENSEVOICE_DIR = os.path.join(MODELS_DIR, "sense-voice")
VOSK_DIR = os.path.join(MODELS_DIR, "vosk-small-cn")

SENSEVOICE_ARCHIVE = "sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17.tar.bz2"
SENSEVOICE_URLS = [
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/" + SENSEVOICE_ARCHIVE,
    "https://gh-proxy.com/https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/" + SENSEVOICE_ARCHIVE,
    "https://ghfast.top/https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/" + SENSEVOICE_ARCHIVE,
]

VOSK_ARCHIVE = "vosk-model-small-cn-0.22.zip"
VOSK_URLS = [
    "https://alphacephei.com/vosk/models/" + VOSK_ARCHIVE,
]

HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "*/*"}


def _download(urls, dest, timeout=30):
    """依次尝试各镜像，成功返回 True。带进度，失败可重试。"""
    for url in urls:
        host = url.split("/")[2]
        for attempt in (1, 2):
            print(f"  下载 <- {host} (第 {attempt} 次)")
            try:
                req = urllib.request.Request(url, headers=HEADERS)
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    total = int(resp.headers.get("Content-Length") or 0)
                    got = 0
                    t0 = time.time()
                    with open(dest, "wb") as fh:
                        while True:
                            chunk = resp.read(262144)
                            if not chunk:
                                break
                            fh.write(chunk)
                            got += len(chunk)
                            if total and got % (8 * 1024 * 1024) < 262144:
                                print(f"    {got * 100 // total:3d}%  "
                                      f"{got / 1048576:.1f}/{total / 1048576:.1f} MB  "
                                      f"({got / 1024 / max(time.time() - t0, .001):.0f} KB/s)")
                size = os.path.getsize(dest)
                print(f"    完成 {size / 1048576:.1f} MB")
                if total and size != total:
                    raise IOError(f"大小不符 {size} != {total}")
                return True
            except Exception as exc:  # noqa: BLE001
                print(f"    失败: {type(exc).__name__}: {str(exc)[:120]}")
                if os.path.exists(dest):
                    try:
                        os.remove(dest)
                    except OSError:
                        pass
    return False


def _extract_tar_bz2(archive, target, inner_prefix=None):
    """解 tar.bz2。压缩包里通常带一层顶层目录，默认剥掉。"""
    os.makedirs(target, exist_ok=True)
    with tarfile.open(archive, "r:bz2") as tf:
        members = tf.getmembers()
        tops = {m.name.split("/")[0] for m in members if m.name}
        strip = inner_prefix
        if strip is None and len(tops) == 1:
            strip = tops.pop()
        for m in members:
            name = m.name
            if strip and name.startswith(strip + "/"):
                name = name[len(strip) + 1:]
            elif strip and name == strip:
                continue
            if not name:
                continue
            dest = os.path.join(target, name)
            if m.isdir():
                os.makedirs(dest, exist_ok=True)
            elif m.isfile():
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                src = tf.extractfile(m)
                if src is None:
                    continue
                with src, open(dest, "wb") as out:
                    out.write(src.read())


def _extract_zip(archive, target):
    with zipfile.ZipFile(archive) as zf:
        names = zf.namelist()
        tops = {n.split("/")[0] for n in names if n}
        strip = tops.pop() if len(tops) == 1 else None
        for n in names:
            rel = n[len(strip) + 1:] if strip and n.startswith(strip + "/") else n
            if not rel:
                continue
            dest = os.path.join(target, rel)
            if n.endswith("/"):
                os.makedirs(dest, exist_ok=True)
            else:
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                with zf.open(n) as src, open(dest, "wb") as out:
                    out.write(src.read())


def sensevoice_ready():
    return (os.path.isfile(os.path.join(SENSEVOICE_DIR, "tokens.txt"))
            and any(os.path.isfile(os.path.join(SENSEVOICE_DIR, f))
                    for f in ("model.int8.onnx", "model.onnx")))


def vosk_ready():
    return os.path.isfile(os.path.join(VOSK_DIR, "am", "final.mdl"))


def install_sensevoice(force=False):
    print("\n[1/2] SenseVoice（sherpa-onnx，约 155 MB，中文最强、自带标点）")
    if sensevoice_ready() and not force:
        print(f"  已就绪: {SENSEVOICE_DIR}")
        return True
    os.makedirs(MODELS_DIR, exist_ok=True)
    archive = os.path.join(MODELS_DIR, "_" + SENSEVOICE_ARCHIVE)
    if not _download(SENSEVOICE_URLS, archive):
        print("  下载失败")
        return False
    print("  解压 ...")
    _extract_tar_bz2(archive, SENSEVOICE_DIR)
    os.remove(archive)
    if sensevoice_ready():
        print(f"  就绪: {SENSEVOICE_DIR}")
        return True
    print("  解压后缺少 model.int8.onnx / tokens.txt")
    return False


def install_vosk(force=False):
    print("\n[2/2] Vosk 小模型（约 44 MB，兜底后端）")
    if vosk_ready() and not force:
        print(f"  已就绪: {VOSK_DIR}")
        return True
    os.makedirs(MODELS_DIR, exist_ok=True)
    archive = os.path.join(MODELS_DIR, "_" + VOSK_ARCHIVE)
    if not _download(VOSK_URLS, archive):
        print("  下载失败")
        return False
    print("  解压 ...")
    _extract_zip(archive, VOSK_DIR)
    os.remove(archive)
    if vosk_ready():
        print(f"  就绪: {VOSK_DIR}")
        return True
    print("  解压后缺少 am/final.mdl")
    return False


def main():
    ap = argparse.ArgumentParser(description="下载本地 ASR 模型")
    ap.add_argument("--with-vosk", action="store_true", help="同时下载 Vosk 兜底模型")
    ap.add_argument("--force", action="store_true", help="已存在也重新下载")
    args = ap.parse_args()

    print("=" * 60)
    print("  下载语音识别模型到 models/")
    print("=" * 60)

    ok = install_sensevoice(force=args.force)
    if args.with_vosk:
        ok = install_vosk(force=args.force) and ok

    print()
    if ok:
        print("完成。可用 `python -c \"import services.asr_client as a; print(a.detect_backends())\"` 检查。")
        return 0
    print("部分模型缺失，语音输入可能不可用。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
