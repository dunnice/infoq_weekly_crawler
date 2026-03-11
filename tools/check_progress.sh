#!/bin/bash
# InfoQ 爬虫进度监控脚本

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=========================================="
echo "InfoQ 周刊爬虫进度监控"
echo "=========================================="
echo ""

# 检查进程
if pgrep -f "python.*infoq_crawler\.py" > /dev/null; then
  echo "✅ 爬虫正在运行中..."
else
  echo "❌ 爬虫未运行"
fi
echo ""

# 显示最新日志（以项目根目录的日志为准）
LOG_FILE="$PROJECT_ROOT/infoq_crawler.log"
echo "📋 最新日志（最后 10 行）："
echo "------------------------------------------"
if [ -f "$LOG_FILE" ]; then
  tail -10 "$LOG_FILE"
else
  echo "未找到日志文件: $LOG_FILE"
fi
echo ""

# 从 config.py 读取输出目录（失败则提示）
OUTPUT_DIR="$(
  (cd "$PROJECT_ROOT" && python3 -c 'import config; print(getattr(config, "OUTPUT_DIR", ""))' 2>/dev/null) || true
)"

if [ -z "$OUTPUT_DIR" ]; then
  echo "⚠️  未能从 config.py 读取 OUTPUT_DIR，请先配置输出目录。"
  exit 0
fi

if [ -d "$OUTPUT_DIR" ]; then
  echo "📁 输出目录状态："
  echo "------------------------------------------"

  WEEKLY_COUNT=$(find "$OUTPUT_DIR" -maxdepth 1 -type d -name "周刊_*" | wc -l | tr -d ' ')
  echo "周刊目录数量: $WEEKLY_COUNT"

  LATEST_WEEKLY=$(find "$OUTPUT_DIR" -maxdepth 1 -type d -name "周刊_*" | sort -r | head -1)
  if [ -n "$LATEST_WEEKLY" ]; then
    echo "最新周刊: $(basename "$LATEST_WEEKLY")"

    MD_COUNT=$(find "$LATEST_WEEKLY" -name "*.md" | wc -l | tr -d ' ')
    echo "  - Markdown 文件: $MD_COUNT 个"

    IMG_COUNT=$(find "$LATEST_WEEKLY/attachments" -type f 2>/dev/null | wc -l | tr -d ' ')
    echo "  - 下载图片: $IMG_COUNT 张"
  fi
else
  echo "⚠️  输出目录不存在: $OUTPUT_DIR"
fi

echo ""
echo "=========================================="
echo "提示: 运行 'bash tools/check_progress.sh' 查看进度"
echo "=========================================="

