## InfoQ 每周精要爬虫设计文档

本文档描述当前 `infoq_weekly_crawler` 的整体设计与核心抓取流程，重点围绕你重新整理并确认过的「每周精要」抓取逻辑。

---

### 总体目标

- **期号发现**：自动识别目前在 InfoQ「每周精要」中已经发布的各期周刊（如 914、913、912、910、909 等）。
- **列表来源唯一**：每期文章列表**只**来自官方的「每周精要」 EDM 页（或等价的 HTML），不再从 `/weekly/{id}` 的推荐流中“猜”文章。
- **按周建目录**：每期输出一个独立目录，命名为：
  - `周刊_{周刊number}_{周刊time时间戳转换为 yyyy-mm-dd}`
- **按篇去重抓取**：同一期/跨期同一篇文章按 URL 维度去重，已经抓取过的文章再次运行时不再重复抓取。
- **Obsidian 友好**：输出 Markdown 及附件布局适配 Obsidian，索引使用双链语法，正文内嵌附图。

---

### 一、期号与精要 HTML 的获取（getPaperList）

- **接口地址**：`https://www.infoq.cn/public/v1/misc/getPaperList`
- **请求方式**：
  - Method: `POST`
  - Headers:
    - `Referer: https://www.infoq.cn/weekly/landing`
    - `Content-Type: application/json`
  - Payload：
    - `{"size": 100}`（一次请求返回最近约 100 期周刊）

- **响应结构（示例）**：

  ```json
  {
    "code": 0,
    "data": [
      {
        "number": 914,
        "time": 1772812800,
        "url": "https://static001.geekbang.org/edm/...914.html"
      },
      {
        "number": 913,
        "time": 1770998400,
        "url": "https://static001.geekbang.org/edm/...913.html"
      },
      ...
    ],
    "error": {},
    "extra": {
      "cost": 0.0009,
      "request-id": "..."
    }
  }
  ```

- **规范化后内部使用的数据结构**：
  - 对 `data` 数组中的每项，转换为：
    - **`id`**：`str(number)`，作为周刊期号（如 `"914"`）
    - **`date`**：由 `time`（秒级时间戳）转换为 `yyyy-MM-dd`
    - **`edm_url`**：`url` 字段（如果不是 http 开头，补全为绝对链接）
    - **`articles`**：`None`（文章列表后续再通过 EDM HTML 解析）

- **作用**：
  - 这是整个爬虫的**唯一期号来源**，保证后续处理的都是 InfoQ 官方承认的「每周精要」期次。

---

### 二、按周建目录的规则

对从 `getPaperList` 得到的每一期（例如 `number = 914, time = 1772812800`）：

- 计算日期：
  - `date = datetime.fromtimestamp(time).strftime("%Y-%m-%d")`
- 构造周刊目录名：
  - `周刊_{number}_{date}`  
  - 示例：`周刊_914_2026-03-12`
- 目录结构（以 914 为例）：
  - `周刊_914_2026-03-12/`
    - `00-index.md`（本期索引，含分析与文章列表）
    - `01-xxx.md`、`02-xxx.md`、…（每篇文章一个 md）
    - `attachments/`（所有该期文章的图片附件）

---

### 三、每期文章列表的来源（严格按「每周精要」）

对于每一期（如 914、913、912 ...），文章列表只来自**对应的 EDM HTML**，具体流程：

- **1）获取精要 HTML**（函数逻辑概念化）：
  - 优先使用 `getPaperList` 返回的 `edm_url` 在线请求：
    - `GET edm_url`，得到整份「每周精要」 EDM 页 HTML。
  - 如果请求失败，再 **可选地** 回退到本地 HTML 快照（如 `InfoQ 每周精要 No.914 (...).html`）。

- **2）从 EDM HTML 中解析文章链接**：
  - 使用 `BeautifulSoup` 解析，遍历所有 `<a href="...">`。
  - 只保留满足以下条件的链接：
    - `href` 中包含：
      - `infoq.cn/article/` 或
      - `xie.infoq.cn/article/` 或
      - `infoq.cn/news/`
    - 且不包含：
      - `/video/`、`/theme/`、`/minibook/`、`space/` 等与文章无关的路径。
  - 取链接文本作为标题（裁剪为合理长度），要求长度大于 2–3 个字符。
  - 将相对路径统一转换为绝对 URL。
  - 对 URL 去重（同一 URL 只保留一条）。

- **3）得到每期的文章列表**：

```python
[
  {"url": "https://www.infoq.cn/article/xxxx", "title": "文章标题1"},
  {"url": "https://www.infoq.cn/article/yyyy", "title": "文章标题2"},
  ...
]
```

> 注意：**不再**从 `/weekly/{id}` 页面（推荐流）中“猜”文章列表，避免与官方「每周精要」不一致。

---

### 四、按 URL 维度去重的策略

- 使用 `output_dir/.processed_articles.json` 记录已抓取文章的 URL：

```json
{
  "914": [
    "https://www.infoq.cn/article/HHm10aPdwzZxiF9k05fN",
    "https://www.infoq.cn/article/2w3JgQftwv3PaM9hHS95",
    ...
  ],
  "913": [
    ...
  ]
}
```

- 在抓取每一期之前：
  - 将该期的 `issue_id`（如 `"914"`）对应的 URL 集合载入到内存中。
  - 对 EDM 解析出的文章列表逐条检查：
    - 如果 URL 已在对应期号的集合中，认为**已抓取过**，这次直接跳过正文抓取，只在索引中做占位。
    - 如果 URL 未出现过，才使用 Selenium 访问详情页并保存内容。
- 每成功抓取一篇新文章：
  - 将其 URL 加入内存集合，并及时回写 `.processed_articles.json`，从而支持**增量与断点续跑**。

---

### 五、文章详情抓取与内容清洗

#### 1. 详情页抓取

- 使用 Selenium + Chrome（headless）访问文章详情页 URL。
- 等待主要内容区加载完成（优先等待 `article-content-layout`、`article-main` 等容器）。
- 使用 `BeautifulSoup` 基于实际 DOM 结构定位正文内容区域。

#### 2. 广告与无关内容清洗

- 在正文区域内：
  - 移除 class 或文本中包含广告/推荐等关键词的块级元素，如：
    - class 关键词：`ad`, `ads`, `advertisement`, `promo`, `推荐阅读`, `你可能还喜欢` 等。
    - 文本关键词：`广告`, `推广`, `扫码关注`, `训练营`, `课程`, `点击领取` 等。
  - 删除导航、分享、评论等与正文无关的区域。
- 末尾裁剪：
  - 从段落列表末尾向前检查，遇到「短、且包含广告关键词」的行连续裁掉，直到遇到正常正文内容为止。

#### 3. 图文顺序与图片下载

- 遍历正文 DOM，保持原始图文顺序：
  - 遇到 `<img>`：
    - 下载到当前期目录的 `attachments/` 下；
    - 在正文中插入 `![[attachments/xxx.png|alt]]`。
  - 遇到段落/标题/代码块/列表：
    - 提取纯文本或包裹在 markdown 语法中（如代码块）。
- 最终正文为一串段落 + 内嵌图片标记的 Markdown 文本。

---

### 六、文件命名与索引生成

#### 1. 文章文件命名

- 文件名规则：

```text
{序号两位}-{标题裁剪清洗}.md
例如：01-独立开发者仅用 500 行代码做出安全版 OpenClaw.md
```

- 标题清洗：
  - 去掉文件系统不允许的字符：`<>:"/\|?*`
  - 截断到合理长度（如 50 字符以内）
  - 去掉首尾空白；若标题为空则退回 `文章{序号}`。

#### 2. 索引文件 `00-index.md`

- 包含：
  - YAML Front Matter（标题、来源 URL、日期、标签等）。
  - 本期概览：日期、文章数量。
  - 文章列表：

```markdown
1. [[01-独立开发者仅用 500 行代码做出安全版 OpenClaw.md|独立开发者仅用 500 行代码做出安全版 OpenClaw]]
   - 作者: ...
   - [原文链接](https://www.infoq.cn/article/...)
```

- 文章列表中的链接采用 **Obsidian 双链语法** `[[文件名|标题]]`，保证在 Obsidian 中一键跳转到对应文章。

---

### 七、运行方式与增量抓取

- **单期抓取**：

```bash
python infoq_crawler.py 914
```

  - 通过 `getPaperList` 得到 914 的 EDM 链接和时间；
  - 解析「每周精要」HTML 得到 19 篇文章；
  - 对其中 URL 未抓取过的文章进行详情抓取与保存；
  - 生成或更新 `周刊_914_yyyy-mm-dd` 目录。

- **批量/全量抓取**：

```bash
python infoq_crawler.py
```

  - 通过 `getPaperList` 一次获取最近约 100 期；
  - 按期号排序后，从新到旧依次处理；
  - 每期都按「文章 URL 是否已抓取」进行增量抓取。

- **断点续跑**：
  - 即使中途中断（例如网络或手动 Ctrl+C），已经成功保存的文章 URL 会记录在 `.processed_articles.json`；下次运行会自动从剩余文章继续。

---

### 八、设计原则小结

- **列表权威性**：期号和文章列表只信任两个地方：
  - `getPaperList` 返回的期号与精要 EDM URL；
  - 必要时，你手动保存的本地「每周精要 No.xxx.html」。
- **输出结构清晰**：按期 + 按文章拆分目录与文件，方便在 Obsidian 中导航、整理与检索。
- **高容错与可维护性**：
  - 所有网络请求与 HTML 解析都做了异常捕获和日志记录；
  - 将「发现期号」「解析精要 HTML」「抓取详情」「生成索引」分段实现，后续如需微调其中一段逻辑（例如调整过滤规则或增加字段）不会影响其他部分。

