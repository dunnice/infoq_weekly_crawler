#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
快速测试爬虫脚本
用于快速验证爬虫是否能正常工作
"""

import sys
from pathlib import Path

# 添加当前目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from infoq_crawler import InfoQWeeklyCrawler
import logging

# 设置详细日志
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('test_crawler.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

def main():
    """测试主函数"""
    print("="*60)
    print("InfoQ 周刊爬虫测试")
    print("="*60)
    
    # 配置
    OUTPUT_DIR = "/Users/ice7/Documents/01.curwork/data/obsidian-rep/Infoq"
    
    # 创建爬虫实例
    crawler = InfoQWeeklyCrawler(output_dir=OUTPUT_DIR)
    
    # 测试获取周刊列表
    print("\n1. 测试获取周刊列表...")
    weekly_list = crawler._get_weekly_list()
    
    print(f"\n结果: 找到 {len(weekly_list)} 期周刊")
    
    if weekly_list:
        print("\n前5期周刊:")
        for i, weekly in enumerate(weekly_list[:5], 1):
            print(f"  [{i}] {weekly['title']}")
            print(f"      ID: {weekly['id']}")
            print(f"      URL: {weekly['url']}")
            print(f"      日期: {weekly.get('date', '未知')}")
            print()
    else:
        print("\n⚠️  未找到任何周刊！")
        print("\n请检查:")
        print("  1. 网络连接是否正常")
        print("  2. 网站是否可以正常访问")
        print("  3. 查看 debug_page_snapshot.html 了解页面结构")
        print("  4. 运行 python debug_crawler.py 进行详细调试")
    
    # 清理
    crawler._close_driver()
    
    print("="*60)
    print("测试完成")
    print("="*60)

if __name__ == "__main__":
    main()
