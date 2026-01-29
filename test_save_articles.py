#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试保存文章功能
"""

from infoq_crawler import InfoQWeeklyCrawler
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def main():
    crawler = InfoQWeeklyCrawler('/Users/ice7/Documents/01.curwork/data/obsidian-rep/Infoq')
    
    weekly = {
        'id': '909',
        'title': '909期 / 每周精要',
        'url': 'https://www.infoq.cn/weekly/909',
        'date': '2026-01-17'
    }
    
    # 获取周刊内容
    weekly_data = crawler._get_weekly_content(weekly)
    
    # 只取前3篇文章进行测试
    weekly_data['articles'] = weekly_data['articles'][:3]
    
    print(f"\n准备保存 {len(weekly_data['articles'])} 篇文章...")
    
    # 保存周刊
    weekly_dir = crawler._save_weekly(weekly_data)
    
    if weekly_dir:
        print(f"\n✓ 保存成功！")
        print(f"目录: {weekly_dir}")
        
        # 列出保存的文件
        import os
        md_files = [f for f in os.listdir(weekly_dir) if f.endswith('.md')]
        print(f"\n保存的文件:")
        for f in sorted(md_files):
            print(f"  - {f}")
    else:
        print("\n✗ 保存失败")

if __name__ == "__main__":
    main()
