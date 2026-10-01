"""言蹊翻译 命令行工具 (CLI Prototype)

提供终端直接翻译、Provider 切换、API 密钥设置及连通性测试。
"""

from __future__ import annotations
import argparse
import sys
from yanche.core.config import AppConfig
from yanche.core.models import TranslationRequest
from yanche.core.translator.factory import create_translator
from yanche.core.cache.sqlite_cache import SQLiteCache


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="yanche-cli",
        description="言蹊翻译 极简划词翻译核心终端工具",
    )
    parser.add_argument("text", nargs="?", help="待翻译文本")
    parser.add_argument("-s", "--source", default=None, help="源语言代码（默认: auto）")
    parser.add_argument("-t", "--target", default=None, help="目标语言代码（默认: zh-CN）")
    parser.add_argument("-p", "--provider", default=None, help="指定翻译服务提供商 (如 deepseek, openai, zhipu)")
    parser.add_argument("--test", action="store_true", help="测试当前提供商网络与 API 连通性")
    parser.add_argument("--list-providers", action="store_true", help="列出所有配置的翻译服务")
    parser.add_argument("--set-key", nargs=2, metavar=("PROVIDER", "KEY"), help="设置指定 Provider 的 API 密钥")
    parser.add_argument("-i", "--interactive", action="store_true", help="进入终端交互式翻译模式")
    return parser.parse_args()


def do_translate(text: str, config: AppConfig, cache: SQLiteCache, source: str, target: str, provider_name: str) -> None:
    provider_cfg = config.providers.get(provider_name)
    if not provider_cfg:
        print(f"❌ 找不到提供商配置: {provider_name}")
        return

    # 1. 尝试缓存
    if config.enable_cache:
        cached = cache.get(text, source, target, provider_name)
        if cached:
            print(f"\n⚡ [Cache] ({cached.source_lang} -> {cached.target_lang})")
            print(f"👉 {cached.translated_text}\n")
            return

    # 2. 调用 API
    translator = create_translator(provider_cfg)
    req = TranslationRequest(text=text, source_lang=source, target_lang=target)
    print(f"⏳ 正在通过 [{provider_name}] 请求翻译...", end="\r", flush=True)
    res = translator.translate(req)

    if res.is_success():
        print(f"\n✅ [{res.provider} | {res.latency_ms}ms] ({res.source_lang} -> {res.target_lang})")
        print(f"👉 {res.translated_text}\n")
        if config.enable_cache:
            cache.put(res)
    else:
        print(f"\n❌ 翻译失败 [{res.provider}]: {res.translated_text}\n")


def main() -> None:
    args = parse_args()
    config = AppConfig.load()
    cache = SQLiteCache()

    # 处理参数 --set-key
    if args.set_key:
        p_name, key = args.set_key
        if p_name in config.providers:
            config.providers[p_name].api_key = key
            config.save()
            print(f"✅ 已成功更新 [{p_name}] 的 API 密钥")
        else:
            print(f"❌ 提供商 [{p_name}] 不存在，可用提供商: {list(config.providers.keys())}")
        return

    # 处理参数 --list-providers
    if args.list_providers:
        print("\n=== 可用的翻译服务提供商 ===")
        for name, p in config.providers.items():
            mark = "★ (默认)" if name == config.default_provider else " "
            if p.provider_type == "microsoft" and not p.api_key:
                has_key = "✔ 免配置 (网页)"
            else:
                has_key = "✔ 已配置 Key" if p.api_key else "✖ 未配置 Key"
            print(f"{mark} {name:<12} | 模型: {p.model:<16} | {has_key} | {p.base_url}")
        print()
        return

    # 确定当前 provider 与语言
    active_provider = args.provider or config.default_provider
    source_lang = args.source or config.default_source_lang
    target_lang = args.target or config.default_target_lang

    # 处理 --test 连通性测试
    if args.test:
        provider_cfg = config.providers.get(active_provider)
        if not provider_cfg:
            print(f"❌ 提供商 [{active_provider}] 未配置")
            sys.exit(1)
        print(f"🔍 正在测试 [{active_provider}] ({provider_cfg.model}) 连通性...")
        translator = create_translator(provider_cfg)
        ok, msg = translator.test_connection()
        if ok:
            print(f"✅ {msg}")
        else:
            print(f"❌ 测试失败: {msg}")
        return

    # 交互模式
    if args.interactive:
        print(f"=== 言蹊翻译 交互模式 (Provider: {active_provider}) ===")
        print("输入待翻译内容后回车，按 Ctrl+C 或输入 'exit' 退出：\n")
        try:
            while True:
                user_input = input(">> ").strip()
                if not user_input:
                    continue
                if user_input.lower() in ("exit", "quit"):
                    break
                do_translate(user_input, config, cache, source_lang, target_lang, active_provider)
        except (KeyboardInterrupt, EOFError):
            print("\n👋 已退出交互模式")
        return

    # 单次翻译
    if args.text:
        do_translate(args.text, config, cache, source_lang, target_lang, active_provider)
    else:
        print("提示: 请输入待翻译的文本，或运行 `yanche-cli --help` 查看帮助。")


if __name__ == "__main__":
    main()
