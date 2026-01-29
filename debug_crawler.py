#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
InfoQ 周刊爬虫调试脚本
用于分析网页结构，定位爬取失败的原因
"""

import os
import time
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import json


def init_driver(headless=False):
    """初始化 WebDriver"""
    chrome_options = Options()
    if headless:
        chrome_options.add_argument('--headless')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--window-size=1920,1080')
    chrome_options.add_argument('--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    driver.implicitly_wait(10)
    return driver


def save_page_snapshot(driver, filename="page_snapshot.html"):
    """保存页面快照"""
    html = driver.page_source
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"✓ 页面快照已保存: {filename}")


def analyze_page_structure(driver):
    """分析页面结构"""
    print("\n" + "="*60)
    print("页面结构分析")
    print("="*60)
    
    soup = BeautifulSoup(driver.page_source, 'html.parser')
    
    # 1. 检查 weekly-list
    print("\n1. 查找 class='weekly-list' 元素:")
    weekly_list = soup.find(class_='weekly-list')
    if weekly_list:
        print(f"   ✓ 找到 weekly-list 容器")
        print(f"   标签: {weekly_list.name}")
        print(f"   子元素数量: {len(weekly_list.find_all())}")
        
        # 查找所有链接
        links = weekly_list.find_all('a', href=True)
        print(f"   链接数量: {len(links)}")
        for i, link in enumerate(links[:5], 1):
            print(f"   [{i}] {link.get('href', '')[:80]}")
    else:
        print("   ✗ 未找到 weekly-list 容器")
    
    # 2. 查找所有包含 'weekly' 的元素
    print("\n2. 查找所有包含 'weekly' 的元素:")
    weekly_elements = soup.find_all(class_=lambda x: x and 'weekly' in str(x).lower())
    print(f"   找到 {len(weekly_elements)} 个元素")
    for i, elem in enumerate(weekly_elements[:10], 1):
        classes = elem.get('class', [])
        print(f"   [{i}] {elem.name}.{'.'.join(classes)}")
    
    # 3. 查找所有链接，筛选包含 weekly 的
    print("\n3. 查找所有包含 'weekly' 的链接:")
    all_links = soup.find_all('a', href=True)
    weekly_links = [link for link in all_links if 'weekly' in link.get('href', '').lower()]
    print(f"   找到 {len(weekly_links)} 个周刊链接")
    for i, link in enumerate(weekly_links[:10], 1):
        href = link.get('href', '')
        text = link.get_text(strip=True)[:50]
        print(f"   [{i}] {text}")
        print(f"       URL: {href}")
    
    # 4. 查找常见的列表容器
    print("\n4. 查找常见的列表容器:")
    list_containers = [
        ('ul', 'ul'),
        ('ol', 'ol'),
        ('div.list', 'div', lambda x: x and 'list' in str(x.get('class', [])).lower()),
        ('div.container', 'div', lambda x: x and 'container' in str(x.get('class', [])).lower()),
        ('div.content', 'div', lambda x: x and 'content' in str(x.get('class', [])).lower()),
        ('main', 'main'),
        ('article', 'article'),
    ]
    
    for name, tag, *filters in list_containers:
        if filters:
            elements = soup.find_all(tag, class_=filters[0])
        else:
            elements = soup.find_all(tag)
        if elements:
            print(f"   {name}: 找到 {len(elements)} 个")
            for elem in elements[:3]:
                classes = elem.get('class', [])
                children = len(elem.find_all())
                print(f"      - {elem.name}.{'.'.join(classes)} (子元素: {children})")
    
    # 5. 查找页面标题
    print("\n5. 页面标题和元信息:")
    title = soup.find('title')
    if title:
        print(f"   标题: {title.get_text()}")
    
    # 6. 检查是否有 JavaScript 错误或动态加载
    print("\n6. 检查页面加载状态:")
    try:
        ready_state = driver.execute_script("return document.readyState")
        print(f"   文档状态: {ready_state}")
        
        # 检查是否有常见的加载指示器
        loading_indicators = soup.find_all(class_=lambda x: x and any(
            kw in str(x).lower() for kw in ['loading', 'spinner', 'skeleton']
        ))
        if loading_indicators:
            print(f"   ⚠️  发现 {len(loading_indicators)} 个可能的加载指示器")
    except Exception as e:
        print(f"   检查失败: {e}")


def try_different_selectors(driver):
    """尝试不同的选择器策略"""
    print("\n" + "="*60)
    print("尝试不同的选择器策略")
    print("="*60)
    
    soup = BeautifulSoup(driver.page_source, 'html.parser')
    
    strategies = [
        {
            'name': '策略1: class="weekly-list" 下的所有链接',
            'selector': lambda s: s.find(class_='weekly-list').find_all('a', href=True) if s.find(class_='weekly-list') else []
        },
        {
            'name': '策略2: 所有包含 weekly 的链接',
            'selector': lambda s: [a for a in s.find_all('a', href=True) if 'weekly' in a.get('href', '').lower()]
        },
        {
            'name': '策略3: 查找包含数字的 weekly 链接',
            'selector': lambda s: [a for a in s.find_all('a', href=True) 
                                   if 'weekly' in a.get('href', '').lower() 
                                   and any(c.isdigit() for c in a.get('href', ''))]
        },
        {
            'name': '策略4: 查找所有 div.item 或 div.card',
            'selector': lambda s: s.find_all(['div'], class_=lambda x: x and any(
                kw in str(x).lower() for kw in ['item', 'card', 'article']
            ))
        },
        {
            'name': '策略5: 查找所有 article 标签',
            'selector': lambda s: s.find_all('article')
        },
    ]
    
    results = {}
    for strategy in strategies:
        try:
            elements = strategy['selector'](soup)
            results[strategy['name']] = len(elements)
            print(f"\n{strategy['name']}:")
            print(f"   找到 {len(elements)} 个元素")
            
            if elements and len(elements) > 0:
                # 显示前3个示例
                for i, elem in enumerate(elements[:3], 1):
                    if elem.name == 'a':
                        href = elem.get('href', '')
                        text = elem.get_text(strip=True)[:50]
                        print(f"   [{i}] {text}")
                        print(f"       {href[:80]}")
                    else:
                        classes = elem.get('class', [])
                        text = elem.get_text(strip=True)[:50]
                        print(f"   [{i}] {elem.name}.{'.'.join(classes)}")
                        print(f"       {text}")
        except Exception as e:
            print(f"\n{strategy['name']}:")
            print(f"   ✗ 执行失败: {e}")
            results[strategy['name']] = 0
    
    return results


def wait_and_analyze(driver, url, wait_times=[3, 5, 10]):
    """等待不同时间后分析"""
    print(f"\n访问页面: {url}")
    driver.get(url)
    
    for wait_time in wait_times:
        print(f"\n等待 {wait_time} 秒后分析...")
        time.sleep(wait_time)
        
        # 滚动页面
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(1)
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(1)
        
        print(f"\n--- 等待 {wait_time} 秒后的结果 ---")
        analyze_page_structure(driver)
        results = try_different_selectors(driver)
        
        # 如果找到内容，可以提前结束
        total_found = sum(results.values())
        if total_found > 0:
            print(f"\n✓ 在等待 {wait_time} 秒后找到 {total_found} 个相关元素")
            break


def main():
    """主函数"""
    url = "https://www.infoq.cn/weekly/landing"
    
    print("="*60)
    print("InfoQ 周刊爬虫调试工具")
    print("="*60)
    
    driver = None
    try:
        # 使用非无头模式，方便观察
        print("\n初始化浏览器（非无头模式，方便观察）...")
        driver = init_driver(headless=False)
        
        # 等待并分析
        wait_and_analyze(driver, url)
        
        # 保存页面快照
        print("\n保存页面快照...")
        save_page_snapshot(driver, "debug_page_snapshot.html")
        
        # 保存页面截图
        print("\n保存页面截图...")
        driver.save_screenshot("debug_page_screenshot.png")
        print("✓ 截图已保存: debug_page_screenshot.png")
        
        print("\n" + "="*60)
        print("调试完成！")
        print("="*60)
        print("\n请查看:")
        print("  - debug_page_snapshot.html (页面HTML)")
        print("  - debug_page_screenshot.png (页面截图)")
        print("\n按 Enter 键关闭浏览器...")
        input()
        
    except Exception as e:
        print(f"\n✗ 发生错误: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        if driver:
            driver.quit()


if __name__ == "__main__":
    main()
