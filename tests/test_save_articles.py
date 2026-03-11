#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试保存文章功能
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from infoq_crawler import InfoQWeeklyCrawler  # noqa: E402
import logging  # noqa: E402


logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


def main():
    try:
        import config  # noqa: E402

        output_dir = config.OUTPUT_DIR
    except Exception:
        output_dir = str(PROJECT_ROOT / "output")

    crawler = InfoQWeeklyCrawler(output_dir)

    weekly = {
        "id": "909",
        "title": "909期 / 每周精要",
        "url": "https://www.infoq.cn/weekly/909",
        "date": "2026-01-17",
    }

    weekly_data = crawler._get_weekly_content(weekly)

    # 只取前3篇文章进行测试
    weekly_data["articles"] = weekly_data["articles"][:3]

    print(f"\n准备保存 {len(weekly_data['articles'])} 篇文章...")

    weekly_dir = crawler._save_weekly(weekly_data)

    if weekly_dir:
        print("\n✓ 保存成功！")
        print(f"目录: {weekly_dir}")

        md_files = sorted([f for f in weekly_dir.iterdir() if f.suffix == ".md"])
        print("\n保存的文件:")
        for f in md_files:
            print(f"  - {f.name}")
    else:
        print("\n✗ 保存失败")


if __name__ == "__main__":
    main()

