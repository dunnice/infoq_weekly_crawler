#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试图文顺序是否正确
"""

import sys
from pathlib import Path

# 添加项目根目录
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from infoq_crawler import InfoQWeeklyCrawler  # noqa: E402
import logging  # noqa: E402


logging.basicConfig(level=logging.INFO)


def test_article_order():
    """测试单篇文章的图文顺序"""
    try:
        import config  # noqa: E402

        output_dir = config.OUTPUT_DIR
    except Exception:
        output_dir = str(PROJECT_ROOT / "output")

    crawler = InfoQWeeklyCrawler(output_dir=output_dir)

    # 测试一篇文章
    test_url = "https://www.infoq.cn/article/GPT-5-2-breakthrough"
    weekly_id = "test"

    print(f"正在测试文章: {test_url}")
    print("=" * 60)

    article = crawler._get_article_detail(test_url, weekly_id)

    if article:
        print(f"\n标题: {article['title']}")
        print(f"作者: {article['author']}")
        print(f"发布时间: {article['publish_time']}")
        print(f"\n图片数量: {len(article['images'])}")
        print(f"内容长度: {len(article['content'])} 字符")

        content = article["content"]
        lines = content.split("\n")

        print("\n内容结构预览（前50行）:")
        print("-" * 60)
        for i, line in enumerate(lines[:50], 1):
            if line.strip():
                if line.startswith("![["):
                    print(f"{i:3d}. [图片] {line[:60]}")
                elif line.startswith("#"):
                    print(f"{i:3d}. [标题] {line[:60]}")
                else:
                    print(f"{i:3d}. [文本] {line[:60]}")

        image_positions = []
        text_positions = []
        for i, line in enumerate(lines):
            if line.strip():
                if line.startswith("![["):
                    image_positions.append(i)
                elif not line.startswith("#"):
                    text_positions.append(i)

        print(f"\n图片位置: {image_positions[:10]}...")
        print(f"文本位置: {text_positions[:10]}...")

        if image_positions and text_positions:
            mixed = any(any(t < img < t + 10 for t in text_positions) for img in image_positions)
            if mixed:
                print("\n✅ 图文顺序正确：图片和文本交替出现")
            else:
                print("\n❌ 图文顺序可能有问题：图片集中在某个位置")
    else:
        print("❌ 获取文章失败")

    crawler._close_driver()


if __name__ == "__main__":
    test_article_order()

