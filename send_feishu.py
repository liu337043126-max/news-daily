#!/usr/bin/env python3
"""Send a compact digest of newly fetched headlines to a Feishu group bot."""

import base64
import hashlib
import hmac
import json
import os
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo
from datetime import datetime


ROOT = Path(__file__).parent
MAX_ITEMS = 10


def article_urls(path):
    if not path.exists():
        return set()
    data = json.loads(path.read_text(encoding="utf-8"))
    return {
        article.get("url")
        for source in data.get("sources", {}).values()
        for article in source.get("articles", [])
        if article.get("url")
    }


def new_articles(data, old_urls):
    """Round-robin sources so one busy publication cannot fill the digest."""
    queues = []
    for source in data.get("sources", {}).values():
        fresh = [
            article
            for article in source.get("articles", [])
            if article.get("title") and article.get("url")
            and article["url"] not in old_urls
        ]
        queues.append((source.get("name_cn") or source.get("name") or "新闻", fresh))

    selected = []
    for index in range(MAX_ITEMS):
        added = False
        for name, articles in queues:
            if index < len(articles):
                selected.append((name, articles[index]))
                added = True
                if len(selected) == MAX_ITEMS:
                    return selected
        if not added:
            break
    return selected


def build_message(items, data):
    updated = datetime.fromisoformat(data["updated"]).astimezone(
        ZoneInfo("Asia/Shanghai")
    ).strftime("%m月%d日 %H:%M")
    lines = [f"财经新闻速递｜{updated}", f"本轮新增标题（展示前 {len(items)} 条）："]
    for number, (source, article) in enumerate(items, 1):
        lines.append(f"{number}. 【{source}】{article['title']}")
        lines.append(f"原文：{article['title_original']}")
        lines.append(article["url"])
    repo = os.getenv("GITHUB_REPOSITORY", "xiaochen00111/news-daily")
    branch = os.getenv("GITHUB_REF_NAME", "main")
    lines.append("标题为机器翻译，具体内容以原文为准。")
    lines.append(f"完整列表：https://github.com/{repo}/blob/{branch}/news.md")
    return "\n".join(lines)


def send(webhook, message, signing_secret=""):
    payload = {"msg_type": "text", "content": {"text": message}}
    if signing_secret:
        timestamp = str(int(time.time()))
        signing_key = f"{timestamp}\n{signing_secret}".encode("utf-8")
        signature = hmac.new(signing_key, b"", hashlib.sha256).digest()
        payload["timestamp"] = timestamp
        payload["sign"] = base64.b64encode(signature).decode("ascii")

    request = Request(
        webhook,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=15) as response:
            result = json.load(response)
    except HTTPError as error:
        raise SystemExit(f"飞书推送失败：HTTP {error.code}") from None
    except URLError:
        raise SystemExit("飞书推送失败：无法连接 Webhook") from None

    if result.get("code", result.get("StatusCode")) != 0:
        raise SystemExit(f"飞书推送失败：{result.get('msg', result.get('StatusMessage', '未知错误'))}")


def main():
    webhook = os.getenv("FEISHU_WEBHOOK")
    if not webhook:
        raise SystemExit("请先在 GitHub Actions Secrets 中设置 FEISHU_WEBHOOK")

    data = json.loads((ROOT / "news.json").read_text(encoding="utf-8"))
    items = new_articles(data, article_urls(ROOT / "previous-news.json"))
    if not items:
        print("没有新增标题，跳过飞书推送")
        return

    send(webhook, build_message(items, data), os.getenv("FEISHU_SIGNING_SECRET", ""))
    print(f"已向飞书推送 {len(items)} 条新增标题")


if __name__ == "__main__":
    main()
