#!/usr/bin/env bash
# 连接蓝牙音箱并等待 A2DP sink 出现
bluetoothctl --timeout 20 connect 6D:4D:F2:66:E7:A9 2>&1 | grep -iE "connect|success|fail"
sleep 6
echo "=== 声卡(找 bluez) ==="
cat /proc/asound/cards
echo "=== PipeWire 蓝牙节点 ==="
pw-cli dump-objects 2>/dev/null | grep -iE "bluez|a2dp|BS-32D" | head
echo "=== 连接状态 ==="
bluetoothctl --timeout 5 info 6D:4D:F2:66:E7:A9 2>&1 | grep -iE "connected|paired"
