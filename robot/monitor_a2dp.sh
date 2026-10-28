#!/usr/bin/env bash
# A2DP 故障监视器（取证模式）
# 策略：开头播两次音确认通道活跃 → 之后**零音频流量**，仅做无副作用状态检查
#       （bluetoothctl info + wpctl 只读查询），让故障在空闲中自然发生。
# 故障判定：设备断开 / 蓝牙 sink 消失 / 默认输出被夺走 —— 任一即为故障
# 故障处理：抓完整快照（不重连、不恢复，保留现场），再观察 3 轮后退出
cd "$(dirname "$0")/.." || exit 1
MAC="F8:D3:F0:A9:08:68"
BT_NAME="Relink"
INTERVAL=10
MAXMIN=13
LOG=~/a2dp_monitor.log
SNAP=~/a2dp_fault_snapshot
mkdir -p "$SNAP"

state_check() {
    # 返回 0=健康, 1=异常; 输出状态串
    local conn="yes" sink="present" def="yes"
    [ "$(bluetoothctl --timeout 5 info $MAC 2>/dev/null | grep -c 'Connected: yes')" -eq 1 ] || conn="no"
    local st line
    st=$(wpctl status 2>/dev/null | sed -n '/Sinks:/,/Sink endpoints/p')
    line=$(echo "$st" | grep -F "$BT_NAME" | grep -F '[vol:')
    [ -n "$line" ] || sink="gone"
    echo "$line" | grep -qF '* ' || def="no"
    echo "connected=$conn sink=$sink default=$def"
    if [ "$conn" = no ] || [ "$sink" = gone ] || [ "$def" = no ]; then
        return 1
    fi
    return 0
}

snapshot() {
    local ts snapdir
    ts=$(date +%s)
    snapdir="$SNAP/${ts}"
    mkdir -p "$snapdir"
    {
        echo "=== 故障时刻 $(date --iso-8601=ns) ==="
        echo "=== bluetoothctl info ==="
        bluetoothctl info $MAC
        echo "=== wpctl status ==="
        wpctl status
        echo "=== pactl list cards (前80行) ==="
        pactl list cards 2>&1 | head -80
        echo "=== pactl list sinks short ==="
        pactl list sinks short
        echo "=== 播放/音频相关进程 ==="
        ps -eo pid,stat,etime,cmd | grep -E '[p]w-play|[p]ipewire|[w]ireplumber'
        echo "=== 故障后追加一次探测音(确认是否卡死型) ==="
        timeout 8 pw-play audio_out/tone440.wav 2>&1
        echo "probe rc=$? (0=能播, 124=通道卡死)"
    } > "$snapdir/state.txt" 2>&1
    sudo journalctl -u bluetooth --since "-5 min" --no-pager > "$snapdir/bluetooth-5min.log" 2>&1
    journalctl --user -u pipewire -u wireplumber --since "-5 min" --no-pager > "$snapdir/audio-5min.log" 2>&1
    echo "[monitor] 快照 → $snapdir (未做任何恢复)" | tee -a "$LOG"
}

echo "[monitor] $(date --iso-8601=seconds) 开始 (间隔 ${INTERVAL}s, 最长 ${MAXMIN}min)" | tee -a "$LOG"
# 确认通道活跃（两次短音）
for i in 1 2; do
    sleep 3
    rc=$(timeout 10 pw-play audio_out/tone440.wav 2>&1; echo $?)
    echo "[monitor] $(date --iso-8601=seconds) 确认音 #$i rc=$rc" | tee -a "$LOG"
done

start=$(date +%s)
n=0
fault_seen=0
while :; do
    n=$((n+1))
    now=$(date +%s)
    if [ $((now - start)) -gt $((MAXMIN * 60)) ]; then
        echo "[monitor] $(date --iso-8601=seconds) 到达 ${MAXMIN}min, 期间未见状态型故障" | tee -a "$LOG"
        # 收尾: 做一次探测音, 判断是否"通道卡死"型(状态健康但播不出)
        rc=$(timeout 8 pw-play audio_out/tone440.wav 2>&1; echo $?)
        echo "[monitor] 收尾探测音 rc=$rc (0=仍通, 124=卡死型故障)" | tee -a "$LOG"
        [ "$rc" != "0" ] && snapshot
        break
    fi
    s=$(state_check); s_rc=$?
    if [ $fault_seen -eq 0 ] && [ $s_rc -ne 0 ]; then
        echo "[monitor] $(date --iso-8601=seconds) *** 状态型故障! $s (第 $n 轮) ***" | tee -a "$LOG"
        snapshot
        fault_seen=1
    else
        # 每 6 轮(60s)加一次探测音, 捕捉"通道卡死"型(状态健康但播不出)
        if [ $((n % 6)) -eq 0 ]; then
            rc=$(timeout 8 pw-play audio_out/tone440.wav >/dev/null 2>&1; echo $?)
            echo "[monitor] $(date --iso-8601=seconds) ok: $s | 60s 探测音 rc=$rc" | tee -a "$LOG"
            if [ $fault_seen -eq 0 ] && [ "$rc" != "0" ]; then
                echo "[monitor] $(date --iso-8601=seconds) *** 卡死型故障! probe rc=$rc (第 $n 轮) ***" | tee -a "$LOG"
                snapshot
                fault_seen=1
            fi
        else
            echo "[monitor] $(date --iso-8601=seconds) ok: $s" | tee -a "$LOG"
        fi
    fi
    # 故障后观察 3 轮再退出
    if [ $fault_seen -eq 1 ] && [ $((n % 3)) -eq 0 ]; then
        echo "[monitor] 故障已观察 3 轮, 退出(保留现场)" | tee -a "$LOG"
        break
    fi
    sleep "$INTERVAL"
done
echo "[monitor] $(date --iso-8601=seconds) 结束, 共 $n 轮" | tee -a "$LOG"
