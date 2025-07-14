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
load_dotenv()                                     # .env からキー読み込み
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

IMG_SIZE = 512        # PDF で貼る最終サイズ（px）

# ─────────────────────────
# 1) ストーリー生成
# ─────────────────────────
def generate_story(age, gender, hero, theme):
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
        max_tokens=450,
        temperature=0.8,
        response_format={"type": "json_object"},
    )
    return json.loads(rsp.choices[0].message.content)

# ─────────────────────────
# 2) 画像生成（DALL·E 3）
# ─────────────────────────
def generate_image(scene_text: str) -> Image.Image:
    dalle_prompt = (
        f"Children's picture-book illustration, "
        f"{scene_text[:80]}, colorful, whimsical, storybook style"
    )
    rsp = client.images.generate(
        model="dall-e-3",      # DALL·E 2 なら size を 512x512 に変えて OK
        prompt=dalle_prompt,
        n=1,
        size="1024x1024",
    )
    url = rsp.data[0].url
    img = Image.open(requests.get(url, stream=True).raw)
    return img.resize((IMG_SIZE, IMG_SIZE), Image.LANCZOS)

# ─────────────────────────
# 3) PDF 組版
# ─────────────────────────
def save_pdf(title, scenes, images, outfile):
    canvas = Canvas(outfile, pagesize=A4)
    W, H = A4
    margin = 40
    text_start_y = H - IMG_SIZE - margin * 2 - 24

    for idx, scene in enumerate(scenes):
        # 画像
        img_reader = ImageReader(images[idx])
        canvas.drawImage(
            img_reader,
            margin,
            H - IMG_SIZE - margin,
            IMG_SIZE,
            IMG_SIZE,
        )

        # テキスト
        if idx == 0:
            canvas.setFont("Helvetica-Bold", 14)
            canvas.drawString(margin, text_start_y + 24, f"『{title}』")
        canvas.setFont("Helvetica", 11)
        wrapped = textwrap.fill(scene, 50)
        text_obj = canvas.beginText(margin, text_start_y)
        for line in wrapped.split("\n"):
            text_obj.textLine(line)
        canvas.drawText(text_obj)

        canvas.showPage()

    canvas.save()

# ─────────────────────────
# 4) メイン処理（テスト用固定値）
# ─────────────────────────
if __name__ == "__main__":
    story = generate_story(age=4, gender="おんなのこ",
                           hero="子ども本人", theme="家族")
    title, scenes = story["title"], story["story"]
    print(f"📖 ストーリー生成完了: {title}")

    images = [generate_image(s) for s in scenes]
    print("🖼️  画像生成完了")

    os.makedirs("output", exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    pdf_path = f"output/book_{ts}.pdf"
    save_pdf(title, scenes, images, pdf_path)
    print(f"✅ PDF 保存 → {pdf_path}")
