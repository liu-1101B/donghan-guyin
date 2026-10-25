#!/usr/bin/env bash
echo "=== 声卡 ==="
cat /proc/asound/cards
echo
echo "=== PipeWire 全部节点 ==="
pw-cli dump-objects 2>/dev/null | grep "node.name" | head -20
echo
echo "=== wireplumber 日志(蓝牙相关) ==="
journalctl -u wireplumber --no-pager --since "5 min ago" 2>&1 | grep -iE "bluez|bluetooth|a2dp" | tail -10
journalctl -u pipewire --no-pager --since "5 min ago" 2>&1 | grep -iE "bluez|bluetooth|a2dp" | tail -10
