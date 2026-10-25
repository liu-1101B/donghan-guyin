#!/usr/bin/env bash
echo "=== /sys/class/sound (所有声卡设备) ==="
ls /sys/class/sound/
echo
echo "=== bluez A2DP D-Bus 服务 ==="
busctl --user list 2>/dev/null | grep -i bluez || busctl list 2>/dev/null | grep -i bluez
echo
echo "=== 直接问 bluez: 音箱的 A2DP 传输状态 ==="
busctl --user introspect org.bluez /org/bluez/hci0/dev_6D_4D_F2_66_E7_A9 2>&1 | head -5
busctl --user call org.bluez /org/bluez/hci0/dev_6D_4D_F2_66_E7_A9 org.freedesktop.DBus.Properties Get sa sv org.bluez.Device Connected 2>&1 | head -3
echo
echo "=== pw-cli 基本状态 ==="
pw-cli info 2>&1 | head -10
echo
echo "=== wpctl 是否存在 ==="
which wpctl && wpctl status 2>&1 | head -30
