# InfoQ 周刊爬虫配置文件示例
# 复制此文件为 config.py 并修改配置

# Obsidian 笔记输出目录
OUTPUT_DIR = "/path/to/your/obsidian/Infoq"

# 图片附件子目录名
IMAGE_DIR = "attachments"

# InfoQ 周刊列表页 URL
INFOQ_WEEKLY_URL = "https://www.infoq.cn/weekly/landing"

# 请求间隔时间（秒），避免请求过快
REQUEST_DELAY = 2

# getPaperList 每次拉取的周刊数量
WEEKLY_LIST_PAYLOAD_SIZE = 20

# 默认批量同步时，向上探测 getPaperList 的最大 size
WEEKLY_LIST_MAX_PAYLOAD_SIZE = 1000

# 每次爬取的周刊数量（默认只爬取最新一期）
DEFAULT_CRAWL_COUNT = 1

# 定时任务配置 (macOS launchd)
LAUNCHD_START_HOUR = 8      # 开始小时 (0-23)
LAUNCHD_START_MINUTE = 0    # 开始分钟 (0-59)
LAUNCHD_WEEKDAY = 1         # 星期几 (0=周日, 1=周一, ..., 6=周六)

# Selenium 配置
HEADLESS = True             # 是否使用无头模式
PAGE_LOAD_TIMEOUT = 30      # 页面加载超时时间（秒）
IMPLICIT_WAIT = 10          # 隐式等待时间（秒）

# 日志配置
LOG_LEVEL = "INFO"          # DEBUG, INFO, WARNING, ERROR
LOG_FILE = "infoq_crawler.log"
