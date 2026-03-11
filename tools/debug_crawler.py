#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
InfoQ 周刊爬虫调试脚本
用于分析网页结构，定位爬取失败的原因
"""

import time
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "tests" / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)


def init_driver(headless=False):
    """初始化 WebDriver"""
    chrome_options = Options()
    if headless:
        chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument(
        "--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    driver.implicitly_wait(10)
    return driver


def save_page_snapshot(driver, path: Path):
    """保存页面快照"""
    path.write_text(driver.page_source, encoding="utf-8")
    print(f"✓ 页面快照已保存: {path}")


def analyze_page_structure(driver):
    """分析页面结构"""
    print("\n" + "=" * 60)
    print("页面结构分析")
    print("=" * 60)

    soup = BeautifulSoup(driver.page_source, "html.parser")

    print("\n1. 查找 class='weekly-list' 元素:")
    weekly_list = soup.find(class_="weekly-list")
    if weekly_list:
        print("   ✓ 找到 weekly-list 容器")
        print(f"   标签: {weekly_list.name}")
        print(f"   子元素数量: {len(weekly_list.find_all())}")

        links = weekly_list.find_all("a", href=True)
        print(f"   链接数量: {len(links)}")
        for i, link in enumerate(links[:5], 1):
            print(f"   [{i}] {link.get('href', '')[:80]}")
    else:
        print("   ✗ 未找到 weekly-list 容器")

    print("\n2. 查找所有包含 'weekly' 的元素:")
    weekly_elements = soup.find_all(class_=lambda x: x and "weekly" in str(x).lower())
    print(f"   找到 {len(weekly_elements)} 个元素")
    for i, elem in enumerate(weekly_elements[:10], 1):
        classes = elem.get("class", [])
        print(f"   [{i}] {elem.name}.{'.'.join(classes)}")

    print("\n3. 查找所有包含 'weekly' 的链接:")
    all_links = soup.find_all("a", href=True)
    weekly_links = [link for link in all_links if "weekly" in link.get("href", "").lower()]
    print(f"   找到 {len(weekly_links)} 个周刊链接")
    for i, link in enumerate(weekly_links[:10], 1):
        href = link.get("href", "")
        text = link.get_text(strip=True)[:50]
        print(f"   [{i}] {text}")
        print(f"       URL: {href}")

    print("\n4. 查找常见的列表容器:")
    list_containers = [
        ("ul", "ul"),
        ("ol", "ol"),
        ("main", "main"),
        ("article", "article"),
    ]

    for name, tag in list_containers:
        elements = soup.find_all(tag)
        if elements:
            print(f"   {name}: 找到 {len(elements)} 个")
            for elem in elements[:3]:
                classes = elem.get("class", [])
                children = len(elem.find_all())
                print(f"      - {elem.name}.{'.'.join(classes)} (子元素: {children})")

    print("\n5. 页面标题和元信息:")
    title = soup.find("title")
    if title:
        print(f"   标题: {title.get_text()}")

    print("\n6. 检查页面加载状态:")
    try:
        ready_state = driver.execute_script("return document.readyState")
        print(f"   文档状态: {ready_state}")
        loading_indicators = soup.find_all(
            class_=lambda x: x and any(kw in str(x).lower() for kw in ["loading", "spinner", "skeleton"])
        )
        if loading_indicators:
            print(f"   ⚠️  发现 {len(loading_indicators)} 个可能的加载指示器")
    except Exception as e:
        print(f"   检查失败: {e}")


def wait_and_analyze(driver, url, wait_times=(3, 5, 10)):
    """等待不同时间后分析"""
    print(f"\n访问页面: {url}")
    driver.get(url)

    for wait_time in wait_times:
        print(f"\n等待 {wait_time} 秒后分析...")
        time.sleep(wait_time)

        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(1)
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(1)

        print(f"\n--- 等待 {wait_time} 秒后的结果 ---")
        analyze_page_structure(driver)


def main():
    """主函数"""
    url = "https://www.infoq.cn/weekly/landing"

    print("=" * 60)
    print("InfoQ 周刊爬虫调试工具")
    print("=" * 60)

    driver = None
    try:
        print("\n初始化浏览器（非无头模式，方便观察）...")
        driver = init_driver(headless=False)

        wait_and_analyze(driver, url)

        print("\n保存页面快照...")
        save_page_snapshot(driver, DATA_DIR / "debug_page_snapshot.html")

        print("\n保存页面截图...")
        screenshot_path = DATA_DIR / "debug_page_screenshot.png"
        driver.save_screenshot(str(screenshot_path))
        print(f"✓ 截图已保存: {screenshot_path}")

        print("\n" + "=" * 60)
        print("调试完成！")
        print("=" * 60)
        print("\n请查看:")
        print(f"  - {DATA_DIR / 'debug_page_snapshot.html'} (页面HTML)")
        print(f"  - {DATA_DIR / 'debug_page_screenshot.png'} (页面截图)")
        print("\n按 Enter 键关闭浏览器...")
        input()

    finally:
        if driver:
            driver.quit()


if __name__ == "__main__":
    main()

