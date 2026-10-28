"""AppTest 验证：每次生成产出三段音频（我的话古韵/回答古韵/回答现代）
+ 等待区 fragment 正常 + 页面结构无异常。
Edge TTS 当前网络不可用 → reply_mod 允许为空（UI 显示网络说明）。
"""
import sys, time
sys.path.insert(0, ".")
# 预热重依赖（脚本在同一进程内执行，import 只需一次）
import services.tts_client, services.llm_client  # noqa
import language.ancient_tts  # noqa
from streamlit.testing.v1 import AppTest

APP = "/home/lab006/.dsh/ungrouped/deepdive/donghan-guyin/robot/app.py"

t0 = time.time()
at = AppTest.from_file(APP)
RUNKW = dict(timeout=300)
at.run(**RUNKW)
print(f"initial render: {time.time()-t0:.1f}s")
assert not at.exception, at.exception

btns = [(i, b.label) for i, b in enumerate(at.button)]
print("buttons:", btns)
gen_idx = next(i for i, l in btns if l == "生成并朗读")

at.text_area[0].set_value("今日天气如何")
t1 = time.time()
at.button[gen_idx].click()
at.run(**RUNKW)
dt = time.time() - t1
print(f"click->return: {dt:.2f}s（异步方案应 <8s）")
assert dt < 8.0, "on_click 疑似仍在同步生成"
assert not at.exception, at.exception

# 轮询：fragment 每秒自刷新，主线程落盘后整页 rerun
t2 = time.time()
saw_thinking = False
for _ in range(120):
    job = at.session_state.get("gen_job")
    if job is None and at.session_state.get("last_result"):
        break
    time.sleep(1.5)
    at.run(**RUNKW)
    if at.exception:
        break
    if job is not None and job.get("result") is None:
        saw_thinking = True
else:
    raise SystemExit("超时：job 未完成")
total = time.time() - t2
print(f"worker + 落盘：{total:.1f}s | 见到等待态: {saw_thinking}")

assert not at.exception, at.exception
res = at.session_state["last_result"]
aud = res.get("audios", {})
print("audios:", {k: (len(v.get("data") or b""), v.get("kind"),
                     (v.get("text") or "")[:14])
                  for k, v in aud.items()})
assert res["reply"], "回复为空"
# 核心断言：两类古韵音频必须产出
assert aud.get("user", {}).get("data"), "缺 我的话·古韵"
assert aud.get("reply_anc", {}).get("data"), "缺 回答·古韵"
# 现代段：Edge 可用则有数据，断网则空（都不算失败）
print("reply_mod 字节:", len(aud.get("reply_mod", {}).get("data") or b""))
print("mode:", res["mode"], "| source:", res["source"],
      "| coverage:", res["coverage"])
print("play_note:", at.session_state.get("play_note"))
print("turns:", [(u, a[:12]) for u, a, m in at.session_state["turns"]])
assert len(at.session_state["turns"]) == 1

# 结果区按钮：每段音频各有一个 设备播放 + 下载
labels = [b.label for b in at.button]
dls = [d.label for d in at.download_button]
print("结果按钮:", labels)
print("下载按钮:", dls)
n_audio = sum(1 for v in aud.values() if v.get("data"))
assert labels.count("设备播放") == n_audio, "每段音频各应有 设备播放"
assert len(dls) == n_audio, "每段音频各应有 下载"
print("\n=== 三音频生成测试通过 ===")
