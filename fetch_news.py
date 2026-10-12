#!/usr/bin/env python3
"""Fetch headlines, translate them to Chinese, and publish a daily digest."""
import feedparser
import hashlib
import json
import os
import time
from urllib.error import HTTPError
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

# ========== 新闻源配置 ==========
SOURCES = {
    "reuters": {
        "name": "Reuters",
        "name_cn": "路透社",
        "rss": "https://news.google.com/rss/search?q=site:reuters.com&hl=en-US&gl=US&ceid=US:en",
    },
    "bloomberg": {
        "name": "Bloomberg",
        "name_cn": "彭博社",
        "title_suffixes": ["Bloomberg.com"],
        "rss": "https://news.google.com/rss/search?q=site:bloomberg.com&hl=en-US&gl=US&ceid=US:en",
    },
    "wsj": {
        "name": "Wall Street Journal",
        "name_cn": "华尔街日报",
        "title_suffixes": ["WSJ", "The Wall Street Journal"],
        "rss": "https://news.google.com/rss/search?q=site:wsj.com&hl=en-US&gl=US&ceid=US:en",
    },
    "ft": {
        "name": "Financial Times",
        "name_cn": "金融时报",
        "rss": "https://news.google.com/rss/search?q=site:ft.com&hl=en-US&gl=US&ceid=US:en",
    },
    "cnbc": {
        "name": "CNBC",
        "name_cn": "CNBC",
        "rss": "https://news.google.com/rss/search?q=site:cnbc.com&hl=en-US&gl=US&ceid=US:en",
    },
    "scmp": {
        "name": "South China Morning Post",
        "name_cn": "南华早报",
        "rss": "https://news.google.com/rss/search?q=site:scmp.com&hl=en-US&gl=US&ceid=US:en",
    },
    "marketwatch": {
        "name": "MarketWatch",
        "name_cn": "MarketWatch",
        "rss": "https://news.google.com/rss/search?q=site:marketwatch.com&hl=en-US&gl=US&ceid=US:en",
    },
    "yahoofinance": {
        "name": "Yahoo Finance",
        "name_cn": "雅虎财经",
        "title_suffixes": ["Yahoo Finance Australia"],
        "rss": "https://news.google.com/rss/search?q=site:finance.yahoo.com&hl=en-US&gl=US&ceid=US:en",
    },
}

OUTPUT_DIR = Path(__file__).parent
MAX_ARTICLES = 15  # 每个源最多取多少条
TRANSLATE_BATCH_SIZE = 10
ARGOS_MODEL_URL = "https://argos-net.com/v1/translate-en_zh-1_9.argosmodel"
ARGOS_MODEL_SHA256 = "433e7c4f034d87fbe2353161e05f18646d7999452f801a4e1f0378522b9850ab"
REMOTE_TRANSLATION_AVAILABLE = True


def clean_title(title, source_name, extra_suffixes=()):
    """Remove Google News' publisher suffix without cutting a headline's own dash."""
    title = " ".join(title.split())
    for publisher in (source_name, *extra_suffixes):
        suffix = f" - {publisher}"
        if title.endswith(suffix):
            return title[:-len(suffix)].strip()
    return title


def translation_cache(path):
    """Reuse translations from the last successful run."""
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {
        article["title_original"]: article["title"]
        for source in data.get("sources", {}).values()
        for article in source.get("articles", [])
        if article.get("title_original") and article.get("title")
    }

def translate_offline(titles):
    """Use a pinned English-to-Chinese model when the public API is rate-limited."""
    import argostranslate.package
    import argostranslate.translate

    languages = argostranslate.translate.get_installed_languages()
    english = next((lang for lang in languages if lang.code == "en"), None)
    chinese = next((lang for lang in languages if lang.code == "zh"), None)
    if english is None or chinese is None or english.get_translation(chinese) is None:
        model_path = Path.home() / ".cache" / "news-daily" / "translate-en_zh-1_9.argosmodel"
        model_path.parent.mkdir(parents=True, exist_ok=True)
        if not model_path.exists() or hashlib.sha256(model_path.read_bytes()).hexdigest() != ARGOS_MODEL_SHA256:
            request = Request(ARGOS_MODEL_URL, headers={"User-Agent": "news-daily/1.0"})
            temporary_path = model_path.with_suffix(".download")
            digest = hashlib.sha256()
            try:
                with urlopen(request, timeout=90) as response, open(temporary_path, "wb") as output:
                    while chunk := response.read(1024 * 1024):
                        output.write(chunk)
                        digest.update(chunk)
                if digest.hexdigest() != ARGOS_MODEL_SHA256:
                    raise RuntimeError("离线翻译模型校验失败")
                os.replace(temporary_path, model_path)
            finally:
                temporary_path.unlink(missing_ok=True)
        argostranslate.package.install_from_path(model_path)

    translated = [argostranslate.translate.translate(title, "en", "zh").strip() for title in titles]
    if not all(translated):
        raise RuntimeError("离线翻译返回空标题；未发布英文标题")
    return translated


def translate_batch(titles):
    """Prefer the public API, falling back to a local model when unavailable."""
    global REMOTE_TRANSLATION_AVAILABLE
    if not REMOTE_TRANSLATION_AVAILABLE:
        return translate_offline(titles)
    query = urlencode({
        "client": "gtx", "sl": "auto", "tl": "zh-CN", "dt": "t",
        "q": "\n".join(titles),
    })
    request = Request(
        f"https://translate.googleapis.com/translate_a/single?{query}",
        headers={"User-Agent": "news-daily/1.0"},
    )
    last_error = None
    for attempt in range(3):
        try:
            with urlopen(request, timeout=20) as response:
                segments = json.load(response)[0]
            translated = "".join(segment[0] for segment in segments).splitlines()
            translated = [title.strip() for title in translated]
            if len(translated) != len(titles) or not all(translated):
                raise ValueError("translation count does not match headline count")
            return translated
        except (OSError, ValueError, KeyError, IndexError, TypeError) as error:
            last_error = error
            if isinstance(error, HTTPError) and error.code == 429:
                break
            if attempt == 2:
                break
            time.sleep(2 ** attempt)
    REMOTE_TRANSLATION_AVAILABLE = False
    print(f"  在线翻译不可用（{last_error}），改用离线模型")
    return translate_offline(titles)


def translate_articles(all_data, cache):
    reused = sum(
        article["title_original"] in cache
        for articles in all_data.values()
        for article in articles
    )
    pending = list(dict.fromkeys(
        article["title_original"]
        for articles in all_data.values()
        for article in articles
        if article["title_original"] and article["title_original"] not in cache
    ))
    for start in range(0, len(pending), TRANSLATE_BATCH_SIZE):
        titles = pending[start:start + TRANSLATE_BATCH_SIZE]
        cache.update(zip(titles, translate_batch(titles)))
    for articles in all_data.values():
        for article in articles:
            article["title"] = cache.get(article["title_original"], "")
    print(f"  已翻译 {len(pending)} 个新标题，复用 {reused} 条历史译文")


def fetch_source(key, config):
    """抓取单个新闻源"""
    print(f"  正在抓取 {config['name_cn']} ({config['name']})...")
    try:
        feed = feedparser.parse(config["rss"])
        articles = []
        for entry in feed.entries[:MAX_ARTICLES]:
            original = clean_title(
                entry.get("title", ""), config["name"], config.get("title_suffixes", ())
            )
            articles.append({
                "title_original": original,
                "url": entry.get("link", ""),
                "published": entry.get("published", ""),
                "summary": entry.get("summary", ""),
            })
        print(f"  ✅ {config['name_cn']}: 获取到 {len(articles)} 篇文章")
        return articles
    except Exception as e:
        print(f"  ❌ {config['name_cn']}: 抓取失败 - {e}")
        return []


def generate_markdown(all_data):
    """生成可读的 Markdown 摘要"""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        f"# 📰 每日财经新闻摘要",
        f"**更新时间：{now}**",
        "",
        "> 来源：路透社 (Reuters) · 彭博社 (Bloomberg) · 华尔街日报 (WSJ)",
        "> 标题为机器翻译，具体内容以原文为准。",
        "",
        "---",
        "",
    ]

    emoji_map = {"reuters": "🔴", "bloomberg": "🟢", "wsj": "🔵", "ft": "🟡", "cnbc": "🟠", "scmp": "🟣", "marketwatch": "🟤", "yahoofinance": "⚪"}

    for key, articles in all_data.items():
        cfg = SOURCES[key]
        emoji = emoji_map.get(key, "📌")
        lines.append(f"## {emoji} {cfg['name_cn']} ({cfg['name']})")
        lines.append("")
        if not articles:
            lines.append("> ⚠️ 本次未获取到文章")
            lines.append("")
            continue
        for i, a in enumerate(articles, 1):
            title = a["title"].strip()
            url = a["url"]
            lines.append(f"{i}. [{title}]({url})")
        lines.append("")

    lines.append("---")
    lines.append(f"*自动生成于 {now}*")
    return "\n".join(lines)


def main():
    print(f"🚀 开始抓取新闻... ({datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')})")
    print()

    all_data = {}
    for key, config in SOURCES.items():
        articles = fetch_source(key, config)
        all_data[key] = articles

    translate_articles(all_data, translation_cache(OUTPUT_DIR / "news.json"))

    # 保存 JSON
    json_path = OUTPUT_DIR / "news.json"
    json_data = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "sources": {
            key: {
                "name": SOURCES[key]["name"],
                "name_cn": SOURCES[key]["name_cn"],
                "count": len(all_data[key]),
                "articles": all_data[key],
            }
            for key in SOURCES
        },
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(json_data, f, ensure_ascii=False, indent=2)

    # 保存 Markdown
    md_path = OUTPUT_DIR / "news.md"
    md_content = generate_markdown(all_data)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    # 统计
    total = sum(len(v) for v in all_data.values())
    print(f"\n✅ 完成！共获取 {total} 篇文章")
    print(f"   JSON: {json_path}")
    print(f"   Markdown: {md_path}")


if __name__ == "__main__":
    main()
