# app.py — あなただけのえほんジェネレーター（Flask 単体）
# ============================================================
from flask import Flask, render_template_string, request, jsonify, send_file
import os, json, textwrap, datetime, traceback, sys, random, requests
from dotenv import load_dotenv
from openai import OpenAI
from PIL import Image
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen.canvas import Canvas
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# ===== 共通プロンプト（日本人向け・文字なし・統一主人公） =====
PROMPT_BASE = (
    "Soft watercolor children’s picture-book illustration, "
    "kawaii Japanese style, gentle pastel colors, "
    "no text, no captions, consistent protagonist, "
)

# ===== OpenAI 初期化 =========================================
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ===== ReportLab フォント設定 =================================
pdfmetrics.registerFont(TTFont("JPFont", "fonts/NotoSansJP-Bold.ttf"))
IMG_SIZE, MARGIN = 512, 40

app = Flask(__name__)

# -------------------------------------------------------------
# 画像生成ラッパー
# -------------------------------------------------------------

def dall_e(prompt: str) -> str:
    """DALL·E 3 で挿絵を生成し URL を返す"""
    rsp = client.images.generate(
        model="dall-e-3",
        prompt=PROMPT_BASE + prompt,
        n=1,
        size="1024x1024"
    )
    return rsp.data[0].url

# -------------------------------------------------------------
# 主人公ビジュアル記述を GPT で生成（1 回）
# -------------------------------------------------------------

def get_hero_desc(hero: str) -> str:
    """主人公キーワードを5〜10語のひらがなで視覚描写"""
    rsp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "あなたはイラストレーターです。ユーザーが入力した主人公を、5〜10語のひらがなだけで視覚描写してください。句読点は使わず"},
            {"role": "user", "content": hero}
        ],
        max_tokens=30,
        temperature=0.7
    )
    return rsp.choices[0].message.content.strip()

# -------------------------------------------------------------
# ストーリー生成用プロンプト
# -------------------------------------------------------------

def story_prompt(age: str, gender: str, hero: str, theme: str) -> str:
    return (
        "あなたはようじむけのさっかです。すべてひらがなでかいてください。\n"
        f"・たいしょうねんれい:{age}さい ・せいべつ:{gender} ・しゅじんこう:{hero} ・てーま:{theme}\n"
        "・ぜん3しーんこうせい(き→しょう→けつ)・もじすう300から400じ\n"
        "JSON={\"title\":\"たいとる\",\"story\":[\"しーん1\",\"しーん2\",\"しーん3\"]}"
    )

# -------------------------------------------------------------
# PDF 作成
# -------------------------------------------------------------

def generate_pdf(data: dict, hero_desc: str) -> str:
    title, scenes = data["title"], data["story"]
    filename = f"book_{datetime.datetime.now():%Y%m%d_%H%M%S}.pdf"
    path = f"/tmp/{filename}"

    c = Canvas(path, pagesize=A4)
    W, H = A4

    for idx, scene in enumerate(scenes[:3]):
        url = dall_e(hero_desc + ", " + scene[:60])
        with Image.open(requests.get(url, stream=True).raw) as img:
            img = img.resize((IMG_SIZE, IMG_SIZE), Image.LANCZOS)
            c.drawImage(ImageReader(img), MARGIN, H-IMG_SIZE-MARGIN, IMG_SIZE, IMG_SIZE)

        if idx == 0:
            c.setFont("JPFont", 14)
            c.drawString(MARGIN, H-IMG_SIZE-MARGIN-20, f"『{title}』")

        c.setFont("JPFont", 11)
        t = c.beginText(MARGIN, H-IMG_SIZE-MARGIN-40)
        t.textLines(textwrap.fill(scene, 38))
        c.drawText(t)
        c.showPage()

    c.save()
    return filename

# ===== HTML & JS 省略（変化なし） =====
#   ※ ここに前回の HTML テンプレートをそのまま貼り付けてください
HTML = """<!! ここに前回の HTML を貼る !!>"""

# ===== ルーティング ============================================
@app.route('/')
def index():
    return render_template_string(HTML)

@app.route('/api/book', methods=['POST'])
def api_book():
    try:
        f = request.form
        hero_desc = get_hero_desc(f['hero'])
        story_rsp = client.chat.completions.create(
            model='gpt-4o-mini',
            messages=[{"role": "system", "content": story_prompt(f['age'], f['gender'], f['hero'], f['theme'])}],
            max_tokens=700,
            response_format={"type": "json_object"}
        )
        story_json = json.loads(story_rsp.choices[0].message.content)

        pages = [{
            "img": dall_e(hero_desc + ", " + sc[:60]),
            "text": sc
        } for sc in story_json["story"][:3]]

        return jsonify({"pages": pages})
    except Exception as e:
        traceback.print_exc(file=sys.stderr)
        return jsonify({"error": str(e)}), 500

@app.route('/api/generate', methods=['POST'])
def api_generate():
    try:
        f = request.form
        hero_desc = get_hero_desc(f['hero'])
        story_rsp = client.chat.completions.create(
            model='gpt-4o-mini',
            messages=[{"role": "system", "content": story_prompt(f['age'], f['gender'], f['hero'], f['theme'])}],
            max_tokens=700,
            response_format={"type": "json_object"}
        )
        story_json = json.loads(story_rsp.choices[0].message.content)
        pdfname = generate_pdf(story_json, hero_desc)
        return jsonify({"file": pdfname})
    except Exception as e:
        traceback.print_exc(file=sys.stderr)
        return jsonify({"error": str(e)}), 500

@app.route('/pdf/<name>')
def download(name):
    return send_file(f"/tmp/{name}", as_attachment=True)

if __name__ == '__main__':
    port = int(os.getenv('PORT', 8000))
    app.run(host='0.0.0.0', port=port)
