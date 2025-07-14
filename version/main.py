import os, json
from dotenv import load_dotenv
from openai import OpenAI   # v1 ではクラス名が OpenAI

# ─────────────────────
# 0. 初期化
# ─────────────────────
load_dotenv()                                     # .env 読み込み
client = OpenAI(api_key=os.getenv("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"))

# ─────────────────────
# 1. マスターデータ
# ─────────────────────
AGES       = list(range(0, 11))
GENDERS    = ["おとこのこ", "おんなのこ"]
HEROES     = ["ロボット", "くるま", "魔法使い", "子ども本人"]
THEMES     = ["友情", "冒険", "挑戦", "家族", "学び"]

PROMPT_TMPL = """
あなたは幼児向け児童文学作家です。
# 条件
・対象年齢: {age}歳
・読者の性別: {gender}
・主人公: {hero}
・テーマ: {theme}
# 制約
・全5シーン構成（起→承→転→結→まとめ）
・ひらがな 80％・カタカナ 10％・漢字 10％以内
・総文字数 400〜550字
# 出力形式（JSON）
{{
  "title": "タイトル",
  "story": ["シーン1", "シーン2", "シーン3", "シーン4", "シーン5"]
}}
"""

# ─────────────────────
# 2. CLI ユーティリティ
# ─────────────────────
def choose(label: str, options: list):
    """番号で選択肢を返す簡易 CLI"""
    while True:
        print(f"\n{label}:")
        for i, opt in enumerate(options):
            print(f"  [{i}] {opt}")
        idx = input("番号を入力: ")
        if idx.isdigit() and int(idx) in range(len(options)):
            return options[int(idx)]
        print("⚠️ 無効な入力です。もう一度。")

# ─────────────────────
# 3. 本体
# ─────────────────────
def main():
    print("=== AI えほんジェネレーター (CLI MVP) ===")

    age    = choose("対象年齢", AGES)
    gender = choose("性別", GENDERS)
    hero   = choose("主人公", HEROES)
    theme  = choose("ストーリー", THEMES)

    prompt = PROMPT_TMPL.format(age=age, gender=gender, hero=hero, theme=theme)
    print("\n⏳ 生成中…\n")

    # v1 API では client.chat.completions.create(...)
    rsp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "system", "content": prompt}],
        max_tokens=450,
        temperature=0.9
    )

    result_text = rsp.choices[0].message.content

    # JSON 変換を試みる
    try:
        data = json.loads(result_text)
        print(f"📖 タイトル: {data['title']}\n")
        for i, scene in enumerate(data["story"], start=1):
            print(f"＜シーン{i}＞\n{scene}\n")
    except (json.JSONDecodeError, KeyError):
        # 期待どおりの JSON で帰らなかった時はそのまま表示
        print(result_text)

if __name__ == "__main__":
    main()
