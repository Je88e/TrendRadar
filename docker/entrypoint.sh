#!/bin/bash
set -e

# 检查配置文件
if [ ! -f "/app/config/config.yaml" ] || [ ! -f "/app/config/frequency_words.txt" ]; then
    echo "❌ 配置文件缺失"
    exit 1
fi

case "${RUN_MODE:-cron}" in
"once")
    echo "🔄 单次执行"
    exec python -m trendradar
    ;;
"cron")
    # 校验 CRON_SCHEDULE 格式（仅允许 cron 表达式合法字符）
    CRON_EXPR="${CRON_SCHEDULE:-*/30 * * * *}"
    if ! echo "$CRON_EXPR" | grep -qE '^[0-9*/,[:space:]-]+$'; then
        echo "❌ CRON_SCHEDULE 格式非法: $CRON_EXPR"
        exit 1
    fi

    # 生成 crontab
    echo "$CRON_EXPR cd /app && python -m trendradar" > /tmp/crontab

    echo "📅 生成的crontab内容:"
    cat /tmp/crontab

    if ! /usr/local/bin/supercronic -test /tmp/crontab; then
        echo "❌ crontab格式验证失败"
        exit 1
    fi

    # 立即执行一次（如果配置了）
    if [ "${IMMEDIATE_RUN:-false}" = "true" ]; then
        echo "▶️ 立即执行一次"
        python -m trendradar
    fi

    # 启动 Web 服务器
    echo "🌐 启动 Web 服务器..."
    python manage.py start_webserver

    echo "⏰ 启动supercronic: $CRON_EXPR"
    echo "🎯 supercronic 将作为 PID 1 运行"

    exec /usr/local/bin/supercronic -passthrough-logs /tmp/crontab
    ;;
"serve")
    echo "🌐 长驻调度 + 管理后台"
    echo "  管理后台: http://localhost:${WEBSERVER_PORT:-8080}/admin/"
    echo "  报告首页: http://localhost:${WEBSERVER_PORT:-8080}/"
    echo "  ADMIN_HOST=${ADMIN_HOST:-0.0.0.0}"
    echo "  WEBSERVER_PORT=${WEBSERVER_PORT:-8080}"
    echo "🔒 安全提示: 远端暴露请自加反代鉴权 (设计 Q5=C)"
    exec python -m trendradar --serve
    ;;
*)
    exec "$@"
    ;;
esac
