# InfoQ 周刊自动爬虫

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)

自动抓取 [InfoQ 周刊](https://www.infoq.cn/weekly/landing) 内容，转换为 Markdown 格式并保存到 Obsidian。支持自动定时任务、图片下载、内容分析和智能去重。

## 功能特性

- 📡 **一次请求拉取多期**：请求周刊列表 API（`Referer: https://www.infoq.cn/weekly/landing`，`Content-Type: application/json`，`payload: {"size":100}`），返回约 100 期周刊，再按周处理。
- 📁 **按周建目录**：目录名为 `周刊_{周刊number}_{周刊时间转为 yyyy-mm-dd}`，每期下含 `00-index.md`、文章 md 与 `attachments/`。
- 🔍 **按篇检查是否已下载**：每期文章列表中，先查本地是否已下载（按 URL 记录）；未下载才抓取正文与图片并保存。
- 📝 转换为 Obsidian 友好 Markdown，索引用双链 `[[文件名|标题]]` 可点击跳转。
- 🧹 正文内与文末广告自动剔除。
- ⏰ 支持定时任务（macOS launchd / Linux cron）。API 无数据时可回退到本地「每周精要」HTML 或周刊页解析。

## 目录结构

```
infoq_weekly_crawler/
├── infoq_crawler.py      # 主爬虫脚本
├── config.py             # 配置文件
├── setup_scheduler.py    # 定时任务配置工具
├── tools/                # 调试/测试过程脚本
│   ├── debug_crawler.py
│   ├── analyze_page.py
│   └── check_progress.sh
├── tests/                # 测试代码与测试数据
│   ├── test_crawler.py
│   ├── test_image_order.py
│   ├── test_dom_order.py
│   ├── test_save_articles.py
│   └── data/             # 测试数据（快照/截图/分析结果等）
├── requirements.txt      # Python 依赖
├── run_crawler.sh        # Shell 包装脚本（自动生成）
├── infoq_crawler.log     # 运行日志
└── README.md             # 使用说明
```

## 快速开始

### 1. 克隆项目

```bash
git clone https://github.com/your-username/infoq-weekly-crawler.git
cd infoq-weekly-crawler
```

### 2. 安装依赖

```bash
# 创建虚拟环境（推荐）
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt
```

### 3. 配置输出目录

编辑 `config.py`，设置你的 Obsidian 目录：

```python
OUTPUT_DIR = "/Users/ice7/Documents/obsidian-doc/Infoq"
```

### 4. 手动运行

```bash
# 激活虚拟环境（如果使用）
source venv/bin/activate

# 请求 API 获取约 100 期列表，按周建目录，未下载的文章才抓取
python infoq_crawler.py

# 只同步指定期（会从本地精要 HTML 或周刊页获取文章列表）
python infoq_crawler.py 914
```

注意：你需要在 `config.py` 里填入真实的 `WEEKLY_LIST_API_URL`。为了避免请求不存在的地址，项目默认不填写该值（为空则不会发起 API 请求）。

若 API 未返回数据或你暂时不配置 API，可将「每周精要」页面另存为 HTML 到项目根目录（文件名含 `InfoQ`、`No.`、期号），程序会据此解析文章列表。

### 6. 设置定时任务

```bash
# 安装定时任务（每周一 08:00 自动执行）
python setup_scheduler.py install

# 查看状态
python setup_scheduler.py status

# 手动执行一次
python setup_scheduler.py run

# 卸载定时任务
python setup_scheduler.py uninstall
```

## 配置说明

编辑 `config.py` 可自定义以下配置：

### 路径配置

```python
# Obsidian 笔记输出目录
OUTPUT_DIR = "/Users/ice7/Documents/01.curwork/data/obsidian-rep/Infoq"

# 图片附件子目录名
IMAGE_DIR = "attachments"
```

### 定时任务配置

```python
# 每周一早上 8:00 执行
LAUNCHD_START_HOUR = 8
LAUNCHD_START_MINUTE = 0
LAUNCHD_WEEKDAY = 1  # 1=周一, 0=周日
```

### 爬虫配置

```python
# 请求间隔时间（秒），避免请求过快
REQUEST_DELAY = 2

# 每次爬取的周刊数量
DEFAULT_CRAWL_COUNT = 1
```

## 输出格式

生成的 Markdown 文件包含：

### YAML Front Matter

```yaml
---
title: "InfoQ周刊第123期"
source: InfoQ周刊
url: "https://www.infoq.cn/weekly/123"
date: 2024-01-15
created: 2024-01-15 08:00:00
tags:
  - InfoQ
  - 技术周刊
---
```

### 文章内容

- 自动生成目录
- 每篇文章标题、作者、链接
- 文章摘要和正文
- 图片使用 Obsidian 附图语法：`![[attachments/xxx.jpg|描述]]`

## 定时任务说明

### macOS (launchd)

脚本会自动创建 launchd 配置文件：
`~/Library/LaunchAgents/com.user.infoq-weekly-crawler.plist`

管理命令：
```bash
# 查看任务状态
launchctl list | grep infoq

# 手动加载
launchctl load ~/Library/LaunchAgents/com.user.infoq-weekly-crawler.plist

# 卸载
launchctl unload ~/Library/LaunchAgents/com.user.infoq-weekly-crawler.plist
```

### Linux (crontab)

手动添加 crontab 任务：
```bash
# 编辑 crontab
crontab -e

# 添加以下行（每周一 08:00）
0 8 * * 1 /Users/ice7/Documents/temp/infoq_weekly_crawler/run_crawler.sh
```

## 调试工具

如果爬虫无法正常工作，可以使用以下调试工具：

### 1. 快速测试

```bash
# 运行测试脚本
python tests/test_crawler.py
```

这会快速测试爬虫是否能找到周刊列表。

### 2. 详细调试

```bash
# 运行调试脚本（会打开浏览器窗口）
python tools/debug_crawler.py
```

调试脚本会：
- 打开浏览器窗口（非无头模式），方便观察
- 分析页面结构
- 尝试多种选择器策略
- 保存页面快照和截图
- 输出详细的调试信息

### 3. 查看页面快照

如果爬取失败，脚本会在输出目录保存 `debug_page_snapshot.html`，可以：
1. 打开该文件查看实际页面结构
2. 检查是否有 `weekly-list` 元素
3. 查看实际的链接格式

## 常见问题

### Q: 爬取失败或内容为空（返回0）？

A: 这是最常见的问题，请按以下步骤排查：

1. **运行调试工具**：
   ```bash
   python tools/debug_crawler.py
   ```

2. **检查网络连接**：
   - 确保可以访问 https://www.infoq.cn/weekly/landing
   - 检查是否需要代理

3. **检查 Chrome 浏览器**：
   - 确保已安装 Chrome 浏览器
   - 首次运行会自动下载 ChromeDriver

4. **查看日志**：
   - 查看 `infoq_crawler.log` 了解详细错误信息
   - 查看 `test_crawler.log` 了解测试结果

5. **检查页面结构**：
   - 网站可能更新了页面结构
   - 查看 `debug_page_snapshot.html` 了解实际结构
   - 如果结构变化，需要更新选择器

6. **尝试手动访问**：
   - 在浏览器中手动访问目标页面
   - 检查是否需要登录或验证
   - 检查是否有反爬虫机制

### Q: 如何修改爬取频率？

A: 编辑 `setup_scheduler.py` 中的定时配置，或直接修改 launchd plist 文件。

### Q: 图片下载失败？

A: 脚本会继续执行，失败的图片会保留原始 URL。检查网络或代理设置。

### Q: 如何重新抓取已处理的周刊？

A: 删除输出目录下的 `.processed_weekly.json` 文件，或在代码中使用 `force=True` 参数。

## 日志说明

日志文件 `infoq_crawler.log` 记录了：
- 每次运行的开始/结束时间
- 发现的周刊列表
- 下载的文章和图片
- 错误和警告信息

## 依赖说明

- **Python 3.8+**
- **Chrome 浏览器** - Selenium 需要
- **requests** - HTTP 请求
- **beautifulsoup4** - HTML 解析
- **selenium** - 动态页面抓取
- **webdriver-manager** - 自动管理 ChromeDriver

## 注意事项

1. 首次运行会自动下载 ChromeDriver
2. 爬虫使用无头模式，不会弹出浏览器窗口
3. 请遵守网站的 robots.txt 和使用条款
4. 建议合理设置抓取频率，避免对服务器造成压力

## 项目结构

```
infoq_weekly_crawler/
├── infoq_crawler.py      # 主爬虫脚本
├── config.py             # 配置文件
├── setup_scheduler.py    # 定时任务配置工具
├── tools/                # 调试/测试过程脚本
│   ├── debug_crawler.py
│   ├── analyze_page.py
│   └── check_progress.sh
├── tests/                # 测试代码与测试数据
│   ├── test_crawler.py       # 快速测试脚本
│   ├── test_image_order.py   # 图文顺序测试脚本
│   ├── test_dom_order.py     # DOM 顺序逻辑验证
│   ├── test_save_articles.py # 文章保存测试脚本
│   └── data/                 # 快照/截图/分析结果等测试数据
├── requirements.txt      # Python 依赖
├── README.md             # 使用说明
├── LICENSE               # MIT 许可证
└── .gitignore           # Git 忽略文件
```

## 输出结构

```
Infoq/
├── 周刊_909_2026-01-17/
│   ├── 00-index.md                    # 周刊索引（包含分析结果）
│   ├── 01-文章标题1.md
│   ├── 02-文章标题2.md
│   ├── ...
│   └── attachments/                   # 图片附件目录
│       ├── image1.webp
│       └── image2.png
└── .processed_weekly.json             # 已处理周刊记录
```

## 贡献指南

欢迎贡献代码！请遵循以下步骤：

1. Fork 本项目
2. 创建你的特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交你的更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启一个 Pull Request

### 代码规范

- 使用 Python 3.8+ 语法
- 遵循 PEP 8 代码风格
- 添加必要的注释和文档字符串
- 确保代码通过基本测试

## 问题反馈

如果遇到问题或有功能建议，请：

1. 查看 [常见问题](#常见问题) 部分
2. 使用调试工具排查问题
3. 在 [Issues](https://github.com/your-username/infoq-weekly-crawler/issues) 中提交问题

## 更新日志

### v1.0.0 (2026-01-25)

- ✨ 初始版本发布
- ✅ 支持自动抓取 InfoQ 周刊
- ✅ 支持图片下载和嵌入
- ✅ 支持内容分析和索引生成
- ✅ 支持定时任务配置
- ✅ 支持 macOS 和 Linux 系统

## 许可证

本项目采用 [MIT License](LICENSE) 许可证。

## 致谢

- [InfoQ](https://www.infoq.cn/) - 提供优质的技术内容
- [Selenium](https://www.selenium.dev/) - 浏览器自动化框架
- [BeautifulSoup](https://www.crummy.com/software/BeautifulSoup/) - HTML 解析库

## 免责声明

本项目仅供学习和个人使用。请遵守 InfoQ 网站的使用条款和 robots.txt 规则。使用本工具时请：

- 合理设置抓取频率，避免对服务器造成压力
- 尊重网站的反爬虫机制
- 不要用于商业用途或大规模数据采集
