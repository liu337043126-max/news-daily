# news-daily

每日自动抓取路透社、彭博社、华尔街日报头条新闻。

## 数据文件

- `news.json` — 结构化 JSON 数据
- `news.md` — Markdown 摘要

抓取时会把英文标题批量翻译为中文，`news.json` 的 `title` 为中文，
`title_original` 保留英文原题；飞书消息和 `news.md` 使用中文标题。
同一标题的历史译文会复用。翻译服务不可用时，本轮抓取会失败，
不会把英文标题误当中文推送。翻译使用 Google Translate 公共接口，
可能受限流或接口变更影响；译文仅供参考，具体内容以原文为准。

## 更新频率

每天北京时间 8:00 和 20:00 自动更新（GitHub Actions）。

## 飞书群推送

在目标飞书群添加「自定义机器人」，复制其 Webhook，并在仓库的
Settings → Secrets and variables → Actions 中添加 Secret `FEISHU_WEBHOOK`。
Webhook 不要写入代码或提交记录。如果机器人开启了签名校验，再添加
`FEISHU_SIGNING_SECRET`。也可将机器人安全关键词设为「财经新闻」。

工作流每次抓取后仅推送新增标题，最多展示 10 条，并附上本仓库的完整
`news.md` 链接；没有新增标题时不推送。GitHub 定时任务可能延迟运行。
