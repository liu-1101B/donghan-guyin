#!/usr/bin/env bash
echo "=== 最近 bluetoothd 日志(找 A2DP/AVDTP 事件) ==="
journalctl -u bluetooth --no-pager -n 40 --since "2 min ago" 2>&1 | grep -iE "a2dp|avdtp|avrcp|connect|disconnect|profile|sep|device" | tail -25
echo
echo "=== 再次连接 ==="
bluetoothctl --timeout 30 connect 6D:4D:F2:66:E7:A9 2>&1 | grep -iE "connect|success|fail"
sleep 4
echo "=== 连接状态 ==="
bluetoothctl --timeout 5 info 6D:4D:F2:66:E7:A9 2>&1 | grep -iE "connected"
echo "=== 声卡 ==="
cat /proc/asound/cards
