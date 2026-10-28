#!/usr/bin/env bash
# 古韵机器人启动器：确保 8501 服务在跑，然后打开浏览器
ROOT="/home/lab006/.dsh/ungrouped/deepdive/donghan-guyin"
cd "$ROOT" || exit 1

if ! curl -s -o /dev/null -m 2 http://127.0.0.1:8501/; then
    setsid nohup "$ROOT/.venv/bin/streamlit" run robot/app.py \
        --server.port 8501 --server.address 0.0.0.0 --server.headless true \
        > "$ROOT/.server.log" 2>&1 &
    for _ in $(seq 1 90); do
        curl -s -o /dev/null -m 2 http://127.0.0.1:8501/ && break
        sleep 1
    done
fi

(xdg-open "http://127.0.0.1:8501" >/dev/null 2>&1 &)
exit 0
