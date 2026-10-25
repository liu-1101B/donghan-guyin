#!/usr/bin/env bash
# 强制重置 A2DP：断开 → 等 → 重连 → 等 sink 稳定 → 播测试音
DEV="F8:D3:F0:A9:08:68"
echo "=== 断开 ==="
bluetoothctl --timeout 10 disconnect $DEV 2>&1 | grep -iE "disconnect|success|fail"
sleep 3
echo "=== 重连 ==="
bluetoothctl --timeout 30 connect $DEV 2>&1 | grep -iE "connect|success|fail"
sleep 10
echo "=== sink 状态 ==="
wpctl status 2>&1 | sed -n '/Sinks:/,/Sink endpoints/p' | grep -E "Relink|\*"
echo "=== 播测试音(限时 15 秒) ==="
timeout 15 pw-play audio_out/tone440.wav 2>&1
echo "pw-play 返回: $? (0=正常播完, 124=卡住超时)"
