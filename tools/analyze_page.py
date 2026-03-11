#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
分析 InfoQ 文章页面结构（用于选择器调试）
"""

import json
import time
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "tests" / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)


def analyze_page(url: str):
    """分析页面结构"""
    chrome_options = Options()
    chrome_options.add_argument("--window-size=1920,1080")
    # 如果需要无头模式，打开下一行
    # chrome_options.add_argument("--headless")

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)

    snapshot_path = DATA_DIR / "page_snapshot.html"
    screenshot_path = DATA_DIR / "page_screenshot.png"
    analysis_path = DATA_DIR / "page_analysis.json"

    try:
        print(f"正在访问: {url}")
        driver.get(url)

        print("等待页面加载...")
        time.sleep(5)

        html = driver.page_source
        snapshot_path.write_text(html, encoding="utf-8")
        print(f"✅ 页面 HTML 已保存到: {snapshot_path}")

        driver.save_screenshot(str(screenshot_path))
        print(f"✅ 页面截图已保存到: {screenshot_path}")

        soup = BeautifulSoup(html, "html.parser")

        print("\n" + "=" * 60)
        print("页面结构分析")
        print("=" * 60)

        print("\n1. 标题元素:")
        title_candidates = []
        for selector in ["h1", ".title", ".article-title", "article h1"]:
            if selector.startswith("."):
                elems = soup.find_all(class_=selector.lstrip("."))
            elif " " in selector:
                parts = selector.split(" ")
                elems = soup.find_all(parts[0], class_=parts[1].lstrip("."))
            else:
                elems = soup.find_all(selector)
            for elem in elems[:3]:
                text = elem.get_text(strip=True)
                if text and len(text) > 10:
                    title_candidates.append(
                        {
                            "selector": selector,
                            "text": text[:100],
                            "tag": elem.name,
                            "class": elem.get("class", []),
                        }
                    )

        for i, title in enumerate(title_candidates[:5], 1):
            print(f"  {i}. {title['selector']}: {title['text']}")

        print("\n2. 内容区域候选:")
        content_candidates = []
        selectors = [
            "article",
            ".article-content",
            ".article-body",
            ".content",
            ".post-content",
            "main",
            ".main-content",
            '[class*="article"]',
            '[class*="content"]',
        ]

        for selector in selectors:
            try:
                if selector.startswith("."):
                    elems = soup.find_all(class_=lambda x: x and selector.lstrip(".") in str(x))
                elif selector.startswith("["):
                    if 'class*="' in selector:
                        class_name = selector.split('class*="')[1].split('"')[0]
                        elems = soup.find_all(class_=lambda x: x and class_name in str(x))
                    else:
                        elems = []
                else:
                    elems = soup.find_all(selector)

                for elem in elems[:3]:
                    text = elem.get_text(strip=True)
                    if text and len(text) > 100:
                        content_candidates.append(
                            {
                                "selector": selector,
                                "text_length": len(text),
                                "text_preview": text[:200],
                                "tag": elem.name,
                                "class": elem.get("class", []),
                                "id": elem.get("id", ""),
                            }
                        )
            except Exception:
                pass

        content_candidates.sort(key=lambda x: x["text_length"], reverse=True)

        for i, content in enumerate(content_candidates[:5], 1):
            print(f"  {i}. {content['selector']} (长度: {content['text_length']})")
            print(f"     标签: {content['tag']}, class: {content['class']}, id: {content['id']}")
            print(f"     预览: {content['text_preview'][:150]}...")

        print("\n3. 图片元素:")
        images = soup.find_all("img")
        print(f"  找到 {len(images)} 个图片元素")

        image_info = []
        for img in images[:10]:
            src = img.get("src") or img.get("data-src") or img.get("data-original", "")
            if src and not src.startswith("data:"):
                image_info.append(
                    {
                        "src": src[:100],
                        "alt": img.get("alt", ""),
                        "class": img.get("class", []),
                        "parent": img.find_parent().name if img.find_parent() else None,
                    }
                )

        for i, img in enumerate(image_info[:5], 1):
            print(f"  {i}. src: {img['src']}")
            print(f"     alt: {img['alt']}, parent: {img['parent']}")

        analysis = {
            "url": url,
            "title_candidates": title_candidates[:5],
            "content_candidates": content_candidates[:5],
            "image_count": len(images),
            "image_info": image_info[:10],
        }

        analysis_path.write_text(json.dumps(analysis, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n✅ 分析结果已保存到: {analysis_path}")

        print("\n" + "=" * 60)
        print("分析完成！")
        print("=" * 60)
        print("\n生成的文件:")
        print(f"  - {snapshot_path} (页面 HTML)")
        print(f"  - {screenshot_path} (页面截图)")
        print(f"  - {analysis_path} (分析结果)")

    finally:
        print("\n关闭浏览器...")
        driver.quit()


if __name__ == "__main__":
    test_url = "https://www.infoq.cn/news/Nb7WV3WYhhCoGdlq6MZy"
    analyze_page(test_url)

