#!/usr/bin/env bash
# 蓝牙 A2DP 音频栈诊断
echo "=== bluez5-media 服务 ==="
systemctl status bluez5-media 2>&1 | head -5
echo
echo "=== /etc/bluetooth/main.conf 关键项 ==="
grep -vE "^\s*#|^\s*$" /etc/bluetooth/main.conf 2>/dev/null
echo
echo "=== pipewire 已加载模块 ==="
pw-cli dump-objects 2>/dev/null | grep -E "module.name" | head -15
echo
echo "=== pipewire 配置里有无 bluetooth 模块 ==="
grep -rn "blue" /usr/share/pipewire/pipewire.conf /etc/pipewire/ 2>/dev/null | head -5
echo
echo "=== wireplumber 蓝牙上下文 ==="
grep -rn "blue" /usr/share/wireplumber/ 2>/dev/null | head -5
echo
echo "=== 当前 ALSA 声卡 ==="
cat /proc/asound/cards
echo
echo "=== 蓝牙设备连接状态 ==="
bluetoothctl --timeout 5 info 6D:4D:F2:66:E7:A9 2>&1 | grep -iE "name|connected|paired" | head -3
