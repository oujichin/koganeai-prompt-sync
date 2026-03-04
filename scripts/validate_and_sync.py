#!/usr/bin/env python3
"""
prompt_template.json の取得・検証・同期スクリプト

検証項目:
  1. HTTPレスポンスが正常 (200)
  2. JSONとして正しくパースできる
  3. トップレベルが dict (カテゴリの辞書)
  4. 各カテゴリの値も dict (テンプレート名→プロンプト本文)
  5. プロンプト本文が空でない文字列
  6. テンプレートが1件以上存在する
  7. 前回と差分がある場合のみ更新
"""

import json
import os
import sys
import hashlib
import urllib.request
import urllib.error

SOURCE_URL = os.environ.get(
    "SOURCE_URL",
    "https://raw.githubusercontent.com/yujiuchi/gptprompt_helper/main/prompt_template.json",
)
TARGET_FILE = os.environ.get("TARGET_FILE", "prompt_template.json")
GITHUB_OUTPUT = os.environ.get("GITHUB_OUTPUT", "")


def set_output(key: str, value: str):
    """GitHub Actions の output に値をセット"""
    if GITHUB_OUTPUT:
        with open(GITHUB_OUTPUT, "a") as f:
            f.write(f"{key}={value}\n")


def write_error(msg: str):
    """エラー内容をファイルに書き出し（Issue作成用）"""
    with open("/tmp/validation_error.txt", "w") as f:
        f.write(msg)


def fetch_json(url: str) -> str:
    """URLからJSONテキストを取得"""
    try:
        if url.startswith("file://"):
            with urllib.request.urlopen(url) as resp:
                return resp.read().decode("utf-8")
        req = urllib.request.Request(url, headers={"User-Agent": "prompt-sync-bot/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            if resp.status != 200:
                raise Exception(f"HTTP {resp.status}")
            return resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        raise Exception(f"HTTP Error {e.code}: {e.reason}") from e
    except urllib.error.URLError as e:
        raise Exception(f"URL Error: {e.reason}") from e


def validate_schema(data: dict) -> list[str]:
    """
    スキーマ検証。期待する構造:
    {
      "カテゴリ名": {
        "テンプレート名": "プロンプト本文（文字列）",
        ...
      },
      ...
    }
    """
    errors = []

    if not isinstance(data, dict):
        return [f"トップレベルがdictではありません (type={type(data).__name__})"]

    if len(data) == 0:
        return ["カテゴリが0件です"]

    total_templates = 0
    for cat_name, cat_value in data.items():
        if not isinstance(cat_value, dict):
            errors.append(
                f'カテゴリ "{cat_name}" の値がdictではありません (type={type(cat_value).__name__})'
            )
            continue

        if len(cat_value) == 0:
            errors.append(f'カテゴリ "{cat_name}" にテンプレートが0件です')
            continue

        for tmpl_name, tmpl_body in cat_value.items():
            if not isinstance(tmpl_body, str):
                errors.append(
                    f'"{cat_name}" > "{tmpl_name}" の本文が文字列ではありません '
                    f"(type={type(tmpl_body).__name__})"
                )
            elif len(tmpl_body.strip()) == 0:
                errors.append(f'"{cat_name}" > "{tmpl_name}" の本文が空です')
            else:
                total_templates += 1

    if total_templates == 0 and not errors:
        errors.append("有効なテンプレートが1件もありません")

    return errors


def file_hash(path: str) -> str | None:
    """既存ファイルのハッシュを取得"""
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def main():
    print(f"📥 ソース取得: {SOURCE_URL}")

    # 1. Fetch
    try:
        raw_text = fetch_json(SOURCE_URL)
    except Exception as e:
        msg = f"取得エラー: {e}"
        print(f"❌ {msg}")
        write_error(msg)
        sys.exit(1)

    print(f"   取得成功 ({len(raw_text)} bytes)")

    # 2. JSON Parse
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as e:
        msg = f"JSONパースエラー: {e}"
        print(f"❌ {msg}")
        write_error(msg)
        sys.exit(1)

    # 3. Schema Validation
    errors = validate_schema(data)
    if errors:
        msg = "スキーマ検証エラー:\n" + "\n".join(f"  - {e}" for e in errors)
        print(f"❌ {msg}")
        write_error(msg)
        sys.exit(1)

    # Stats
    categories = len(data)
    templates = sum(len(v) for v in data.values())
    print(f"✅ 検証OK: {categories}カテゴリ, {templates}テンプレート")

    # 4. Diff Check
    # 整形済みJSONで比較（余計な差分を防ぐ）
    formatted = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    new_hash = hashlib.sha256(formatted.encode("utf-8")).hexdigest()
    old_hash = file_hash(TARGET_FILE)

    if new_hash == old_hash:
        print("⏭️  差分なし。スキップします。")
        set_output("updated", "false")
        return

    # 5. Write
    with open(TARGET_FILE, "w", encoding="utf-8") as f:
        f.write(formatted)

    print(f"📝 更新完了: {TARGET_FILE}")
    print(f"   旧ハッシュ: {old_hash or '(新規)'}")
    print(f"   新ハッシュ: {new_hash}")
    set_output("updated", "true")


if __name__ == "__main__":
    main()