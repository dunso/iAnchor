#!/bin/bash
# ============================================================
# iAnchor WebUI 停止脚本
# 用法: bash stop_ui.sh
# ============================================================
PIDFILE="/tmp/ianchor_webui.pid"

if [ ! -f "$PIDFILE" ]; then
    echo "WebUI 未在运行 (无 PID 文件)"
    exit 0
fi

PID=$(cat "$PIDFILE")

if kill -0 "$PID" 2>/dev/null; then
    kill "$PID"
    sleep 1
    if kill -0 "$PID" 2>/dev/null; then
        kill -9 "$PID"
        echo "WebUI 已强制停止 (PID: $PID)"
    else
        echo "WebUI 已停止 (PID: $PID)"
    fi
else
    echo "WebUI 进程不存在 (PID: $PID)"
fi

rm -f "$PIDFILE"
