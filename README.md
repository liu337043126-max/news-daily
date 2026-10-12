# news-daily

每日自动抓取路透社、彭博社、华尔街日报等财经新闻源的头条。

## 数据文件

- `news.json` — 结构化 JSON 数据
- `news.md` — Markdown 摘要

抓取时将英文标题译为中文：`title` 保存中文，`title_original` 保留英文原题；飞书消息和 `news.md` 同时显示中文标题与英文原题。同一标题的历史译文会复用。

优先使用 Google Translate 公共接口；接口限流或不可用时，切换到 Argos 离线模型。如果两种方式都失败，本轮不会更新新闻或推送英文标题。机器译文可能不准确，具体内容以原文为准。

## 更新频率

GitHub Actions 配置为北京时间每天 8:00 和 20:00 运行。GitHub 定时任务可能延迟。也可在 Actions 中手动运行「手动刷新中文新闻标题」，只刷新列表，不发送飞书消息。

## 飞书群推送

在目标飞书群添加「自定义机器人」，复制其 Webhook，并在仓库的 Settings → Secrets and variables → Actions 中添加 Secret `FEISHU_WEBHOOK`。Webhook 不要写入代码或提交记录。如果机器人开启签名校验，再添加 `FEISHU_SIGNING_SECRET`。

每日工作流每次抓取后仅推送新增标题，最多展示 10 条，并附上本仓库的 `news.md` 链接；没有新增标题时不推送。
