# -*- coding: utf-8 -*-
"""UI 冒烟：无头跑 guyun_app.py 整个脚本树，检查无异常 + 拟音体系 selectbox 存在。

用法（工作树 CWD，环境变量见 docs/HANDOVER.md）：

    $py scripts/smoke_app.py

退出码 0 = 通过；非 0 时打印 Streamlit 捕获的异常与堆栈尾部。
"""
import os

from streamlit.testing.v1 import AppTest

_APP = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "guyun_app.py")
at = AppTest.from_file(_APP, default_timeout=120)
at.run()

if at.exception:
    for e in at.exception:
        print("EXC:", repr(e.value))
        st_lines = e.stack_trace or []
        if isinstance(st_lines, str):
            st_lines = st_lines.splitlines()
        for line in st_lines[-15:]:
            print("   ", line)
    raise SystemExit(1)

print("selectbox labels:", [o.label for o in at.selectbox])
print("OK smoke, selectboxes:", len(at.selectbox))
