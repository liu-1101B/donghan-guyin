#!/usr/bin/env bash
# 连接并激活蓝牙音箱输出（配对已做过，只需连接 + 确保是默认输出 + 音量非 0）
# 用法: ./robot/bt_connect.sh [MAC]   (默认: Relink 蓝牙设备)
set -u
MAC="${1:-F8:D3:F0:A9:08:68}"

echo "==> 连接 $MAC"
bluetoothctl --timeout 30 connect "$MAC" 2>&1 | grep -iE "connect|success|fail"
sleep 6

# 取该 MAC 对应的设备名（PipeWire sink 用设备名，不用 MAC）
# 注意: info 的字段行带制表符缩进，且会混入 CHG 事件行
NAME="$(bluetoothctl --timeout 5 info "$MAC" 2>&1 | awk '
  /^\tName:/ { sub(/^\tName:[ \t]*/, ""); print; exit }')"
if [ -z "${NAME:-}" ]; then
  echo "!! 取不到设备名，检查 MAC 是否正确: $MAC"
  exit 1
fi
echo "==> 设备名: $NAME"

echo "==> 当前 sink 列表:"
wpctl status 2>&1 | sed -n '/Sinks:/,/Sink endpoints/p'

# 按设备名匹配 sink id（sink 行形如: │ * 90. 设备名 [vol: 0.40]，
# 用 "含设备名 且 含 [vol:" 两个条件排除 Devices 段同名行）
SINK_ID="$(wpctl status 2>&1 | grep -F "$NAME" | grep -F '[vol:' \
  | grep -oE '[0-9]+' | head -1)"

if [ -z "${SINK_ID:-}" ]; then
  echo "!! 未找到名为 [$NAME] 的蓝牙 sink"
  exit 1
fi

echo "==> sink id: $SINK_ID ($NAME)，设为默认输出"
wpctl set-default "$SINK_ID" 2>&1

VOL="$(wpctl get-volume "$SINK_ID" 2>/dev/null | grep -oE '[0-9]+\.[0-9]+' | head -1)"
echo "==> 当前音量: ${VOL:-?}"
if [ -n "${VOL:-}" ]; then
  LOW=$(awk -v v="$VOL" 'BEGIN{print (v < 0.10) ? 1 : 0}')
  [ "$LOW" = "1" ] && { echo "==> 音量过低，抬到 60%"; wpctl set-volume "$SINK_ID" 60% 2>&1; }
fi

echo "==> 默认输出:"
wpctl status 2>&1 | sed -n '/Sinks:/,/Sink endpoints/p' | grep -E "^\s*[│ ]*\*"
echo "完成。现在 python -m robot.main 的播放会走该蓝牙设备。"
