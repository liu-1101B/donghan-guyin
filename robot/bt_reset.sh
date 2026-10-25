#!/usr/bin/env bash
# 强制重置 A2DP：断开 → 等 → 重连 → 等 sink 稳定 → 设为默认输出 → 测试音自检
# 适用故障：
#  - A2DP profile 断开但 L2CAP 仍在（蓝牙 sink 消失、默认掉回空接口 → 无声）
#  - A2DP 通道挂死（pw-play 永久阻塞）
DEV="${1:-F8:D3:F0:A9:08:68}"
echo "=== 断开 ==="
bluetoothctl --timeout 10 disconnect $DEV 2>&1 | grep -iE "disconnect|success|fail"
sleep 3
echo "=== 重连 ==="
bluetoothctl --timeout 30 connect $DEV 2>&1 | grep -iE "connect|success|fail"
sleep 10
echo "=== 设为默认输出 ==="
NAME=$(bluetoothctl --timeout 5 info $DEV 2>/dev/null \
       | awk '/^\tName:/ { sub(/^\tName:[ \t]*/, ""); print; exit }')
SID=$(wpctl status 2>/dev/null \
      | grep -F "$NAME" | grep -F '[vol:' | grep -oE '[0-9]+' | head -1)
if [ -n "$SID" ]; then
    wpctl set-default $SID 2>&1 && echo "默认输出 → sink $SID ($NAME)"
else
    echo "警告: 未找到蓝牙 sink ($NAME)，A2DP 可能未建立"
fi
echo "=== sink 状态 ==="
wpctl status 2>&1 | sed -n '/Sinks:/,/Sink endpoints/p' | grep -E "\*|vol:"
echo "=== 播测试音(限时 15 秒) ==="
timeout 15 pw-play audio_out/tone440.wav 2>&1
echo "pw-play 返回: $? (0=正常播完, 124=卡死)"
