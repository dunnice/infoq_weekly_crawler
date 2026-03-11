#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试 DOM 顺序处理逻辑
"""

from bs4 import BeautifulSoup

# 模拟一个包含图文混合的 HTML
html_content = """
<div class="article-content">
    <p>这是第一段文字。</p>
    <img src="image1.jpg" alt="图片1" />
    <p>这是第二段文字。</p>
    <p>这是第三段文字。</p>
    <img src="image2.jpg" alt="图片2" />
    <h2>这是一个标题</h2>
    <p>这是第四段文字。</p>
    <img src="image3.jpg" alt="图片3" />
    <p>这是第五段文字。</p>
</div>
"""

soup = BeautifulSoup(html_content, "html.parser")
content_area = soup.find("div", class_="article-content")

# 模拟处理逻辑
paragraphs = []
processed_elements = set()


def process_element(element, depth=0):
    """递归处理元素，保持DOM顺序"""
    if element in processed_elements:
        return
    processed_elements.add(element)

    # 如果是图片元素
    if element.name == "img":
        img_src = element.get("src")
        alt = element.get("alt", "图片")
        paragraphs.append(f"[图片: {img_src} - {alt}]")
        return

    # 如果是文本元素
    if element.name in ["p", "h1", "h2", "h3", "h4", "h5", "h6"]:
        text = element.get_text(strip=True)
        if text:
            if element.name == "p":
                paragraphs.append(f"[文本: {text}]")
            elif element.name in ["h1", "h2", "h3", "h4", "h5", "h6"]:
                level = int(element.name[1])
                paragraphs.append(f"[标题{level}: {text}]")
        return

    # 如果是容器元素，递归处理子元素
    if element.name in ["div", "section", "article"]:
        if hasattr(element, "children"):
            for child in element.children:
                if hasattr(child, "name"):
                    process_element(child, depth + 1)


# 处理内容
if hasattr(content_area, "children"):
    for child in content_area.children:
        if hasattr(child, "name"):
            process_element(child)

# 输出结果
print("处理结果（按 DOM 顺序）:")
print("=" * 60)
for i, item in enumerate(paragraphs, 1):
    print(f"{i}. {item}")

# 验证顺序
print("\n" + "=" * 60)
print("验证结果:")
expected_order = [
    "[文本: 这是第一段文字。]",
    "[图片: image1.jpg - 图片1]",
    "[文本: 这是第二段文字。]",
    "[文本: 这是第三段文字。]",
    "[图片: image2.jpg - 图片2]",
    "[标题2: 这是一个标题]",
    "[文本: 这是第四段文字。]",
    "[图片: image3.jpg - 图片3]",
    "[文本: 这是第五段文字。]",
]

if paragraphs == expected_order:
    print("✅ 顺序正确！图文按照原文顺序排列。")
else:
    print("❌ 顺序不正确！")
    print("\n期望顺序:")
    for i, item in enumerate(expected_order, 1):
        print(f"{i}. {item}")
    print("\n实际顺序:")
    for i, item in enumerate(paragraphs, 1):
        print(f"{i}. {item}")

