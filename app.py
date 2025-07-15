
import os, random, sys, json, traceback
from flask import Flask, request, jsonify
from dotenv import load_dotenv
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.utils import ImageReader
from PIL import Image
import openai
import requests

load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")
client = openai

app = Flask(__name__)

font_path = "fonts/NotoSansJP-Bold.ttf"
pdfmetrics.registerFont(TTFont("JPFont", font_path))

def story_prompt(age, gender, hero, theme):
    return f"""
あなたは日本の子ども向け絵本作家です。
読者は{age}の{gender}です。
主人公は「{hero}」で、テーマは「{theme}」です。
すべての漢字には必ずふりがなをつけてください。
句点「。」ごとに区切って、1文ずつの配列JSONで返してください。
文章はやさしいひらがなで、心温まる結末にしてください。
"""

def dall_e(prompt):
    res = client.images.generate(
        model="dall-e-3",
        prompt=prompt + " 日本人の子ども向け、かわいい絵本のイラスト。文字なし。",
        size="1024x1024",
        quality="standard",
        n=1,
        response_format="url"
    )
    return res.data[0].url

def generate_pdf(story, hero_tag=""):
    from datetime import datetime
    filename = f"output/book_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    os.makedirs("output", exist_ok=True)
    c = canvas.Canvas(filename, pagesize=A4)
    width, height = A4

    for i, page in enumerate(story):
        try:
            url = dall_e(page[:60] + " " + hero_tag)
            img_data = requests.get(url).content
            img_path = f"output/temp_img_{i}.png"
            with open(img_path, "wb") as f:
                f.write(img_data)

            img = Image.open(img_path)
            img_width = width * 0.8
            aspect = img.height / img.width
            img_height = img_width * aspect
            c.drawImage(ImageReader(img_path), (width - img_width) / 2, height - img_height - 60, width=img_width, height=img_height)
            img.close()

            text_y = height - img_height - 80
            c.setFont("JPFont", 20)
            for line in page.split("。"):
                c.drawString(50, text_y, line.strip() + "。")
                text_y -= 24
        except Exception as e:
            traceback.print_exc()
            c.setFont("JPFont", 14)
            c.drawString(50, 500, f"エラーが発生しました: {str(e)}")

        c.showPage()

    c.save()
    return filename

@app.route("/")
def index():
    return """
<html>
  <head><title>あなただけのえほん</title></head>
  <body style="background-color:#fff0f5; font-family:sans-serif; text-align:center;">
    <h2 style="color:#d63384;">あなただけのえほん</h2>
    <form action="/api/book" method="POST">
      <label>なんさい？ <input name="age" /></label><br/><br/>
      <label>おとこのこ？おんなのこ？
        <select name="gender"><option>おとこのこ</option><option>おんなのこ</option></select>
      </label><br/><br/>
      <label>しゅじんこうは？
        <select name="hero"><option>ロボット</option><option>くるま</option><option>まほうつかい</option><option>じぶん</option></select>
      </label><br/><br/>
      <label>テーマは？
        <select name="theme"><option>ゆうじょう</option><option>ぼうけん</option><option>ちょうせん</option><option>かぞく</option><option>まなび</option></select>
      </label><br/><br/>
      <button type="submit">えほんをつくる</button>
    </form>
  </body>
</html>
"""

@app.route("/api/book", methods=["POST"])
def api_book():
    try:
        f = request.form
        prompt = story_prompt(f["age"], f["gender"], f["hero"], f["theme"])
        rsp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role":"system","content": prompt}],
            max_tokens=700,
            temperature=0.9,
            response_format={"type":"json_object"}
        )
        story = json.loads(rsp.choices[0].message.content)["ストーリー"]
        pdf = generate_pdf(story, f["hero"])
        return jsonify({"file": pdf})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
