#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
InfoQ 周刊爬虫脚本
每周自动抓取 InfoQ 周刊内容并保存为 Obsidian Markdown 格式
"""

import os
import re
import time
import json
import hashlib
import requests
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse
from typing import List, Dict, Optional, Tuple
import logging

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
from webdriver_manager.chrome import ChromeDriverManager

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('infoq_crawler.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class InfoQWeeklyCrawler:
    """InfoQ 周刊爬虫类"""
    
    # 基础配置
    BASE_URL = "https://www.infoq.cn"
    WEEKLY_LANDING_URL = "https://www.infoq.cn/weekly/landing"
    
    def __init__(self, output_dir: str, image_dir: str = "attachments"):
        """
        初始化爬虫
        
        Args:
            output_dir: Obsidian 笔记输出目录
            image_dir: 图片存储子目录名
        """
        self.output_dir = Path(output_dir)
        self.image_dir = image_dir
        self.driver = None
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        })
        
        # 记录已处理的周刊，避免重复
        self.processed_file = self.output_dir / ".processed_weekly.json"
        self.processed_weekly = self._load_processed()
        
        # 确保目录存在
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # 当前周刊目录（在爬取时设置）
        self.current_weekly_dir = None
        
    def _load_processed(self) -> set:
        """加载已处理的周刊记录"""
        if self.processed_file.exists():
            try:
                with open(self.processed_file, 'r', encoding='utf-8') as f:
                    return set(json.load(f))
            except Exception as e:
                logger.warning(f"加载已处理记录失败: {e}")
        return set()
    
    def _save_processed(self):
        """保存已处理的周刊记录"""
        try:
            with open(self.processed_file, 'w', encoding='utf-8') as f:
                json.dump(list(self.processed_weekly), f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存已处理记录失败: {e}")
    
    def _init_driver(self):
        """初始化 Selenium WebDriver"""
        if self.driver is not None:
            return
            
        chrome_options = Options()
        chrome_options.add_argument('--headless')  # 无头模式
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        
        try:
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=chrome_options)
            self.driver.implicitly_wait(10)
            logger.info("WebDriver 初始化成功")
        except Exception as e:
            logger.error(f"WebDriver 初始化失败: {e}")
            raise
    
    def _close_driver(self):
        """关闭 WebDriver"""
        if self.driver:
            self.driver.quit()
            self.driver = None
            
    def _download_image(self, img_url: str, weekly_id: str) -> Optional[str]:
        """
        下载图片到本地
        
        Args:
            img_url: 图片 URL
            weekly_id: 周刊 ID，用于组织图片目录
            
        Returns:
            本地图片相对路径（相对于周刊目录），失败返回 None
        """
        try:
            if not img_url:
                return None
            
            # 跳过 base64 图片
            if img_url.startswith('data:'):
                return None
                
            # 处理相对路径
            if img_url.startswith('//'):
                img_url = 'https:' + img_url
            elif img_url.startswith('/'):
                img_url = urljoin(self.BASE_URL, img_url)
            
            # 生成文件名
            url_hash = hashlib.md5(img_url.encode()).hexdigest()[:8]
            ext = self._get_image_extension(img_url)
            filename = f"{url_hash}{ext}"
            
            # 确保周刊目录和附件目录存在
            if not self.current_weekly_dir:
                return None
            
            attachments_dir = self.current_weekly_dir / self.image_dir
            attachments_dir.mkdir(parents=True, exist_ok=True)
            
            # 本地路径
            local_path = attachments_dir / filename
            relative_path = f"{self.image_dir}/{filename}"
            
            # 如果已存在则跳过
            if local_path.exists():
                logger.debug(f"图片已存在: {filename}")
                return relative_path
            
            # 下载图片
            response = self.session.get(img_url, timeout=30)
            response.raise_for_status()
            
            with open(local_path, 'wb') as f:
                f.write(response.content)
            
            logger.debug(f"下载图片成功: {filename}")
            return relative_path
            
        except Exception as e:
            logger.warning(f"下载图片失败 {img_url}: {e}")
            return None
    
    def _get_image_extension(self, url: str) -> str:
        """获取图片扩展名"""
        parsed = urlparse(url)
        path = parsed.path.lower()
        
        if '.png' in path:
            return '.png'
        elif '.gif' in path:
            return '.gif'
        elif '.webp' in path:
            return '.webp'
        elif '.svg' in path:
            return '.svg'
        else:
            return '.jpg'
    
    def _get_weekly_list(self) -> List[Dict]:
        """
        获取周刊列表
        
        Returns:
            周刊列表，每项包含 title, url, date, id 等信息
        """
        self._init_driver()
        weekly_list = []
        
        try:
            logger.info(f"正在访问周刊列表页: {self.WEEKLY_LANDING_URL}")
            self.driver.get(self.WEEKLY_LANDING_URL)
            
            # 等待页面基本加载
            logger.info("等待页面加载...")
            time.sleep(5)  # 先等待5秒，确保基础内容加载
            
            # 尝试等待 weekly-list，但不强制要求
            try:
                WebDriverWait(self.driver, 15).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )
                logger.info("页面主体已加载")
            except TimeoutException:
                logger.warning("页面加载超时，继续尝试解析...")
            
            # 滚动页面以加载更多内容
            logger.info("滚动页面以触发懒加载...")
            self._scroll_to_load(scroll_times=5, wait_time=2)
            
            # 再次等待
            time.sleep(3)
            
            # 获取页面源码
            soup = BeautifulSoup(self.driver.page_source, 'html.parser')
            
            # 保存页面快照用于调试
            debug_file = self.output_dir / "debug_page_snapshot.html"
            with open(debug_file, 'w', encoding='utf-8') as f:
                f.write(self.driver.page_source)
            logger.debug(f"页面快照已保存: {debug_file}")
            
            # 策略1: 尝试查找 weekly-list 容器（InfoQ 的实际结构）
            weekly_container = soup.find(class_='weekly-list')
            if weekly_container:
                logger.info("找到 weekly-list 容器")
                # InfoQ 的 weekly-list 是 <ul>，里面是 <li>，每个 <li> 包含期号和日期，但没有链接
                # 需要从期号构建 URL
                items = weekly_container.find_all('li')
                if items:
                    logger.info(f"从 weekly-list 容器中找到 {len(items)} 个条目")
                    # 直接解析这些 li 元素
                    for li in items:
                        try:
                            # 提取期号
                            no_elem = li.find(class_='no')
                            if not no_elem:
                                # 尝试从 weekly-title 中提取
                                title_elem = li.find(class_='weekly-title')
                                if title_elem:
                                    no_text = title_elem.get_text()
                                    # 提取数字
                                    import re
                                    match = re.search(r'(\d+)', no_text)
                                    if match:
                                        weekly_no = match.group(1)
                                    else:
                                        continue
                                else:
                                    continue
                            else:
                                weekly_no = no_elem.get_text(strip=True)
                            
                            # 提取日期
                            date_elem = li.find(class_='date')
                            date_str = date_elem.get_text(strip=True) if date_elem else datetime.now().strftime('%Y-%m-%d')
                            
                            # 构建 URL（InfoQ 周刊 URL 格式通常是 /weekly/期号）
                            weekly_url = f"{self.BASE_URL}/weekly/{weekly_no}"
                            
                            # 提取标题
                            title_elem = li.find(class_='weekly-title')
                            title = title_elem.get_text(strip=True) if title_elem else f"InfoQ周刊第{weekly_no}期"
                            
                            weekly_info = {
                                'id': weekly_no,
                                'title': title,
                                'url': weekly_url,
                                'date': date_str
                            }
                            
                            # 避免重复
                            if weekly_no not in [w['id'] for w in weekly_list]:
                                weekly_list.append(weekly_info)
                                logger.info(f"发现周刊: {weekly_info['title']} (ID: {weekly_no})")
                        except Exception as e:
                            logger.debug(f"解析周刊条目失败: {e}")
                            continue
                    
                    # 如果从 weekly-list 成功解析，直接返回
                    if weekly_list:
                        logger.info(f"从 weekly-list 成功解析 {len(weekly_list)} 期周刊")
                        return weekly_list
                items = []
            else:
                logger.warning("未找到 weekly-list 容器，尝试其他策略...")
                items = []
            
            # 策略2: 如果策略1失败，直接查找所有包含 weekly 的链接
            if not items:
                logger.info("尝试策略2: 查找所有包含 'weekly' 的链接")
                all_links = soup.find_all('a', href=True)
                weekly_links = [
                    link for link in all_links 
                    if 'weekly' in link.get('href', '').lower()
                ]
                logger.info(f"找到 {len(weekly_links)} 个周刊相关链接")
                items = weekly_links
            
            # 策略3: 如果还是没找到，尝试查找包含数字的 weekly 链接
            if not items:
                logger.info("尝试策略3: 查找包含数字的 weekly 链接")
                all_links = soup.find_all('a', href=True)
                weekly_links = [
                    link for link in all_links 
                    if 'weekly' in link.get('href', '').lower()
                    and any(c.isdigit() for c in link.get('href', ''))
                ]
                logger.info(f"找到 {len(weekly_links)} 个可能的周刊链接")
                items = weekly_links
            
            # 策略4: 查找所有可能的列表容器
            if not items:
                logger.info("尝试策略4: 查找所有列表容器")
                containers = soup.find_all(['ul', 'ol', 'div'], 
                    class_=lambda x: x and any(
                        kw in str(x).lower() for kw in ['list', 'container', 'content', 'main']
                    ))
                logger.info(f"找到 {len(containers)} 个可能的容器")
                for container in containers:
                    container_items = self._extract_items_from_container(container)
                    if container_items:
                        items.extend(container_items)
                        logger.info(f"从容器中找到 {len(container_items)} 个条目")
            
            # 解析找到的条目
            logger.info(f"开始解析 {len(items)} 个条目...")
            for item in items:
                try:
                    weekly_info = self._parse_weekly_item(item)
                    if weekly_info:
                        # 避免重复
                        if weekly_info['id'] not in [w['id'] for w in weekly_list]:
                            weekly_list.append(weekly_info)
                            logger.info(f"发现周刊: {weekly_info['title']} (ID: {weekly_info['id']})")
                except Exception as e:
                    logger.debug(f"解析周刊条目失败: {e}")
                    continue
            
            logger.info(f"共发现 {len(weekly_list)} 期周刊")
            
            # 如果还是没找到，输出调试信息
            if not weekly_list:
                logger.error("="*60)
                logger.error("未找到任何周刊！")
                logger.error("="*60)
                logger.error("调试信息:")
                logger.error(f"  页面标题: {soup.find('title').get_text() if soup.find('title') else '未知'}")
                logger.error(f"  所有链接数量: {len(soup.find_all('a', href=True))}")
                logger.error(f"  包含 'weekly' 的链接: {len([a for a in soup.find_all('a', href=True) if 'weekly' in a.get('href', '').lower()])}")
                logger.error(f"  页面快照已保存: {debug_file}")
                logger.error("请检查页面快照文件以了解实际页面结构")
                logger.error("="*60)
            
        except TimeoutException:
            logger.error("等待页面加载超时")
            if self.driver:
                debug_file = self.output_dir / "debug_page_snapshot_timeout.html"
                with open(debug_file, 'w', encoding='utf-8') as f:
                    f.write(self.driver.page_source)
                logger.error(f"超时时的页面快照已保存: {debug_file}")
        except Exception as e:
            logger.error(f"获取周刊列表失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            
        return weekly_list
    
    def _extract_items_from_container(self, container) -> List:
        """从容器中提取条目"""
        items = []
        
        # 尝试多种选择器
        selectors = [
            # 查找带特定 class 的元素
            lambda c: c.find_all(['a', 'div', 'li'], class_=lambda x: x and any(
                kw in str(x).lower() for kw in ['item', 'card', 'weekly', 'article', 'news']
            )),
            # 查找所有链接
            lambda c: c.find_all('a', href=True),
            # 查找所有 div
            lambda c: c.find_all('div'),
        ]
        
        for selector in selectors:
            try:
                found = selector(container)
                if found:
                    items = found
                    break
            except:
                continue
        
        return items
    
    def _parse_weekly_item(self, item) -> Optional[Dict]:
        """解析单个周刊条目"""
        # 提取链接
        if item.name == 'a':
            link = item
        else:
            link = item.find('a', href=True)
        
        if not link:
            return None
        
        href = link.get('href', '')
        if not href:
            return None
        
        # 检查是否包含 weekly（更宽松的检查）
        href_lower = href.lower()
        if 'weekly' not in href_lower and '/week' not in href_lower:
            # 如果不是明确的周刊链接，跳过
            return None
        
        # 构建完整 URL
        if href.startswith('/'):
            full_url = urljoin(self.BASE_URL, href)
        elif not href.startswith('http'):
            full_url = urljoin(self.BASE_URL, '/' + href)
        else:
            full_url = href
        
        # 提取周刊 ID（更宽松的提取）
        weekly_id = self._extract_weekly_id(href)
        if not weekly_id:
            # 如果无法提取ID，使用URL的hash作为临时ID
            weekly_id = hashlib.md5(href.encode()).hexdigest()[:8]
            logger.debug(f"无法从URL提取ID，使用hash: {weekly_id}")
        
        # 提取标题
        title = self._extract_title(item)
        if not title:
            title = link.get_text(strip=True)
        if not title:
            title = f"InfoQ周刊-{weekly_id}"
        
        # 提取日期
        date_str = self._extract_date(item)
        
        return {
            'id': weekly_id,
            'title': title,
            'url': full_url,
            'date': date_str
        }
    
    def _scroll_to_load(self, scroll_times: int = 3, wait_time: float = 1.5):
        """滚动页面以触发懒加载"""
        for i in range(scroll_times):
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(wait_time)
            
    def _extract_weekly_id(self, url: str) -> Optional[str]:
        """从 URL 提取周刊 ID"""
        # 尝试多种模式
        patterns = [
            r'/weekly/(\d+)',           # /weekly/123
            r'/weekly-(\d+)',           # /weekly-123
            r'weekly[_-]?(\d+)',        # weekly123, weekly_123, weekly-123
            r'/week/(\d+)',             # /week/123
            r'week[_-]?(\d+)',         # week123
            r'/(\d+)/?$',               # /123/
            r'id[=:](\d+)',             # id=123 或 id:123
            r'(\d{4,})',                # 4位以上的数字（可能是ID）
        ]
        for pattern in patterns:
            match = re.search(pattern, url, re.IGNORECASE)
            if match:
                weekly_id = match.group(1)
                # 验证ID合理性（应该是数字）
                if weekly_id.isdigit():
                    return weekly_id
        return None
    
    def _extract_title(self, element) -> str:
        """提取标题"""
        # 尝试多种选择器
        for selector in ['.title', '.name', 'h2', 'h3', 'h4', '.heading']:
            title_elem = element.find(class_=selector.lstrip('.')) if selector.startswith('.') else element.find(selector)
            if title_elem and title_elem.get_text(strip=True):
                return title_elem.get_text(strip=True)
        
        # 直接获取文本
        text = element.get_text(strip=True)
        if text and len(text) < 100:
            return text[:50]
        
        return ""
    
    def _extract_date(self, element) -> str:
        """提取日期"""
        # 查找日期相关元素
        for selector in ['.date', '.time', '.publish-time', 'time']:
            date_elem = element.find(class_=selector.lstrip('.')) if selector.startswith('.') else element.find(selector)
            if date_elem:
                date_text = date_elem.get_text(strip=True)
                if date_text:
                    return date_text
        
        # 从文本中查找日期格式
        text = element.get_text()
        date_patterns = [
            r'(\d{4}[-/]\d{1,2}[-/]\d{1,2})',
            r'(\d{1,2}月\d{1,2}日)',
        ]
        for pattern in date_patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1)
        
        return datetime.now().strftime('%Y-%m-%d')
    
    def _get_weekly_content(self, weekly_info: Dict) -> Dict:
        """
        获取单期周刊的详细内容
        
        Args:
            weekly_info: 周刊基本信息
            
        Returns:
            包含所有文章内容的字典
        """
        self._init_driver()
        articles = []
        
        try:
            logger.info(f"正在获取周刊内容: {weekly_info['title']}")
            self.driver.get(weekly_info['url'])
            
            # 等待内容加载
            time.sleep(5)
            WebDriverWait(self.driver, 20).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            # 滚动加载完整内容
            self._scroll_to_load(scroll_times=5, wait_time=2)
            
            soup = BeautifulSoup(self.driver.page_source, 'html.parser')
            
            # 保存页面快照用于调试
            if self.current_weekly_dir:
                debug_file = self.current_weekly_dir / "debug_weekly_page.html"
                with open(debug_file, 'w', encoding='utf-8') as f:
                    f.write(self.driver.page_source)
                logger.debug(f"周刊页面快照已保存: {debug_file}")
            
            # 先提取文章链接（在移除不需要的元素之前）
            article_links = []
            
            # 方法1: 查找带有 com-article-title class 的链接（InfoQ 的标准文章标题链接）
            article_title_links = soup.find_all('a', class_='com-article-title')
            for link in article_title_links:
                href = link.get('href', '')
                if href:
                    full_url = urljoin(self.BASE_URL, href) if not href.startswith('http') else href
                    title = link.get_text(strip=True)
                    if title and len(title) > 5:
                        article_links.append({
                            'url': full_url,
                            'title': title[:200]
                        })
            
            # 方法2: 查找 article-item 容器中的链接
            article_items = soup.find_all(class_='article-item')
            for item in article_items:
                link = item.find('a', href=True)
                if link:
                    href = link.get('href', '')
                    if '/article/' in href or 'infoq.cn/article' in href:
                        full_url = urljoin(self.BASE_URL, href) if not href.startswith('http') else href
                        # 尝试从多个地方提取标题
                        title = link.get_text(strip=True)
                        if not title or len(title) < 5:
                            title_elem = item.find(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', '.title', '.com-article-title'])
                            if title_elem:
                                title = title_elem.get_text(strip=True)
                        
                        if title and len(title) > 5:
                            # 检查是否已存在
                            if not any(a['url'] == full_url for a in article_links):
                                article_links.append({
                                    'url': full_url,
                                    'title': title[:200]
                                })
            
            # 方法3: 查找所有包含 /article/ 的链接
            if not article_links:
                all_links = soup.find_all('a', href=True)
                for link in all_links:
                    href = link.get('href', '')
                    if '/article/' in href or 'infoq.cn/article' in href:
                        full_url = urljoin(self.BASE_URL, href) if not href.startswith('http') else href
                        title = link.get_text(strip=True)
                        # 过滤太短的标题和明显不是文章的链接
                        if title and len(title) > 5 and not any(kw in title.lower() for kw in ['首页', '登录', '注册', '订阅', '关注', '更多']):
                            article_links.append({
                                'url': full_url,
                                'title': title[:200]
                            })
            
            # 去重
            seen_urls = set()
            unique_articles = []
            for article in article_links:
                if article['url'] not in seen_urls:
                    seen_urls.add(article['url'])
                    unique_articles.append(article)
            
            logger.info(f"找到 {len(unique_articles)} 篇文章链接")
            
            # 移除不需要的元素（在提取文章链接之后）
            self._remove_unwanted_elements(soup)
            
            # 获取每篇文章的详细内容（优化：减少等待时间）
            for i, article_link in enumerate(unique_articles, 1):
                try:
                    logger.info(f"正在获取文章 {i}/{len(unique_articles)}: {article_link['title'][:50]}")
                    article_detail = self._get_article_detail(article_link['url'], weekly_info['id'])
                    if article_detail:
                        # 优先使用列表页的标题，如果详情页有标题且列表页标题太短，则使用详情页标题
                        list_title = article_link['title'].strip()
                        detail_title = article_detail.get('title', '').strip()
                        
                        if list_title and len(list_title) > 5:
                            article_detail['title'] = list_title
                        elif detail_title and len(detail_title) > 5:
                            article_detail['title'] = detail_title
                        elif list_title:
                            article_detail['title'] = list_title
                        elif detail_title:
                            article_detail['title'] = detail_title
                        else:
                            article_detail['title'] = f"文章{i}"
                        
                        articles.append(article_detail)
                    else:
                        # 即使获取详情失败，也保存基本信息
                        articles.append({
                            'title': article_link['title'] or f"文章{i}",
                            'url': article_link['url'],
                            'content': '',
                            'images': [],
                            'author': '',
                            'publish_time': ''
                        })
                    time.sleep(0.5)  # 减少等待时间，提高效率
                except Exception as e:
                    logger.warning(f"获取文章失败 {article_link['url']}: {e}")
                    # 即使失败也保存基本信息
                    articles.append({
                        'title': article_link.get('title', f"文章{i}"),
                        'url': article_link['url'],
                        'content': '',
                        'images': [],
                        'author': '',
                        'publish_time': ''
                    })
                    continue
            
            logger.info(f"共解析 {len(articles)} 篇文章")
            
        except Exception as e:
            logger.error(f"获取周刊内容失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
        
        return {
            'info': weekly_info,
            'articles': articles
        }
    
    def _remove_unwanted_elements(self, soup):
        """移除不需要的元素（导航、广告、评论等）"""
        # 移除导航栏
        for nav in soup.find_all(['nav', 'header', 'footer']):
            nav.decompose()
        
        # 移除广告相关
        unwanted_classes = ['ad', 'advertisement', 'ads', 'sidebar', 'comment', 'comments', 
                           'footer', 'header', 'nav', 'navigation', 'menu', 'social', 'share']
        for class_name in unwanted_classes:
            for elem in soup.find_all(class_=lambda x: x and class_name in str(x).lower()):
                elem.decompose()
        
        # 移除脚本和样式
        for script in soup.find_all(['script', 'style', 'noscript']):
            script.decompose()
        
        # 移除常见的无关元素
        unwanted_tags = ['iframe', 'embed', 'object', 'svg']
        for tag in unwanted_tags:
            for elem in soup.find_all(tag):
                elem.decompose()
    
    def _parse_article(self, element, weekly_id: str) -> Optional[Dict]:
        """解析单篇文章"""
        try:
            # 提取标题
            title = ""
            for selector in ['h1', 'h2', 'h3', '.title', '.name']:
                if selector.startswith('.'):
                    title_elem = element.find(class_=selector.lstrip('.'))
                else:
                    title_elem = element.find(selector)
                if title_elem:
                    title = title_elem.get_text(strip=True)
                    break
            
            if not title:
                return None
            
            # 提取链接
            link = element.find('a', href=True)
            url = ""
            if link:
                href = link.get('href', '')
                if href:
                    url = urljoin(self.BASE_URL, href) if not href.startswith('http') else href
            
            # 提取摘要
            summary = ""
            for selector in ['.summary', '.desc', '.description', '.excerpt', 'p']:
                if selector.startswith('.'):
                    summary_elem = element.find(class_=selector.lstrip('.'))
                else:
                    summary_elem = element.find(selector)
                if summary_elem:
                    summary = summary_elem.get_text(strip=True)
                    break
            
            # 提取图片
            images = []
            for img in element.find_all('img'):
                img_src = img.get('src') or img.get('data-src') or img.get('data-original')
                if img_src:
                    local_path = self._download_image(img_src, weekly_id)
                    if local_path:
                        images.append({
                            'original': img_src,
                            'local': local_path,
                            'alt': img.get('alt', '')
                        })
            
            # 提取作者
            author = ""
            for selector in ['.author', '.writer', '.by']:
                author_elem = element.find(class_=selector.lstrip('.')) if selector.startswith('.') else None
                if author_elem:
                    author = author_elem.get_text(strip=True)
                    break
            
            # 提取标签/分类
            tags = []
            for tag_elem in element.find_all(class_=lambda x: x and 'tag' in str(x).lower()):
                tag_text = tag_elem.get_text(strip=True)
                if tag_text and len(tag_text) < 20:
                    tags.append(tag_text)
            
            return {
                'title': title,
                'url': url,
                'summary': summary,
                'author': author,
                'tags': tags,
                'images': images
            }
            
        except Exception as e:
            logger.debug(f"解析文章失败: {e}")
            return None
    
    def _parse_page_as_article(self, soup, weekly_info: Dict) -> Optional[Dict]:
        """将整个页面解析为一篇文章"""
        try:
            # 查找主要内容区域
            content_area = soup.find(class_='content') or soup.find('article') or soup.find('main')
            if not content_area:
                content_area = soup.body
            
            # 提取所有文本内容
            content_text = []
            for p in content_area.find_all(['p', 'div', 'section']):
                text = p.get_text(strip=True)
                if text and len(text) > 20:
                    content_text.append(text)
            
            # 提取所有图片
            images = []
            for img in content_area.find_all('img'):
                img_src = img.get('src') or img.get('data-src')
                if img_src:
                    local_path = self._download_image(img_src, weekly_info['id'])
                    if local_path:
                        images.append({
                            'original': img_src,
                            'local': local_path,
                            'alt': img.get('alt', '')
                        })
            
            return {
                'title': weekly_info['title'],
                'url': weekly_info['url'],
                'summary': '\n\n'.join(content_text[:10]),  # 取前10段
                'author': '',
                'tags': [],
                'images': images
            }
            
        except Exception as e:
            logger.error(f"解析页面内容失败: {e}")
            return None
    
    def _get_article_detail(self, article_url: str, weekly_id: str) -> Optional[Dict]:
        """
        获取文章详情页内容（只提取正文，去掉导航、广告、评论）
        
        Args:
            article_url: 文章详情页 URL
            weekly_id: 周刊 ID
            
        Returns:
            文章详细内容
        """
        if not article_url:
            return None
            
        try:
            self.driver.get(article_url)
            time.sleep(2)  # 减少等待时间
            
            # 等待内容加载
            try:
                WebDriverWait(self.driver, 10).until(  # 减少超时时间
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )
            except TimeoutException:
                logger.warning(f"页面加载超时: {article_url}")
                return None
            
            soup = BeautifulSoup(self.driver.page_source, 'html.parser')
            
            # 移除不需要的元素
            self._remove_unwanted_elements(soup)
            
            # 提取标题
            title = ""
            title_selectors = ['h1', '.title', '.article-title', 'article h1']
            for selector in title_selectors:
                if selector.startswith('.'):
                    title_elem = soup.find(class_=selector.lstrip('.'))
                elif ' ' in selector:
                    parts = selector.split(' ')
                    title_elem = soup.find(parts[0], class_=parts[1].lstrip('.')) if len(parts) > 1 else soup.find(parts[0])
                else:
                    title_elem = soup.find(selector)
                if title_elem:
                    title = title_elem.get_text(strip=True)
                    break
            
            # 查找正文内容区域 - 尝试多种选择器
            content_area = None
            content_selectors = [
                'article',
                '.article-content',
                '.content',
                '.article-body',
                '.post-content',
                'main',
                '.main-content'
            ]
            
            for selector in content_selectors:
                if selector.startswith('.'):
                    content_area = soup.find(class_=selector.lstrip('.'))
                else:
                    content_area = soup.find(selector)
                if content_area:
                    # 进一步清理：移除内容区域内的广告、评论等
                    for unwanted in content_area.find_all(class_=lambda x: x and any(
                        kw in str(x).lower() for kw in ['ad', 'comment', 'share', 'sidebar', 'related']
                    )):
                        unwanted.decompose()
                    break
            
            if not content_area:
                logger.warning(f"未找到内容区域: {article_url}")
                return None
            
            # 提取段落和结构化内容，同时处理图片嵌入
            paragraphs = []
            images = []
            processed_images = set()  # 记录已处理的图片URL，避免重复
            
            # 方法：按DOM顺序遍历所有元素，文本和图片交替处理
            # 先找到所有需要处理的元素（文本元素和图片）
            all_elements = []
            
            # 收集所有文本元素
            for elem in content_area.find_all(['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'pre', 'code', 'ul', 'ol', 'li', 'blockquote']):
                all_elements.append(('text', elem))
            
            # 收集所有图片元素
            for img in content_area.find_all('img'):
                all_elements.append(('img', img))
            
            # 按在DOM中的位置排序（使用元素的sourceline或位置）
            try:
                all_elements.sort(key=lambda x: x[1].sourceline if hasattr(x[1], 'sourceline') else 0)
            except:
                pass  # 如果无法排序，保持原顺序
            
            # 处理每个元素
            for elem_type, elem in all_elements:
                if elem_type == 'img':
                    img_src = elem.get('src') or elem.get('data-src') or elem.get('data-original')
                    if img_src and not img_src.startswith('data:') and img_src not in processed_images:
                        local_path = self._download_image(img_src, weekly_id)
                        if local_path:
                            alt = elem.get('alt', '') or elem.get('title', '') or '图片'
                            images.append({
                                'original': img_src,
                                'local': local_path,
                                'alt': alt
                            })
                            processed_images.add(img_src)
                            paragraphs.append(f"\n![[{local_path}|{alt}]]\n")
                
                elif elem_type == 'text':
                    # 检查元素内是否有图片（先处理图片）
                    elem_imgs = elem.find_all('img')
                    for img in elem_imgs:
                        img_src = img.get('src') or img.get('data-src') or img.get('data-original')
                        if img_src and not img_src.startswith('data:') and img_src not in processed_images:
                            local_path = self._download_image(img_src, weekly_id)
                            if local_path:
                                alt = img.get('alt', '') or img.get('title', '') or '图片'
                                images.append({
                                    'original': img_src,
                                    'local': local_path,
                                    'alt': alt
                                })
                                processed_images.add(img_src)
                                paragraphs.append(f"\n![[{local_path}|{alt}]]\n")
                    
                    # 提取文本（移除图片）
                    elem_copy = BeautifulSoup(str(elem), 'html.parser')
                    for img in elem_copy.find_all('img'):
                        img.decompose()
                    text = elem_copy.get_text(strip=True)
                    
                    if text and len(text) > 3:
                        # 跳过明显是导航或无关的内容
                        if any(kw in text.lower() for kw in ['首页', '登录', '注册', '订阅', '关注', '分享', '评论']):
                            if len(text) < 20:
                                continue
                        
                        if elem.name == 'p':
                            paragraphs.append(text)
                        elif elem.name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
                            level = int(elem.name[1])
                            paragraphs.append(f"\n{'#' * level} {text}\n")
                        elif elem.name in ['pre', 'code']:
                            code = elem.get_text()
                            if code and len(code) > 10:
                                paragraphs.append(f"\n```\n{code}\n```\n")
                        elif elem.name == 'blockquote':
                            paragraphs.append(f"> {text}")
                        elif elem.name == 'li':
                            parent = elem.find_parent(['ul', 'ol'])
                            if parent and parent.name == 'ul':
                                paragraphs.append(f"- {text}")
                            elif parent and parent.name == 'ol':
                                paragraphs.append(f"1. {text}")
            
            # 提取作者
            author = ""
            author_selectors = ['.author', '.writer', '.by', '.article-author']
            for selector in author_selectors:
                author_elem = soup.find(class_=selector.lstrip('.'))
                if author_elem:
                    author = author_elem.get_text(strip=True)
                    break
            
            # 提取发布时间
            publish_time = ""
            time_selectors = ['time', '.publish-time', '.date', '.article-date']
            for selector in time_selectors:
                if selector.startswith('.'):
                    time_elem = soup.find(class_=selector.lstrip('.'))
                else:
                    time_elem = soup.find(selector)
                if time_elem:
                    publish_time = time_elem.get_text(strip=True)
                    break
            
            return {
                'title': title,
                'content': '\n\n'.join(paragraphs),
                'images': images,
                'author': author,
                'publish_time': publish_time,
                'url': article_url
            }
            
        except Exception as e:
            logger.warning(f"获取文章详情失败 {article_url}: {e}")
            return None
    
    def _convert_to_markdown(self, weekly_data: Dict) -> str:
        """
        将周刊数据转换为 Markdown 格式
        
        Args:
            weekly_data: 周刊数据
            
        Returns:
            Markdown 格式字符串
        """
        info = weekly_data['info']
        articles = weekly_data['articles']
        
        md_lines = []
        
        # 添加 YAML Front Matter
        md_lines.append("---")
        md_lines.append(f"title: \"{info['title']}\"")
        md_lines.append(f"source: InfoQ周刊")
        md_lines.append(f"url: \"{info['url']}\"")
        md_lines.append(f"date: {info.get('date', datetime.now().strftime('%Y-%m-%d'))}")
        md_lines.append(f"created: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        md_lines.append("tags:")
        md_lines.append("  - InfoQ")
        md_lines.append("  - 技术周刊")
        md_lines.append("---")
        md_lines.append("")
        
        # 主标题
        md_lines.append(f"# {info['title']}")
        md_lines.append("")
        md_lines.append(f"> 来源: [InfoQ 周刊]({info['url']})")
        md_lines.append(f"> 日期: {info.get('date', '未知')}")
        md_lines.append("")
        md_lines.append("---")
        md_lines.append("")
        
        # 目录
        if articles:
            md_lines.append("## 目录")
            md_lines.append("")
            for i, article in enumerate(articles, 1):
                title = article.get('title', '未知标题')
                anchor = self._generate_anchor(title)
                md_lines.append(f"{i}. [{title}](#{anchor})")
            md_lines.append("")
            md_lines.append("---")
            md_lines.append("")
        
        # 文章内容
        for i, article in enumerate(articles, 1):
            title = article.get('title', '未知标题')
            
            md_lines.append(f"## {i}. {title}")
            md_lines.append("")
            
            # 元信息
            if article.get('author'):
                md_lines.append(f"**作者**: {article['author']}")
            if article.get('url'):
                md_lines.append(f"**链接**: [{article['url']}]({article['url']})")
            if article.get('tags'):
                md_lines.append(f"**标签**: {', '.join(article['tags'])}")
            md_lines.append("")
            
            # 摘要
            if article.get('summary'):
                md_lines.append(article['summary'])
                md_lines.append("")
            
            # 正文内容
            if article.get('content'):
                md_lines.append(article['content'])
                md_lines.append("")
            
            # 图片
            if article.get('images'):
                md_lines.append("### 附图")
                md_lines.append("")
                for img in article['images']:
                    alt = img.get('alt', '图片')
                    local_path = img.get('local', '')
                    if local_path:
                        md_lines.append(f"![[{local_path}|{alt}]]")
                    else:
                        md_lines.append(f"![{alt}]({img.get('original', '')})")
                md_lines.append("")
            
            md_lines.append("---")
            md_lines.append("")
        
        return '\n'.join(md_lines)
    
    def _generate_anchor(self, title: str) -> str:
        """生成 Markdown 锚点"""
        # 移除特殊字符，保留中文和字母数字
        anchor = re.sub(r'[^\w\u4e00-\u9fff-]', '-', title.lower())
        anchor = re.sub(r'-+', '-', anchor)
        return anchor.strip('-')
    
    def _save_weekly(self, weekly_data: Dict) -> Optional[Path]:
        """
        保存周刊内容（新的组织结构：每周一个子目录）
        
        Args:
            weekly_data: 周刊数据
            
        Returns:
            周刊目录路径
        """
        try:
            info = weekly_data['info']
            articles = weekly_data['articles']
            
            # 生成周刊目录名
            date_str = info.get('date', datetime.now().strftime('%Y-%m-%d'))
            date_clean = re.sub(r'[^\d-]', '', date_str)[:10]
            if not date_clean:
                date_clean = datetime.now().strftime('%Y-%m-%d')
            
            weekly_dir_name = f"周刊_{info['id']}_{date_clean}"
            weekly_dir = self.output_dir / weekly_dir_name
            weekly_dir.mkdir(parents=True, exist_ok=True)
            
            # 设置当前周刊目录（用于图片下载）
            self.current_weekly_dir = weekly_dir
            
            # 创建附件目录
            attachments_dir = weekly_dir / self.image_dir
            attachments_dir.mkdir(parents=True, exist_ok=True)
            
            # 1. 保存索引文件 00-index.md
            index_content = self._generate_index(weekly_data)
            index_file = weekly_dir / "00-index.md"
            with open(index_file, 'w', encoding='utf-8') as f:
                f.write(index_content)
            logger.info(f"保存索引文件: {index_file}")
            
            # 2. 保存每篇文章
            saved_articles = []
            for i, article in enumerate(articles, 1):
                try:
                    article_file = self._save_article(article, weekly_dir, i)
                    if article_file:
                        saved_articles.append(article_file)
                except Exception as e:
                    logger.error(f"保存文章失败: {e}")
                    continue
            
            logger.info(f"周刊保存完成: {weekly_dir}")
            logger.info(f"  - 索引文件: {index_file}")
            logger.info(f"  - 文章数量: {len(saved_articles)}")
            
            return weekly_dir
            
        except Exception as e:
            logger.error(f"保存周刊失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None
    
    def _analyze_weekly_articles(self, articles: List[Dict]) -> Dict:
        """
        分析周刊文章，提取关键信息
        
        Args:
            articles: 文章列表
            
        Returns:
            分析结果字典
        """
        if not articles:
            return {
                'keywords': [],
                'topics': [],
                'trends': [],
                'summary': '暂无文章'
            }
        
        # 收集所有文本内容
        all_text = []
        all_titles = []
        for article in articles:
            title = article.get('title', '')
            content = article.get('content', '')
            if title:
                all_titles.append(title)
            if content:
                all_text.append(content)
        
        combined_text = ' '.join(all_titles + all_text)
        
        # 提取关键词（简单方法：统计高频词）
        import re
        from collections import Counter
        
        # 中文关键词提取（2-4字词）
        chinese_words = re.findall(r'[\u4e00-\u9fff]{2,4}', combined_text)
        word_freq = Counter(chinese_words)
        
        # 过滤常见停用词和无关词
        stop_words = {
            '一个', '这个', '那个', '可以', '能够', '进行', '通过', '实现', '开发', 
            '技术', '系统', '平台', '应用', '服务', '数据', '用户', '企业', '公司',
            '如何', '什么', '为什么', '但是', '如果', '因为', '所以', '以及', '或者',
            '现在', '就是', '也是', '不是', '还是', '都是', '都是', '都是', '都是',
            '问题', '方法', '方式', '方面', '时候', '情况', '需要', '要求', '应该',
            '可能', '一定', '必须', '应该', '需要', '要求', '可以', '能够', '能够',
            '比如', '例如', '比如', '例如', '比如', '例如', '比如', '例如',
            '当然', '确实', '确实', '确实', '确实', '确实', '确实', '确实',
            '主持人', '也就是说', '说实话', '没错', '是的', '当然', '比如', '比如',
            '的问题', '的问题', '的问题', '的问题', '的问题', '的问题'
        }
        
        # 优先选择3-4字的技术术语
        keywords_3_4 = [word for word, count in word_freq.most_common(50) 
                        if word not in stop_words and 3 <= len(word) <= 4 and count >= 2]
        keywords_2 = [word for word, count in word_freq.most_common(50) 
                     if word not in stop_words and len(word) == 2 and count >= 3]
        
        keywords = (keywords_3_4 + keywords_2)[:20]
        
        # 识别主题（基于关键词和标题）
        topics = []
        topic_keywords = {
            'AI/大模型': ['AI', '大模型', '模型', '智能', '机器学习', '深度学习', 'GPT', 'LLM', 'Agent', '人工智能'],
            '架构设计': ['架构', '设计', '系统', '平台', '框架', '微服务', '分布式'],
            '云原生': ['云', 'Kubernetes', '容器', 'Docker', '云原生', 'DevOps'],
            '前端技术': ['前端', 'React', 'Vue', 'JavaScript', 'TypeScript', 'Web'],
            '后端技术': ['后端', 'Java', 'Python', 'Go', '服务', 'API'],
            '数据技术': ['数据', '数据库', '大数据', '分析', '存储'],
            '安全': ['安全', '加密', '防护', '漏洞'],
            '工程实践': ['工程', '实践', '开发', '测试', '部署', '运维']
        }
        
        for topic, keywords_list in topic_keywords.items():
            count = sum(1 for kw in keywords_list if any(kw in text for text in all_titles + all_text))
            if count > 0:
                topics.append({'name': topic, 'count': count})
        
        topics.sort(key=lambda x: x['count'], reverse=True)
        topics = topics[:8]  # 取前8个主题
        
        # 识别趋势（基于标题中的热点词汇）
        trends = []
        trend_keywords = {
            '开源': ['开源', 'Open Source'],
            '新版本发布': ['发布', '版本', '更新', 'Release'],
            '融资/投资': ['融资', '投资', '融资', 'IPO'],
            '技术突破': ['突破', '创新', '革命', '颠覆'],
            '行业动态': ['行业', '市场', '趋势', '发展']
        }
        
        for trend, keywords_list in trend_keywords.items():
            count = sum(1 for kw in keywords_list if any(kw in title for title in all_titles))
            if count > 0:
                trends.append({'name': trend, 'count': count})
        
        trends.sort(key=lambda x: x['count'], reverse=True)
        
        # 生成摘要
        summary_parts = []
        if topics:
            top_topics = ', '.join([t['name'] for t in topics[:3]])
            summary_parts.append(f"本期周刊主要关注 **{top_topics}** 等主题。")
        
        if trends:
            top_trends = ', '.join([t['name'] for t in trends[:3]])
            summary_parts.append(f"热点趋势包括：**{top_trends}**。")
        
        summary_parts.append(f"共收录 **{len(articles)}** 篇文章，涵盖技术前沿、实践案例和行业动态。")
        
        summary = ' '.join(summary_parts) if summary_parts else '本期周刊内容丰富，涵盖多个技术领域。'
        
        return {
            'keywords': keywords,
            'topics': topics,
            'trends': trends,
            'summary': summary,
            'article_count': len(articles)
        }
    
    def _generate_index(self, weekly_data: Dict) -> str:
        """生成索引文件内容"""
        info = weekly_data['info']
        articles = weekly_data['articles']
        
        # 分析文章
        analysis = self._analyze_weekly_articles(articles)
        
        lines = []
        
        # YAML Front Matter
        lines.append("---")
        lines.append(f"title: \"{info['title']} - 索引\"")
        lines.append(f"source: InfoQ周刊")
        lines.append(f"url: \"{info['url']}\"")
        lines.append(f"date: {info.get('date', datetime.now().strftime('%Y-%m-%d'))}")
        lines.append(f"created: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("tags:")
        lines.append("  - InfoQ")
        lines.append("  - 技术周刊")
        lines.append("  - 索引")
        lines.append("---")
        lines.append("")
        
        # 标题
        lines.append(f"# {info['title']}")
        lines.append("")
        lines.append(f"> 来源: [InfoQ 周刊]({info['url']})")
        lines.append(f"> 日期: {info.get('date', '未知')}")
        lines.append(f"> 文章数量: {len(articles)}")
        lines.append("")
        lines.append("---")
        lines.append("")
        
        # 周刊分析
        lines.append("## 📊 周刊分析")
        lines.append("")
        lines.append("### 内容摘要")
        lines.append("")
        lines.append(analysis['summary'])
        lines.append("")
        
        if analysis['topics']:
            lines.append("### 主要主题")
            lines.append("")
            for topic in analysis['topics']:
                lines.append(f"- **{topic['name']}**: {topic['count']} 篇相关文章")
            lines.append("")
        
        if analysis['trends']:
            lines.append("### 热点趋势")
            lines.append("")
            for trend in analysis['trends']:
                lines.append(f"- **{trend['name']}**: {trend['count']} 篇相关文章")
            lines.append("")
        
        if analysis['keywords']:
            lines.append("### 关键词")
            lines.append("")
            keywords_str = '、'.join(analysis['keywords'][:20])
            lines.append(f"{keywords_str}")
            lines.append("")
        
        lines.append("---")
        lines.append("")
        
        # 文章列表
        if articles:
            lines.append("## 📚 文章列表")
            lines.append("")
            for i, article in enumerate(articles, 1):
                title = article.get('title', '').strip()
                if not title or title == f'文章{i}':
                    # 尝试从文件名推断标题
                    article_filename = self._generate_article_filename(article, i)
                    # 从文件名中提取标题（去掉序号和扩展名）
                    filename_title = article_filename.replace(f"{i:02d}-", "").replace(".md", "")
                    if filename_title and filename_title != f"文章{i:02d}":
                        title = filename_title
                    else:
                        title = f"文章 {i}"
                
                # 生成文章文件名
                article_filename = self._generate_article_filename(article, i)
                lines.append(f"{i}. [{title}]({article_filename})")
                if article.get('author'):
                    lines.append(f"   - 作者: {article['author']}")
                if article.get('url'):
                    lines.append(f"   - [原文链接]({article['url']})")
                lines.append("")
        else:
            lines.append("## 📚 文章列表")
            lines.append("")
            lines.append("暂无文章")
            lines.append("")
        
        return '\n'.join(lines)
    
    def _generate_article_filename(self, article: Dict, index: int) -> str:
        """生成文章文件名"""
        title = article.get('title', f'文章{index}')
        # 清理文件名：移除特殊字符，限制长度
        safe_title = re.sub(r'[<>:"/\\|?*]', '', title)
        safe_title = safe_title[:50]  # 限制长度
        safe_title = safe_title.strip()
        
        # 如果标题为空，使用索引
        if not safe_title:
            safe_title = f"文章{index:02d}"
        
        return f"{index:02d}-{safe_title}.md"
    
    def _save_article(self, article: Dict, weekly_dir: Path, index: int) -> Optional[Path]:
        """保存单篇文章"""
        try:
            title = article.get('title', f'文章{index}')
            filename = self._generate_article_filename(article, index)
            filepath = weekly_dir / filename
            
            lines = []
            
            # YAML Front Matter
            lines.append("---")
            lines.append(f"title: \"{title}\"")
            lines.append(f"source: InfoQ")
            if article.get('url'):
                lines.append(f"url: \"{article['url']}\"")
            if article.get('author'):
                lines.append(f"author: \"{article['author']}\"")
            if article.get('publish_time'):
                lines.append(f"publish_time: \"{article['publish_time']}\"")
            lines.append(f"created: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            lines.append("tags:")
            lines.append("  - InfoQ")
            lines.append("---")
            lines.append("")
            
            # 标题
            lines.append(f"# {title}")
            lines.append("")
            
            # 元信息
            if article.get('author'):
                lines.append(f"**作者**: {article['author']}")
            if article.get('publish_time'):
                lines.append(f"**发布时间**: {article['publish_time']}")
            if article.get('url'):
                lines.append(f"**原文链接**: [{article['url']}]({article['url']})")
            lines.append("")
            lines.append("---")
            lines.append("")
            
            # 正文内容
            if article.get('content'):
                lines.append(article['content'])
                lines.append("")
            
            # 检查是否有未嵌入的图片，添加到末尾
            if article.get('images'):
                content_text = article.get('content', '')
                unembedded_images = []
                for img in article['images']:
                    local_path = img.get('local', '')
                    if local_path and local_path not in content_text:
                        unembedded_images.append(img)
                
                if unembedded_images:
                    lines.append("## 附图")
                    lines.append("")
                    for img in unembedded_images:
                        alt = img.get('alt', '图片') or '图片'
                        local_path = img.get('local', '')
                        if local_path:
                            lines.append(f"![[{local_path}|{alt}]]")
                    lines.append("")
            
            # 保存文件
            content = '\n'.join(lines)
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            
            logger.info(f"保存文章: {filename}")
            return filepath
            
        except Exception as e:
            logger.error(f"保存文章失败: {e}")
            return None
    
    def crawl_latest(self, count: int = 1, force: bool = False) -> List[Path]:
        """
        爬取最新的周刊
        
        Args:
            count: 要爬取的期数
            force: 是否强制重新爬取已处理的周刊
            
        Returns:
            保存的文件路径列表
        """
        saved_files = []
        
        try:
            # 获取周刊列表
            weekly_list = self._get_weekly_list()
            
            if not weekly_list:
                logger.warning("未获取到周刊列表")
                return saved_files
            
            # 按 ID 降序排序（最新的在前）
            weekly_list.sort(key=lambda x: int(x.get('id', 0)), reverse=True)
            
            # 选择要爬取的周刊
            to_crawl = []
            for weekly in weekly_list[:count * 2]:  # 多取一些以防有些已处理
                if force or weekly['id'] not in self.processed_weekly:
                    to_crawl.append(weekly)
                    if len(to_crawl) >= count:
                        break
            
            if not to_crawl:
                logger.info("没有新的周刊需要爬取")
                return saved_files
            
            # 爬取每期周刊
            for weekly_info in to_crawl:
                try:
                    logger.info(f"开始爬取: {weekly_info['title']}")
                    
                    # 获取周刊内容
                    weekly_data = self._get_weekly_content(weekly_info)
                    
                    # 获取每篇文章的详细内容
                    for i, article in enumerate(weekly_data['articles']):
                        if article.get('url'):
                            detail = self._get_article_detail(article['url'], weekly_info['id'])
                            if detail:
                                weekly_data['articles'][i].update(detail)
                    
                    # 保存周刊（新结构：子目录+索引+单独文章）
                    weekly_dir = self._save_weekly(weekly_data)
                    if weekly_dir:
                        saved_files.append(weekly_dir)
                        self.processed_weekly.add(weekly_info['id'])
                    
                    # 适当延迟，避免请求过快
                    time.sleep(2)
                    
                except Exception as e:
                    logger.error(f"爬取周刊失败 {weekly_info['id']}: {e}")
                    continue
            
            # 保存处理记录
            self._save_processed()
            
        except Exception as e:
            logger.error(f"爬取过程出错: {e}")
            
        finally:
            self._close_driver()
        
        return saved_files
    
    def run(self):
        """主运行方法"""
        logger.info("="*50)
        logger.info("InfoQ 周刊爬虫启动")
        logger.info(f"输出目录: {self.output_dir}")
        logger.info("="*50)
        
        saved_files = self.crawl_latest(count=1)
        
        logger.info("="*50)
        logger.info(f"爬取完成，共保存 {len(saved_files)} 期周刊")
        for f in saved_files:
            logger.info(f"  - {f}")
        logger.info("="*50)
        
        return saved_files


def main():
    """主入口"""
    # 配置
    OUTPUT_DIR = "/Users/ice7/Documents/01.curwork/data/obsidian-rep/Infoq"
    
    # 创建爬虫实例并运行
    crawler = InfoQWeeklyCrawler(output_dir=OUTPUT_DIR)
    crawler.run()


if __name__ == "__main__":
    main()
