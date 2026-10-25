#!/usr/bin/env bash
# A2DP 档案诊断
echo "=== 音箱(BS-32D)上报的 UUID(看它是否提供 A2DP Sink) ==="
bluetoothctl --timeout 5 info 6D:4D:F2:66:E7:A9 2>&1 | grep -iE "uuid|class"
echo
echo "=== 控制器是否支持 A2DP Sink(本机作为音频发送方) ==="
bluetoothctl --timeout 5 show 2>&1 | grep -iE "a2dp|advanced"
echo "(空 = bluez 未上报 A2DP Sink 能力)"
echo
echo "=== main.conf 的 AVDTP/Policy 段完整内容 ==="
sed -n '/\[AVDTP\]/,/^\[/p' /etc/bluetooth/main.conf
echo
echo "=== bluetooth 服务状态 + 最近日志 ==="
systemctl is-active bluetooth
journalctl -u bluetooth --no-pager -n 25 2>&1 | tail -25
echo
echo "=== bluez media 进程/服务是否存在 ==="
systemctl list-units --all 2>/dev/null | grep -i bluez
pgrep -a bluez | head -5
