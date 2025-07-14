import os, io, json, datetime, textwrap, requests
from dotenv import load_dotenv
from openai import OpenAI
from PIL import Image
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen.canvas import Canvas
from reportlab.lib.utils import ImageReader

# ─────────────────────────
# 0) 初期化
# ─────────────────────────
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

IMG_SIZE = 512            # 画像を PDF に貼るサイズ(px)
MARGIN   = 40             # 余白 (pt)

AGES    = list(range(0, 11))
GENDERS = ["おとこのこ", "おんなのこ"]
HEROES  = ["ロボット", "くるま", "魔法使い", "子ども本人"]
THEMES  = ["友情", "冒険", "挑戦", "家族", "学び"]

# ─────────────────────────
# 1) CLI 選択ユーティリティ
# ─────────────────────────
def choose(label, options):
    while True:
        print(f"\n{label}:")
        for i, opt in enumerate(options):
            print(f"  [{i}] {opt}")
        idx = input("番号を入力: ")
        if idx.isdigit() and int(idx) in range(len(options)):
            return options[int(idx)]
        print("⚠️ 無効な入力です。もう一度。")

# ─────────────────────────
# 2) ストーリー生成
# ─────────────────────────
def generate_story(age, gender, hero, theme, max_tokens=700):
    prompt = f"""
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
{{"title":"タイトル","story":["シーン1","シーン2","シーン3","シーン4","シーン5"]}}
"""
    rsp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "system", "content": prompt}],
        max_tokens=max_tokens,
        temperature=0.8,
        response_format={"type": "json_object"},
    )
    try:
        return json.loads(rsp.choices[0].message.content)
    except json.JSONDecodeError:
        # ★ 1 回だけトークン数を増やしてリトライ
        if max_tokens < 900:
            return generate_story(age, gender, hero, theme, max_tokens=max_tokens+200)
        raise                    # それでも失敗したら例外を投げる


# ─────────────────────────
# 3) 画像生成
# ─────────────────────────
def generate_image(scene):
    dalle_prompt = (
        f"Children's picture-book illustration, {scene[:80]}, "
        "colorful, whimsical, storybook style"
    )
    rsp = client.images.generate(
        model="dall-e-3",
        prompt=dalle_prompt,
        n=1,
        size="1024x1024",
    )
    url = rsp.data[0].url
    img = Image.open(requests.get(url, stream=True).raw)
    return img.resize((IMG_SIZE, IMG_SIZE), Image.LANCZOS)

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
# …（省略）…
# ↑ 既存 import に追記
# フォント登録 ── ここを 1 行にする
pdfmetrics.registerFont(TTFont("JPFont", "fonts/NotoSansJP-Bold.ttf"))



# ── ★ ここを新規追加 ─────────────────
# フォントファイルのパス（例：MS ゴシック）
FONT_PATH = "fonts/NotoSansJP-Bold.ttf"   # ★ 太字フォントを直接指定
# もし NotoSans を使うなら → FONT_PATH = "fonts/NotoSansJP-Regular.otf"

# フォント登録
pdfmetrics.registerFont(TTFont("JPFontR", "fonts/NotoSansJP-Regular.ttf"))
pdfmetrics.registerFont(TTFont("JPFontB", "fonts/NotoSansJP-Bold.ttf"))

# ────────────────────────────────

# ─────────────────────────
# 4) PDF 組版（画像の直下に本文）
# ─────────────────────────
def save_pdf(title, scenes, images, outfile):
    canvas = Canvas(outfile, pagesize=A4)
    W, H = A4

    for idx, scene in enumerate(scenes):
        img_reader = ImageReader(images[idx])
        img_y = H - IMG_SIZE - MARGIN
        canvas.drawImage(img_reader, MARGIN, img_y, IMG_SIZE, IMG_SIZE)

        # タイトル
        if idx == 0:
            canvas.setFont("JPFontB", 14)     # ← 変更
            canvas.drawString(MARGIN, img_y - 20, f"『{title}』")

        # 本文
        canvas.setFont("JPFontR", 11)        # ← 変更
        text_start_y = img_y - 40 if idx == 0 else img_y - 20
        wrapped = textwrap.fill(scene, 38)   # 行幅を少し短く
        text_obj = canvas.beginText(MARGIN, text_start_y)
        for line in wrapped.split("\n"):
            text_obj.textLine(line)
        canvas.drawText(text_obj)

        canvas.showPage()
    canvas.save()


# ─────────────────────────
# 5) メインフロー
# ─────────────────────────
def main():
    print("=== AI えほんジェネレーター (PDF) ===")

    age    = choose("対象年齢", AGES)
    gender = choose("性別", GENDERS)
    hero   = choose("主人公", HEROES)
    theme  = choose("テーマ", THEMES)

    story = generate_story(age, gender, hero, theme)
    title, scenes = story["title"], story["story"]
    print(f"\n📖 ストーリー生成完了: {title}")

    images = [generate_image(s) for s in scenes]
    print("🖼️  画像生成完了")

    os.makedirs("output", exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    pdf_path = f"output/book_{ts}.pdf"
    save_pdf(title, scenes, images, pdf_path)
    print(f"\n✅ PDF 保存 → {pdf_path}")

if __name__ == "__main__":
    main()
