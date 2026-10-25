#!/usr/bin/env bash
echo "=== 连接音箱(已配对, 直接连) ==="
bluetoothctl --timeout 30 connect 6D:4D:F2:66:E7:A9 2>&1 | grep -iE "connect|success|fail"
sleep 8
echo "=== 连接状态 ==="
bluetoothctl --timeout 5 info 6D:4D:F2:66:E7:A9 2>&1 | grep -iE "connected|paired"
echo "=== 声卡(找 bluez/A2DP) ==="
cat /proc/asound/cards
echo "=== PipeWire 蓝牙 sink ==="
pw-cli dump-objects 2>/dev/null | grep -iE "bluez|a2dp|BS-32D" | head
