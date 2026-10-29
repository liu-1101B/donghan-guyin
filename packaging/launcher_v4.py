# -*- coding: utf-8 -*-
"""launcher_v4.py — 古韵机器人 v4.0.0 的 PyInstaller 入口。

和 v3 的 launcher.py 的差别：
- 启动的是新版机器人界面 robot/app.py（不再是 guyun_app.py）；
- 关掉 Streamlit 的文件监视与热重载（frozen 模式下 __file__ 在 _internal 里，
  热重载逻辑会把 .py 当源码去 reload，容易炸）；
- 关掉 Streamlit 的首选主题探测，让 .streamlit/config.toml 里的浅色主题生效。
"""
import io
import os
import sys

os.environ["PYTHONUTF8"] = "1"
os.environ["PYTHONIOENCODING"] = "utf-8"
os.environ["STREAMLIT_BROWSER_GATHER_USAGE_STATS"] = "false"
os.environ["STREAMLIT_SERVER_HEADLESS"] = "true"
os.environ["STREAMLIT_SERVER_FILE_WATCHER_TYPE"] = "none"


def bundle_dir():
    """数据文件所在目录：PyInstaller 6 起是 _internal，更早版本是 exe 同级。"""
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(sys.executable)
        internal = os.path.join(exe_dir, "_internal")
        return internal if os.path.isdir(internal) else exe_dir
    return os.path.dirname(os.path.abspath(__file__))


def show_error(title, message):
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, message, title, 0)
    except Exception:
        print(message)


def main():
    if sys.stdin is None:                 # --windowed 时没有 stdin
        sys.stdin = io.StringIO("")

    root = bundle_dir()
    app_path = os.path.join(root, "robot", "app.py")
    if not os.path.exists(app_path):
        show_error("古韵机器人 - 错误", f"找不到界面文件：{app_path}")
        sys.exit(1)

    # 关键：数据文件在 _internal，import robot / services / language 靠它
    sys.path.insert(0, root)
    os.chdir(root)

    port = int(os.environ.get("GUYUN_PORT", "8501"))

    def open_browser():
        import time
        import urllib.request
        import webbrowser
        for _ in range(40):
            try:
                urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/_stcore/health", timeout=1)
                webbrowser.open(f"http://localhost:{port}")
                return
            except Exception:
                time.sleep(1)

    import threading
    threading.Thread(target=open_browser, daemon=True).start()

    try:
        from streamlit.web import cli as stcli
        sys.argv = [
            "streamlit", "run", app_path,
            f"--server.port={port}",
            "--global.developmentMode=false",
            "--server.fileWatcherType=none",
            "--server.runOnSave=false",
            "--browser.gatherUsageStats=false",
        ]
        stcli.main()
    except Exception as exc:
        import traceback
        show_error("古韵机器人 - 启动失败",
                   f"错误: {exc}\n\n{traceback.format_exc()}")
        sys.exit(1)


if __name__ == "__main__":
    main()
