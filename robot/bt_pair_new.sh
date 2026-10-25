#!/usr/bin/env bash
DEV="F8:D3:F0:A9:08:68"
echo "=== 配对 ==="
bluetoothctl --timeout 30 pair $DEV 2>&1 | grep -iE "pair|success|fail"
echo "=== 信任 + 连接 ==="
bluetoothctl --timeout 5 trust $DEV 2>&1 | grep -i trust
bluetoothctl --timeout 30 connect $DEV 2>&1 | grep -iE "connect|success|fail"
sleep 10
echo "=== 连接状态 ==="
bluetoothctl --timeout 5 info $DEV 2>&1 | grep -iE "name|connected|paired"
echo "=== PipeWire 里的新设备 ==="
wpctl status 2>&1 | sed -n '/Devices:/,/Sinks:/p'
echo "=== sink 列表 ==="
wpctl status 2>&1 | sed -n '/Sinks:/,/Sink endpoints/p'
