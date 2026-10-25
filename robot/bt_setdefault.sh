#!/usr/bin/env bash
echo "=== 所有 sink ==="
wpctl status 2>&1 | sed -n '/Sinks:/,/Sources:/p'
echo "=== 默认 sink ==="
wpctl status 2>&1 | grep -A1 "Default:" | head -4
echo
echo "=== 找 BS-32D 的 sink id 并设为默认 ==="
SINK_ID=$(wpctl status 2>&1 | awk '/Sinks:/{f=1} f && /BS-32D/{print $1; exit}')
echo "BS-32D sink id: $SINK_ID"
if [ -n "$SINK_ID" ]; then
  wpctl set-default-sink "$SINK_ID"
  echo "已设为默认"
fi
echo
echo "=== 设后默认 sink ==="
wpctl status 2>&1 | grep -A2 "Default:" | head -6
