#!/usr/bin/env bash
# 重新配对流程
echo "=== 断开并移除旧配对 ==="
bluetoothctl --timeout 5 remove 6D:4D:F2:66:E7:A9 2>&1 | grep -v "^$"
echo "=== 重新配对 ==="
bluetoothctl --timeout 30 pair 6D:4D:F2:66:E7:A9 2>&1 | grep -iE "pair|success|fail"
echo "=== 信任 + 连接 ==="
bluetoothctl --timeout 5 trust 6D:4D:F2:66:E7:A9 2>&1 | grep -iE "trust"
bluetoothctl --timeout 30 connect 6D:4D:F2:66:E7:A9 2>&1 | grep -iE "connect|success|fail"
sleep 6
echo "=== 声卡 ==="
cat /proc/asound/cards
echo "=== PipeWire 蓝牙节点 ==="
pw-cli dump-objects 2>/dev/null | grep -iE "bluez|a2dp" | head
echo "=== 状态 ==="
bluetoothctl --timeout 5 info 6D:4D:F2:66:E7:A9 2>&1 | grep -iE "connected|paired|bonded"
