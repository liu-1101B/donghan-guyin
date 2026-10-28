"""AppTest 验证：东汉古韵模式下同样产出三段音频 + IPA 区正常"""
import sys, time
sys.path.insert(0, ".")
import services.tts_client, services.llm_client  # noqa
import language.ancient_tts  # noqa
from streamlit.testing.v1 import AppTest

APP = "/home/lab006/.dsh/ungrouped/deepdive/donghan-guyin/robot/app.py"

t0 = time.time()
at = AppTest.from_file(APP)
RUNKW = dict(timeout=300)
at.run(**RUNKW)
assert not at.exception, at.exception
print(f"initial render: {time.time()-t0:.1f}s")

# 切到东汉古韵（radio[0] 的 label 是"模式"，选项在 options 里）
at.radio[0].set_value("东汉古韵")
at.run(**RUNKW)
assert not at.exception, at.exception

btns = [(i, b.label) for i, b in enumerate(at.button)]
gen_idx = next(i for i, l in btns if l == "生成并朗读")

at.text_area[0].set_value("你从哪里来")
t1 = time.time()
at.button[gen_idx].click()
at.run(**RUNKW)
print(f"click->return: {time.time()-t1:.2f}s")
assert not at.exception, at.exception

t2 = time.time()
for _ in range(120):
    job = at.session_state.get("gen_job")
    if job is None and at.session_state.get("last_result"):
        break
    time.sleep(1.5)
    at.run(**RUNKW)
    if at.exception:
        break
else:
    raise SystemExit("超时")
print(f"worker + 落盘：{time.time()-t2:.1f}s")
assert not at.exception, at.exception

res = at.session_state["last_result"]
aud = res.get("audios", {})
print("mode:", res["mode"], "| source:", res["source"],
      "| coverage:", res["coverage"])
print("audios:", {k: (len(v.get("data") or b""), (v.get("text") or "")[:16])
                  for k, v in aud.items()})
assert res["mode"] == "ancient"
assert aud.get("user", {}).get("data"), "缺 我的话·古韵"
assert aud.get("reply_anc", {}).get("data"), "缺 回答·古韵"
# IPA 区（古韵模式）
md = " ".join(m.value for m in at.markdown)
assert "东汉洛阳音 IPA" in md, "缺 IPA 区"
n_audio = sum(1 for v in aud.values() if v.get("data"))
labels = [b.label for b in at.button]
assert labels.count("设备播放") == n_audio, "每段音频各应有 设备播放"
print("\n=== 古韵模式三音频测试通过 ===")
