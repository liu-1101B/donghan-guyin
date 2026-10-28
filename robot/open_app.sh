#!/usr/bin/env bash
# 启动当前克隆目录中的机器人前端；不再依赖开发机上的固定绝对路径。
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT"

APP_REL="robot/app.py"
STREAMLIT="$ROOT/.venv/bin/streamlit"
BASE_PORT="${GUYUN_ROBOT_PORT:-8501}"

if [[ ! -x "$STREAMLIT" ]]; then
    echo "[古韵机器人] 未找到当前仓库的 Streamlit：$STREAMLIT"
    echo "请先在仓库根目录创建 .venv 并安装 requirements-robot.txt。"
    exit 1
fi
if [[ ! -f "$ROOT/$APP_REL" ]]; then
    echo "[古韵机器人] 当前仓库缺少前端入口：$ROOT/$APP_REL"
    exit 1
fi
if ! [[ "$BASE_PORT" =~ ^[0-9]+$ ]]; then
    echo "GUYUN_ROBOT_PORT 必须是数字端口；当前值：$BASE_PORT"
    exit 1
fi

port_listening() {
    if command -v ss >/dev/null 2>&1; then
        ss -H -ltn 2>/dev/null |
            awk -v suffix=":$1" '$4 ~ (suffix "$") { found=1 } END { exit !found }'
    else
        curl -s -o /dev/null -m 1 "http://127.0.0.1:$1/"
    fi
}

find_current_app_pid() {
    local wanted_port="$1" pid args
    while read -r pid args; do
        if [[ "$args" == *"$STREAMLIT"* &&
              "$args" == *"run $APP_REL"* &&
              "$args" == *"--server.port $wanted_port"* ]]; then
            echo "$pid"
            return 0
        fi
    done < <(ps -eo pid=,args=)
    return 1
}

wait_for_http() {
    local wanted_port="$1"
    for _ in $(seq 1 45); do
        if curl -s -o /dev/null -m 2 "http://127.0.0.1:$wanted_port/"; then
            return 0
        fi
        sleep 1
    done
    return 1
}

# 复用当前仓库已经启动的机器人 UI；若 8501 被旧应用占用，则寻找下一个空闲端口。
PORT=""
MAX_PORT=$((BASE_PORT + 9))
for candidate in $(seq "$BASE_PORT" "$MAX_PORT"); do
    if find_current_app_pid "$candidate" >/dev/null 2>&1; then
        PORT="$candidate"
        if wait_for_http "$PORT"; then
            echo "[古韵机器人] 复用当前仓库前端：http://127.0.0.1:$PORT"
            (xdg-open "http://127.0.0.1:$PORT" >/dev/null 2>&1 &) || true
            exit 0
        fi
        echo "[古韵机器人] 检测到本仓库前端进程，但端口 $PORT 未能正常响应。"
        LOG_FILE="$ROOT/.server-$PORT.log"
        [[ ! -f "$LOG_FILE" ]] || tail -n 40 "$LOG_FILE"
        exit 1
    fi
    if ! port_listening "$candidate"; then
        PORT="$candidate"
        break
    fi
done

if [[ -z "$PORT" ]]; then
    echo "[古韵机器人] 端口 $BASE_PORT-$MAX_PORT 均已被占用。"
    echo "可用 GUYUN_ROBOT_PORT=端口号 指定另一组起始端口。"
    exit 1
fi

LOG_FILE="$ROOT/.server-$PORT.log"
echo "[古韵机器人] 仓库目录：$ROOT"
echo "[古韵机器人] 前端入口：$ROOT/$APP_REL"
echo "[古韵机器人] 启动地址：http://127.0.0.1:$PORT"
setsid nohup "$STREAMLIT" run "$APP_REL" \
    --server.port "$PORT" --server.address 0.0.0.0 --server.headless true \
    > "$LOG_FILE" 2>&1 </dev/null &

if ! wait_for_http "$PORT"; then
    echo "[古韵机器人] 启动失败，最近日志如下："
    tail -n 60 "$LOG_FILE" || true
    exit 1
fi

(xdg-open "http://127.0.0.1:$PORT" >/dev/null 2>&1 &) || true
echo "[古韵机器人] 已就绪：http://127.0.0.1:$PORT"
