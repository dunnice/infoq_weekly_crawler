#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
InfoQ 周刊爬虫

流程说明：
1. 通过 API 一次请求获取多期周刊列表：POST，Referer=weekly/landing，Content-Type=application/json，payload={"size":100}。
2. 按周处理：目录名为 周刊_{周刊number}_{周刊时间转为 yyyy-mm-dd}。
3. 每期：获取该期文章列表，检查每篇文章本地是否已下载（按 URL 记录）；未下载则抓取正文与图片并保存。
4. 入口：无参数 = 拉取 100 期列表并逐期同步；指定期号 = 只同步该期（需能拿到该期文章列表）。
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
import sys
import io

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from webdriver_manager.chrome import ChromeDriverManager

# 确保终端输出使用 UTF-8，避免中文日志在部分环境下乱码
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "buffer"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        # 文件日志：保留完整中文信息
        logging.FileHandler("infoq_crawler.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

# 终端日志：只输出 ASCII，可读进度信息，避免中文在终端环境下乱码
class _AsciiOnlyFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:  # type: ignore[override]
        try:
            msg = record.getMessage()
            # 将消息转换为只包含 ASCII 字符（中文会变成 ?）
            safe = msg.encode("ascii", errors="replace").decode("ascii")
            record.msg = safe
            record.args = ()
        except Exception:
            pass
        return True

_console_handler = logging.StreamHandler()
_console_handler.setLevel(logging.INFO)
_console_handler.addFilter(_AsciiOnlyFilter())
_console_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
logger.addHandler(_console_handler)

# 脚本所在目录：用于扫描「每周精要」HTML
SCRIPT_DIR = Path(__file__).resolve().parent


class InfoQWeeklyCrawler:
    """InfoQ 周刊爬虫：以本地「每周精要」HTML 为文章列表来源，按 URL 去重抓取。"""

    BASE_URL = "https://www.infoq.cn"

    def __init__(self, output_dir: str, image_dir: str = "attachments", edm_dir: Optional[Path] = None):
        self.output_dir = Path(output_dir)
        self.image_dir = image_dir
        self.edm_dir = Path(edm_dir) if edm_dir else SCRIPT_DIR
        self.driver = None
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        })
        self.processed_articles_file = self.output_dir / ".processed_articles.json"
        self.processed_articles = self._load_processed_articles()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.current_weekly_dir: Optional[Path] = None
        # API 配置（与 config 对齐，便于覆盖）
        try:
            import config as _cfg
            self._api_referer = getattr(_cfg, "WEEKLY_LIST_REFERER", "https://www.infoq.cn/weekly/landing")
            self._api_url = getattr(_cfg, "WEEKLY_LIST_API_URL", "") or ""
            self._api_size = getattr(_cfg, "WEEKLY_LIST_PAYLOAD_SIZE", 100)
        except ImportError:
            self._api_referer = "https://www.infoq.cn/weekly/landing"
            self._api_url = ""
            self._api_size = 100

    def _load_processed_articles(self) -> Dict[str, set]:
        if self.processed_articles_file.exists():
            try:
                with open(self.processed_articles_file, "r", encoding="utf-8") as f:
                    raw = json.load(f) or {}
                return {str(k): set(v or []) for k, v in raw.items()}
            except Exception as e:
                logger.warning("加载已处理文章记录失败: %s", e)
        return {}

    def _save_processed_articles(self):
        try:
            data = {k: sorted(list(v)) for k, v in self.processed_articles.items()}
            with open(self.processed_articles_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error("保存已处理文章记录失败: %s", e)

    def _normalize_week_time_to_date(self, raw: Optional[str], ts_ms: Optional[int] = None) -> str:
        """将周刊时间转为 yyyy-mm-dd。支持时间戳（毫秒）或日期字符串。"""
        if ts_ms is not None:
            try:
                return datetime.fromtimestamp(ts_ms / 1000.0).strftime("%Y-%m-%d")
            except Exception:
                pass
        if raw:
            s = re.sub(r"[^\d-]", "", str(raw))[:10]
            if len(s) >= 10:
                return s
            # 尝试解析 20260311 等
            m = re.search(r"(\d{4})(\d{2})(\d{2})", str(raw))
            if m:
                return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
        return datetime.now().strftime("%Y-%m-%d")

    # ---------- 1. API：一次请求获取多期周刊列表 ----------
    def fetch_weekly_list_from_api(self, size: Optional[int] = None) -> List[Dict]:
        """
        请求周刊列表 API：Referer=weekly/landing，Content-Type=application/json，payload={"size": N}。
        对于 getPaperList 接口，返回的数据形如：
        {"code":0,"data":[{"number":914,"time":1772812800,"url":"https://static001.geekbang.org/edm/...html"},...]}
        这里将其规范为 [{"id": str, "date": "yyyy-mm-dd", "articles": None, "edm_url": str}, ...]。
        """
        size = size if size is not None else self._api_size
        url = (self._api_url or "").strip()
        if not url:
            # 未配置真实接口时，不发请求（避免打到不存在的默认地址）
            return []
        headers = {
            "Referer": self._api_referer,
            "Content-Type": "application/json",
            "User-Agent": self.session.headers.get("User-Agent", ""),
            "Accept": "application/json",
        }
        payload = {"size": size}
        out: List[Dict] = []
        try:
            resp = self.session.post(url, json=payload, headers=headers, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.warning("周刊列表 API 请求失败（将尝试备用方式）: %s", e)
            return out
        # 兼容多种响应结构：以 getPaperList 的 data 数组为主
        raw_list = data.get("data") if isinstance(data, dict) else None
        if not raw_list or not isinstance(raw_list, list):
            logger.warning("周刊列表 API 返回格式异常: 无 data 数组")
            return out
        for item in raw_list:
            if not isinstance(item, dict):
                continue
            # 期号：number（getPaperList）或其他兼容字段
            wid = item.get("number") or item.get("id") or item.get("weeklyId") or item.get("issueId")
            if wid is None:
                continue
            issue_id = str(wid)
            # 时间：getPaperList 的 time 为秒级时间戳
            ts_sec = item.get("time")
            date_str = None
            if isinstance(ts_sec, (int, float)):
                try:
                    date_str = datetime.fromtimestamp(ts_sec).strftime("%Y-%m-%d")
                except Exception:
                    date_str = None
            if not date_str:
                date_str = self._normalize_week_time_to_date(None, None)
            edm_url = item.get("url") or ""
            if edm_url and not edm_url.startswith("http"):
                edm_url = urljoin(self.BASE_URL, edm_url)
            out.append({"id": issue_id, "date": date_str, "articles": None, "edm_url": edm_url})
        logger.info("从 API(getPaperList) 解析到 %s 期周刊", len(out))
        return out

    LANDING_URL = "https://www.infoq.cn/weekly/landing"

    def fetch_weekly_list_from_landing_page(self) -> List[Dict]:
        """
        用 Selenium 打开 weekly/landing 页，解析页面上所有往期链接（/weekly/数字），
        返回 [{"id": str, "date": "yyyy-mm-dd" or None}, ...]，按期号降序（最新在前）。
        """
        self._init_driver()
        out: List[Dict] = []
        try:
            logger.info("正在打开 landing 页: %s", self.LANDING_URL)
            self.driver.get(self.LANDING_URL)
            time.sleep(5)
            try:
                WebDriverWait(self.driver, 15).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )
                # 等待往期列表链接出现（SPA 可能异步加载）
                WebDriverWait(self.driver, 20).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "a[href*='/weekly/']"))
                )
            except TimeoutException:
                pass
            time.sleep(2)
            # 滚动以触发懒加载
            for _ in range(3):
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            self.driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(1)
            soup = BeautifulSoup(self.driver.page_source, "html.parser")
            # 收集所有 /weekly/数字 链接（排除 landing、preview、wechat 等）
            seen_ids = set()
            for a in soup.find_all("a", href=True):
                href = (a.get("href") or "").strip()
                if not href or "weekly" not in href.lower():
                    continue
                m = re.search(r"(?:/|#/)weekly/(\d+)(?:/|$|\?|#)", href)
                if not m:
                    continue
                issue_id = m.group(1)
                if issue_id in seen_ids:
                    continue
                seen_ids.add(issue_id)
                date_str = None
                # 尝试从同一行/父级取日期（如 class 含 date 的节点）
                parent = a.find_parent(["li", "div", "tr"])
                if parent:
                    date_el = parent.find(class_=re.compile(r"date|time|publish", re.I))
                    if date_el:
                        raw = date_el.get_text(strip=True)
                        if raw and re.search(r"\d", raw):
                            date_str = self._normalize_week_time_to_date(raw, None)
                out.append({"id": issue_id, "date": date_str, "articles": None})
            out.sort(key=lambda x: int(x["id"]), reverse=True)
            logger.info("从 landing 页解析到 %s 期往期", len(out))
        except Exception as e:
            logger.warning("从 landing 页解析往期列表失败: %s", e)
        return out

    # ---------- 2. 发现可爬期号（本地「每周精要」HTML，用作文章列表备用）----------
    def discover_issues(self) -> Dict[str, Path]:
        """
        扫描 edm_dir 下所有「InfoQ*No.{期号}*.html」。
        返回 {issue_id: html_path}，同期的多份取修改时间最新的一份。
        """
        mapping: Dict[str, Path] = {}
        for p in self.edm_dir.glob("InfoQ*No.*.html"):
            m = re.search(r"No\.(\d+)", p.name)
            if not m:
                continue
            issue_id = m.group(1)
            if issue_id not in mapping or (p.stat().st_mtime > mapping[issue_id].stat().st_mtime):
                mapping[issue_id] = p
        return mapping

    def get_article_links_from_edm(self, issue_id: str, edm_url: Optional[str] = None) -> List[Dict[str, str]]:
        """
        从该期「每周精要」HTML 中解析出精选文章链接（仅 article/news，去重）。
        优先使用 API 返回的 edm_url 在线获取；否则退回到本地保存的 InfoQ 每周精要 No.xxx.html。
        返回 [{"url": "...", "title": "..."}, ...]。
        """
        html = ""
        html_path: Optional[Path] = None
        # 1) 若 API 提供了 edm_url，则直接在线获取 HTML
        if edm_url:
            try:
                resp = self.session.get(edm_url, timeout=30)
                resp.raise_for_status()
                # 避免 requests 错误按 ISO-8859-1 解码导致中文标题乱码，优先按 UTF-8 直接解码
                raw = resp.content
                try:
                    html = raw.decode("utf-8")
                except UnicodeDecodeError:
                    # 回退到 requests 的自动检测
                    resp.encoding = resp.apparent_encoding or "utf-8"
                    html = resp.text
            except Exception as e:
                logger.warning("从 edm_url 获取第 %s 期精要 HTML 失败: %s", issue_id, e)
        # 2) 如果没有 edm_url 或在线获取失败，则退回到本地 HTML 文件
        if not html:
            mapping = self.discover_issues()
            html_path = mapping.get(str(issue_id))
            if not html_path or not html_path.exists():
                return []
            html = html_path.read_text(encoding="utf-8", errors="ignore")
        try:
            soup = BeautifulSoup(html, "html.parser")
            links = []
            for a in soup.find_all("a", href=True):
                href = (a.get("href") or "").strip()
                h = href.lower()
                if not (
                    "infoq.cn/article/" in h
                    or "xie.infoq.cn/article/" in h
                    or "infoq.cn/news/" in h
                ):
                    continue
                if any(x in h for x in ["/video/", "/theme/", "/minibook/", "space/"]):
                    continue
                title = (a.get_text(" ", strip=True) or "")[:200]
                if not title or len(title) < 3:
                    continue
                full_url = href if href.startswith("http") else urljoin(self.BASE_URL, href)
                links.append({"url": full_url, "title": title})
            seen = set()
            uniq = []
            for it in links:
                if it["url"] in seen:
                    continue
                seen.add(it["url"])
                uniq.append(it)
            if uniq:
                src = html_path.name if html_path else (edm_url or "inline-html")
                logger.info("从精要 HTML 解析到 %s 条链接: %s", len(uniq), src)
            return uniq
        except Exception as e:
            logger.warning("解析精要 HTML 失败（issue=%s）: %s", issue_id, e)
            return []

    def get_article_links_for_week(self, issue_id: str, from_api: Optional[List[Dict]] = None, edm_url: Optional[str] = None) -> List[Dict[str, str]]:
        """
        获取某一期的文章链接列表。
        规则（严格按照「每周精要」列表）：
        1）若 from_api 提供该期 articles，则直接使用；
        2）否则仅使用本地「每周精要 No.xxx.html」解析结果；
        3）如果本地没有对应 HTML，则本期直接跳过（不再从 /weekly/{id} 热推流里“猜测”文章列表）。
        返回 [{"url": "...", "title": "..."}, ...]。
        """
        if from_api and isinstance(from_api, list):
            return from_api
        links = self.get_article_links_from_edm(issue_id, edm_url=edm_url)
        if links:
            return links
        logger.warning("第 %s 期没有本地「每周精要」HTML，且未从 API 获得文章列表，本期将跳过以保持与精要列表一致", issue_id)
        return []

    def is_article_downloaded(self, issue_id: str, article_url: str) -> bool:
        """判断该期下该文章是否已下载（以 URL 是否在 processed_articles 中为准）。"""
        return (article_url or "") in self.processed_articles.get(str(issue_id), set())

    # ---------- 4. 本期目录与附件目录 ----------
    def _weekly_dir_path(self, issue_id: str, date_str: Optional[str] = None) -> Path:
        date_clean = (re.sub(r"[^\d-]", "", (date_str or "")[:10]) or datetime.now().strftime("%Y-%m-%d"))[:10]
        return self.output_dir / f"周刊_{issue_id}_{date_clean}"

    def prepare_weekly_dir(self, issue_id: str, date_str: Optional[str] = None, clean: bool = False) -> Path:
        """创建本期目录与 attachments 子目录，设为 current_weekly_dir。clean=True 时删除该期下已有 .md 与 debug 快照。"""
        weekly_dir = self._weekly_dir_path(issue_id, date_str)
        weekly_dir.mkdir(parents=True, exist_ok=True)
        (weekly_dir / self.image_dir).mkdir(parents=True, exist_ok=True)
        if clean:
            for name in ["00-index.md", "debug_weekly_page.html"]:
                for p in weekly_dir.glob(name):
                    try:
                        p.unlink()
                    except Exception:
                        pass
            for p in weekly_dir.glob("[0-9][0-9]-*.md"):
                try:
                    p.unlink()
                except Exception:
                    pass
        self.current_weekly_dir = weekly_dir
        logger.info("本期周刊目录已就绪: %s", weekly_dir)
        return weekly_dir

    def _download_image(self, img_url: str) -> Optional[str]:
        """下载图片到 current_weekly_dir/attachments/，返回相对路径如 attachments/xxx.jpg。"""
        try:
            if not img_url or img_url.startswith("data:"):
                return None
            if img_url.startswith("//"):
                img_url = "https:" + img_url
            elif img_url.startswith("/"):
                img_url = urljoin(self.BASE_URL, img_url)
            if not self.current_weekly_dir:
                logger.warning("未设置本期周刊目录，跳过图片下载")
                return None
            url_hash = hashlib.md5(img_url.encode()).hexdigest()[:8]
            path_lower = urlparse(img_url).path.lower()
            ext = ".png" if ".png" in path_lower else ".gif" if ".gif" in path_lower else ".webp" if ".webp" in path_lower else ".jpg"
            filename = f"{url_hash}{ext}"
            attachments_dir = self.current_weekly_dir / self.image_dir
            local_path = attachments_dir / filename
            rel = f"{self.image_dir}/{filename}"
            if local_path.exists():
                return rel
            resp = self.session.get(img_url, timeout=30)
            resp.raise_for_status()
            with open(local_path, "wb") as f:
                f.write(resp.content)
            return rel
        except Exception as e:
            logger.warning("下载图片失败 %s: %s", img_url[:80], e)
            return None

    # ---------- 5. 文章详情（Selenium + 正文提取 + 去广告）----------
    _AD_CLASS_KEYWORDS = [
        "ad", "ads", "advert", "advertisement", "promo", "sponsor", "recommend",
        "related", "hot", "share", "qrcode", "follow", "course", "buy", "banner",
        "推广", "广告", "推荐阅读", "延伸阅读", "你可能还喜欢",
    ]
    _AD_TEXT_KEYWORDS = [
        "广告", "推广", "赞助", "推荐阅读", "扫码", "关注公众号", "训练营", "课程",
        "立即购买", "优惠", "更多精彩", "你可能还喜欢", "延伸阅读", "关注我们", "了解更多",
        "订阅", "报名", "限时", "抢购", "点击领取",
    ]

    def _init_driver(self):
        if self.driver is not None:
            return
        opts = Options()
        opts.add_argument("--headless")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--disable-gpu")
        opts.add_argument("--window-size=1920,1080")
        opts.add_argument("--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        try:
            self.driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)
            self.driver.implicitly_wait(10)
            logger.info("WebDriver 初始化成功")
        except Exception as e:
            logger.error("WebDriver 初始化失败: %s", e)
            raise

    def _close_driver(self):
        if self.driver:
            self.driver.quit()
            self.driver = None

    def _remove_article_ads(self, content_area) -> None:
        if not content_area:
            return
        for elem in list(content_area.find_all(True)):
            try:
                if elem is None or not getattr(elem, "attrs", None):
                    continue
                classes = elem.get("class") or []
                class_str = " ".join(classes).lower() if isinstance(classes, list) else str(classes).lower()
                if any(kw in class_str for kw in self._AD_CLASS_KEYWORDS):
                    elem.decompose()
                    continue
                text = (elem.get_text(strip=True) or "") if hasattr(elem, "get_text") else ""
                if len(text) < 300 and any(kw in text for kw in self._AD_TEXT_KEYWORDS):
                    elem.decompose()
            except Exception:
                continue

    def _trim_trailing_ads(self, paragraphs: List[str], images: List[Dict]) -> Tuple[List[str], List[Dict]]:
        if not paragraphs:
            return paragraphs, images
        new_paragraphs = list(paragraphs)
        while new_paragraphs:
            last = new_paragraphs[-1].strip()
            if not last:
                new_paragraphs.pop()
                continue
            if len(last) < 250 and any(kw in last for kw in self._AD_TEXT_KEYWORDS):
                new_paragraphs.pop()
                continue
            break
        content_str = "\n".join(new_paragraphs)
        kept_paths = set(re.findall(r"!\[\[(attachments/[^\|\]]+)", content_str))
        new_images = [
            img for img in images
            if ((img.get("local") or "").split("|")[0].strip() in kept_paths
                or (img.get("local") or "").strip() in kept_paths)
        ]
        return new_paragraphs, new_images

    def fetch_article_detail(self, article_url: str, weekly_id: str, list_title: str = "") -> Optional[Dict]:
        """
        用 Selenium 打开文章详情页，提取标题、正文、图片、作者、时间；
        正文区域去广告、末尾广告裁剪；图片下载到 current_weekly_dir/attachments/。
        返回 {"title","content","images","author","publish_time","url"}，失败返回 None。
        """
        if not article_url:
            return None
        self._init_driver()
        try:
            self.driver.get(article_url)
            time.sleep(3)
            try:
                WebDriverWait(self.driver, 15).until(
                    EC.presence_of_element_located((By.CLASS_NAME, "article-content-layout"))
                )
                time.sleep(2)
            except TimeoutException:
                try:
                    WebDriverWait(self.driver, 10).until(
                        EC.presence_of_element_located((By.TAG_NAME, "body"))
                    )
                    time.sleep(2)
                except TimeoutException:
                    logger.warning("页面加载超时: %s", article_url)
                    return None
            soup = BeautifulSoup(self.driver.page_source, "html.parser")
            title = ""
            for sel in ["h1.article-title", "h1", ".article-title"]:
                try:
                    if " " in sel:
                        tag, cls = sel.split(".", 1)
                        el = soup.find(tag, class_=cls)
                    else:
                        el = soup.find(sel.lstrip(".")) if sel.startswith(".") else soup.find(sel)
                    if el and el.get_text(strip=True):
                        title = el.get_text(strip=True)
                        if len(title) > 10:
                            break
                except Exception:
                    continue
            if not title and list_title:
                title = list_title
            if not title:
                title = "未命名"

            content_area = None
            for sel in [
                ".article-content-wrap",
                ".article-main",
                ".content-main",
                ".article-content-layout",
                "article",
                ".content",
                "main",
            ]:
                if " " in sel:
                    parts = sel.split()
                    parent = soup.find(class_=parts[0].lstrip(".")) if parts[0].startswith(".") else soup.find(parts[0])
                    content_area = parent.find(class_=parts[1].lstrip(".")) if parent and parts[1].startswith(".") else (parent.find(parts[1]) if parent else None)
                else:
                    content_area = soup.find(class_=sel.lstrip(".")) if sel.startswith(".") else soup.find(sel)
                if content_area:
                    text = content_area.get_text(strip=True)
                    if len(text) > 500 and any(c in text for c in ["。", "，", "的", "是"]):
                        break
                    content_area = None
            if not content_area:
                for div in soup.find_all("div"):
                    text = div.get_text(strip=True)
                    if len(text) > 500 and div.find("p") and any(c in text for c in ["。", "，", "的"]):
                        content_area = div
                        break
            if not content_area:
                logger.warning("未找到正文区域: %s", article_url)
                return None

            for unwanted in content_area.find_all(class_=lambda x: x and any(
                kw in str(x).lower() for kw in ["ad", "comment", "share", "sidebar", "related", "recommend", "hot"]
            )):
                unwanted.decompose()
            self._remove_article_ads(content_area)

            paragraphs = []
            images = []
            processed_imgs = set()

            def process(el):
                if el.name == "img":
                    src = el.get("src") or el.get("data-src") or el.get("data-original")
                    if src and not src.startswith("data:") and src not in processed_imgs:
                        local = self._download_image(src)
                        if local:
                            alt = el.get("alt") or el.get("title") or "图片"
                            images.append({"original": src, "local": local, "alt": alt})
                            processed_imgs.add(src)
                            paragraphs.append(f"\n![[{local}|{alt}]]\n")
                    return
                if el.name in ["p", "h1", "h2", "h3", "h4", "h5", "h6", "pre", "code", "blockquote", "li"]:
                    for c in getattr(el, "children", []):
                        if getattr(c, "name", None) == "img":
                            process(c)
                    copy = BeautifulSoup(str(el), "html.parser")
                    for img in copy.find_all("img"):
                        img.decompose()
                    text = copy.get_text(strip=True)
                    if not text or len(text) < 3:
                        return
                    if el.name == "p":
                        paragraphs.append(text)
                    elif el.name in ["h1", "h2", "h3", "h4", "h5", "h6"]:
                        lv = int(el.name[1])
                        paragraphs.append(f"\n{'#' * lv} {text}\n")
                    elif el.name in ["pre", "code"]:
                        paragraphs.append(f"\n```\n{text}\n```\n")
                    elif el.name == "blockquote":
                        paragraphs.append(f"> {text}")
                    elif el.name == "li":
                        paragraphs.append(f"- {text}")
                    return
                if el.name in ["div", "section", "article", "main", "ul", "ol"]:
                    for c in getattr(el, "children", []):
                        if getattr(c, "name", None):
                            process(c)

            for child in getattr(content_area, "children", []):
                if getattr(child, "name", None):
                    process(child)

            paragraphs, images = self._trim_trailing_ads(paragraphs, images)

            author = ""
            for sel in [".author", ".writer", ".by", ".article-author"]:
                el = soup.find(class_=sel.lstrip("."))
                if el:
                    author = el.get_text(strip=True)
                    break
            publish_time = ""
            for sel in ["time", ".publish-time", ".date", ".article-date"]:
                el = soup.find("time") if sel == "time" else soup.find(class_=sel.lstrip("."))
                if el:
                    publish_time = el.get_text(strip=True)
                    break

            return {
                "title": title,
                "content": "\n\n".join(paragraphs),
                "images": images,
                "author": author,
                "publish_time": publish_time,
                "url": article_url,
            }
        except Exception as e:
            logger.warning("获取文章详情失败 %s: %s", article_url, e)
            return None

    # ---------- 6. 保存单篇文章与索引 ----------
    def _article_filename(self, article: Dict, index: int) -> str:
        title = article.get("title", f"文章{index}")
        safe = re.sub(r'[<>:"/\\|?*]', "", title)[:50].strip() or f"文章{index:02d}"
        return f"{index:02d}-{safe}.md"

    def save_article(self, article: Dict, index: int) -> Optional[Path]:
        if not self.current_weekly_dir:
            return None
        try:
            filename = self._article_filename(article, index)
            path = self.current_weekly_dir / filename
            title = article.get("title", f"文章{index}")
            lines = [
                "---",
                f'title: "{title}"',
                "source: InfoQ",
                f'url: "{article.get("url", "")}"',
                f'author: "{article.get("author", "")}"',
                f'publish_time: "{article.get("publish_time", "")}"',
                f'created: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}',
                "tags:",
                "  - InfoQ",
                "---",
                "",
                f"# {title}",
                "",
            ]
            if article.get("author"):
                lines.append(f"**作者**: {article['author']}")
            if article.get("publish_time"):
                lines.append(f"**发布时间**: {article['publish_time']}")
            if article.get("url"):
                lines.append(f"**原文链接**: [{article['url']}]({article['url']})")
            lines.extend(["", "---", ""])
            if article.get("content"):
                lines.append(article["content"])
                lines.append("")
            content_text = article.get("content", "")
            unembedded = [img for img in article.get("images", []) if (img.get("local") or "") and (img.get("local") or "").split("|")[0] not in content_text]
            if unembedded:
                lines.append("## 附图")
                lines.append("")
                for img in unembedded:
                    alt = img.get("alt", "图片")
                    lines.append(f"![[{img.get('local', '')}|{alt}]]")
                lines.append("")
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
            logger.info("保存文章: %s", filename)
            return path
        except Exception as e:
            logger.error("保存文章失败: %s", e)
            return None

    def generate_index(self, issue_id: str, date_str: Optional[str], articles: List[Dict]) -> str:
        """生成 00-index.md 内容，文章列表使用 Obsidian 双链 [[文件名|标题]]。"""
        lines = [
            "---",
            f'title: "InfoQ周刊第{issue_id}期 - 索引"',
            "source: InfoQ周刊",
            f'url: "{self.BASE_URL}/weekly/{issue_id}"',
            f"date: {date_str or datetime.now().strftime('%Y-%m-%d')}",
            f'created: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}',
            "tags:",
            "  - InfoQ",
            "  - 技术周刊",
            "  - 索引",
            "---",
            "",
            f"# InfoQ周刊第{issue_id}期",
            "",
            f"> 来源: [InfoQ 周刊]({self.BASE_URL}/weekly/{issue_id})",
            f"> 日期: {date_str or '未知'}",
            f"> 文章数量: {len(articles)}",
            "",
            "---",
            "",
            "## 文章列表",
            "",
        ]
        for i, article in enumerate(articles, 1):
            title = (article.get("title") or "").strip() or f"文章{i}"
            filename = self._article_filename(article, i)
            display = title[:80].replace("|", "｜").replace("]]", "").replace("\n", " ").strip() or filename
            lines.append(f"{i}. [[{filename}|{display}]]")
            if article.get("author"):
                lines.append(f"   - 作者: {article['author']}")
            if article.get("url"):
                lines.append(f"   - [原文链接]({article['url']})")
            lines.append("")
        return "\n".join(lines)

    # ---------- 7. 按周同步：建目录 + 检查已下载 + 未下载则抓取 ----------
    def sync_issue(self, issue_id: str, force: bool = True, date_str: Optional[str] = None) -> Optional[Path]:
        """
        同步一期：获取该期文章列表；每篇检查本地是否已下载，未下载则抓取；最后写 00-index.md。
        """
        # 通过 getPaperList 无法单独按期过滤，只能依靠已有本地精要 HTML 或手动提供 edm_url；
        # 这里沿用原有行为：仅使用本地「每周精要」HTML。
        return self._sync_one_week(issue_id, date_str, from_api_articles=None, edm_url=None, force=force)

    # ---------- 8. 一次请求 100 期列表，按周建目录并逐篇检查是否已下载 ----------
    def sync_all(self, size: Optional[int] = None, force: bool = False) -> List[Path]:
        """
        请求周刊列表 API（payload size=100），按周处理：
        目录名 周刊_{number}_{yyyy-mm-dd}；每期文章列表中未下载的才抓取。
        """
        size = size if size is not None else self._api_size
        weekly_list = self.fetch_weekly_list_from_api(size=size)
        if not weekly_list:
            logger.info("API 未返回列表，改为从 landing 页抓取往期列表: %s", self.LANDING_URL)
            weekly_list = self.fetch_weekly_list_from_landing_page()
        if not weekly_list:
            logger.warning("landing 页也未解析到列表，尝试用本地精要 HTML 同步")
            issues = self.discover_issues()
            if not issues:
                logger.warning("未发现任何「每周精要」HTML，请将 InfoQ*No.xxx.html 放入目录: %s", self.edm_dir)
                return []
            weekly_list = [{"id": iid, "date": None, "articles": None} for iid in sorted(issues.keys(), key=int)]
        saved = []
        for week in weekly_list:
            issue_id = str(week.get("id", ""))
            if not issue_id:
                continue
            date_str = week.get("date")
            try:
                path = self._sync_one_week(
                    issue_id,
                    date_str,
                    from_api_articles=week.get("articles"),
                    edm_url=week.get("edm_url"),
                    force=force,
                )
                if path:
                    saved.append(path)
            except Exception as e:
                logger.error("同步第 %s 期失败: %s", issue_id, e)
        return saved

    def _sync_one_week(
        self,
        issue_id: str,
        date_str: Optional[str],
        from_api_articles: Optional[List[Dict]] = None,
        edm_url: Optional[str] = None,
        force: bool = False,
    ) -> Optional[Path]:
        """处理单期：建目录 周刊_{id}_{date}，取文章列表（严格基于每周精要），未下载则抓取，写索引。"""
        links = self.get_article_links_for_week(issue_id, from_api=from_api_articles, edm_url=edm_url)
        if not links:
            logger.debug("第 %s 期无文章列表，跳过", issue_id)
            return None
        self.prepare_weekly_dir(issue_id, date_str, clean=force)
        weekly_id = issue_id
        issue_done = self.processed_articles.setdefault(issue_id, set())
        articles = []
        for i, link in enumerate(links, 1):
            url = link.get("url", "")
            title_from_list = link.get("title", "")
            if not url:
                continue
            if self.is_article_downloaded(issue_id, url):
                logger.info("跳过已下载: %s", url[:60])
                articles.append({"title": title_from_list or f"文章{i}", "url": url, "content": "", "images": [], "author": "", "publish_time": ""})
                continue
            logger.info("抓取 %s/%s: %s", i, len(links), (title_from_list or url)[:50])
            detail = self.fetch_article_detail(url, weekly_id, list_title=title_from_list)
            if detail:
                if title_from_list and len(title_from_list) > 5:
                    detail["title"] = title_from_list
                articles.append(detail)
                issue_done.add(url)
                self._save_processed_articles()
                self.save_article(detail, len(articles))
            else:
                articles.append({"title": title_from_list or f"文章{i}", "url": url, "content": "", "images": [], "author": "", "publish_time": ""})
            time.sleep(0.5)
        for idx, a in enumerate(articles, 1):
            if not a.get("content") and a.get("url"):
                fpath = self.current_weekly_dir / self._article_filename(a, idx)
                if not fpath.exists():
                    self.save_article(a, idx)
        index_content = self.generate_index(issue_id, date_str, articles)
        weekly_dir = self._weekly_dir_path(issue_id, date_str)
        index_file = weekly_dir / "00-index.md"
        with open(index_file, "w", encoding="utf-8") as f:
            f.write(index_content)
        logger.info("第 %s 期完成: %s，共 %s 篇", issue_id, weekly_dir, len(articles))
        return weekly_dir

    def close(self):
        self._close_driver()


def main():
    import sys
    try:
        import config
        output_dir = config.OUTPUT_DIR
    except ImportError:
        output_dir = "/Users/ice7/Documents/obsidian-doc/Infoq"
    edm_dir = SCRIPT_DIR
    crawler = InfoQWeeklyCrawler(output_dir=output_dir, edm_dir=edm_dir)
    try:
        if len(sys.argv) >= 2 and sys.argv[1].strip().isdigit():
            issue_id = sys.argv[1].strip()
            crawler.sync_issue(issue_id, force=True)
        else:
            crawler.sync_all(force=False)
    finally:
        crawler.close()


if __name__ == "__main__":
    main()
