#!/usr/bin/env bash
echo "=== 当前 sink(确认 BS-32D 是否还在) ==="
wpctl status 2>&1 | sed -n '/Sinks:/,/Sink endpoints/p'
echo
echo "=== 蓝牙连接状态 ==="
bluetoothctl --timeout 5 info 6D:4D:F2:66:E7:A9 2>&1 | grep -iE "connected"
echo
echo "=== 用节点名设音量(避免 id 漂移) ==="
wpctl status 2>&1 | grep "BS-32D"
ID=$(wpctl status 2>&1 | awk '/Sinks:/{f=1} f && /BS-32D/{print $1; exit}')
echo "当前 id: [$ID]"
if [ -n "$ID" ] && [ "$ID" != "│" ]; then
  wpctl set-volume 78 60% 2>/dev/null || wpctl set-volume "$ID" 60%
  echo "音量已设 60%"
  wpctl status 2>&1 | grep "BS-32D"
fi
