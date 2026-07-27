# -*- coding: utf-8 -*-
"""
launcher.py
古韵合成器 v3.0.0 - PyInstaller 统一入口
"""
import os
import sys
import io

# === 强制UTF-8，根治编码问题 ===
os.environ["PYTHONUTF8"] = "1"
os.environ["PYTHONIOENCODING"] = "utf-8"
# ====================================

# 禁止 Streamlit 弹出欢迎/邮件页面
os.environ["STREAMLIT_BROWSER_GATHER_USAGE_STATS"] = "false"
os.environ["STREAMLIT_SERVER_HEADLESS"] = "true"
os.environ["STREAMLIT_THEME_BASE"] = "dark"


def find_app_file(filename):
    """在 dev 或 frozen 环境下查找 app 文件"""
    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(sys.executable)
        for d in [exe_dir, os.path.join(exe_dir, '_internal')]:
            path = os.path.join(d, filename)
            if os.path.exists(path):
                return path
        return None
    else:
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)


def show_error(title, message):
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, message, title, 0)
    except Exception:
        pass


def main():
    # 修复 --windowed 模式无 stdin 的问题
    if sys.stdin is None:
        sys.stdin = io.StringIO("")

    try:
        app_path = find_app_file("guyun_app.py")
        if not app_path:
            show_error("古韵合成器 - 错误",
                        "找不到 guyun_app.py，程序无法启动。")
            sys.exit(1)

        app_dir = os.path.dirname(app_path)
        os.chdir(app_dir)

        # 关键：把 _internal 也加入 sys.path（PyInstaller 5.x+ 数据文件放这里）
        exe_dir = os.path.dirname(sys.executable)
        internal_dir = os.path.join(exe_dir, '_internal')
        if os.path.isdir(internal_dir):
            sys.path.insert(0, internal_dir)
        sys.path.insert(0, exe_dir)

        port = 8501

        def open_browser():
            import time
            import urllib.request
            import webbrowser
            for _ in range(30):
                try:
                    urllib.request.urlopen(
                        f"http://127.0.0.1:{port}/_stcore/health", timeout=1
                    )
                    webbrowser.open(f"http://localhost:{port}")
                    return
                except Exception:
                    time.sleep(1)

        import threading
        threading.Thread(target=open_browser, daemon=True).start()

        from streamlit.web import cli as stcli
        sys.argv = [
            "streamlit", "run", app_path,
            f"--server.port={port}",
            "--global.developmentMode=false",
            "--server.fileWatcherType=none",   # 防止 frozen 模式下 file watcher 崩溃
            "--server.runOnSave=false",          # 同上
        ]
        stcli.main()

    except Exception as e:
        import traceback
        error_msg = f"错误: {e}\n\n完整追踪:\n{traceback.format_exc()}"
        show_error("古韵合成器 - 启动失败", error_msg)
        sys.exit(1)


if __name__ == "__main__":
    main()
