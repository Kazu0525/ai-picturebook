# app.py — あなただけのえほんジェネレーター（単体 Flask アプリ）
# -------------------------------------------------------------
from flask import Flask, render_template_string, request, jsonify, send_file
import os, json, textwrap, datetime, random, traceback, sys, requests
from dotenv import load_dotenv
from openai import OpenAI
from PIL import Image
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen.canvas import Canvas
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# ====== 共通プロンプト（日本人が好む・文字なし・主人公統一） ======
PROMPT_BASE = (
    "Soft watercolor children’s picture-book illustration, "
    "kawaii Japanese style, gentle pastel colors, "
    "no text, no captions, consistent protagonist, "
)

# ====== OpenAI 初期化 =================================================
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ====== ReportLab 日本語フォント設定 =================================
pdfmetrics.registerFont(TTFont("JPFont", "fonts/NotoSansJP-Bold.ttf"))
IMG_SIZE, MARGIN = 512, 40  # 画像サイズ & 余白

app = Flask(__name__)

# ====== 画像生成ラッパー（seed 未サポート版） =======================

def dall_e(prompt: str) -> str:
    """DALL·E 3 で挿絵を生成し URL を返す"""
    rsp = client.images.generate(
        model="dall-e-3",
        prompt=PROMPT_BASE + prompt,
        n=1,
        size="1024x1024",
    )
    return rsp.data[0].url

# ====== GPT へのプロンプト作成 =======================================

def story_prompt(age: str, gender: str, hero: str, theme: str) -> str:
    return f"""
あなたは幼児向け児童文学作家です。
・対象年齢:{age}さい ・読者の性別:{gender} ・主人公:{hero} ・テーマ:{theme}
・全3シーン構成(起→承→結)・総文字数300〜400字
JSON={{"title":"タイトル","story":["シーン1","シーン2","シーン3"]}}
"""

# ====== PDF 作成 ======================================================

def generate_pdf(data: dict, hero_tag: str) -> str:
    """ストーリー JSON + 主人公タグ → 挿絵付き PDF を /tmp に保存してファイル名を返す"""

    title, scenes = data["title"], data["story"]
    filename = f"book_{datetime.datetime.now():%Y%m%d_%H%M%S}.pdf"
    path = f"/tmp/{filename}"

    canvas = Canvas(path, pagesize=A4)
    W, H = A4

    for idx, scene in enumerate(scenes[:3]):  # 3 ページ
        url = dall_e(hero_tag + ", " + scene[:60])
        with Image.open(requests.get(url, stream=True).raw) as img:
            img = img.resize((IMG_SIZE, IMG_SIZE), Image.LANCZOS)
            canvas.drawImage(ImageReader(img), MARGIN, H - IMG_SIZE - MARGIN, IMG_SIZE, IMG_SIZE)

        if idx == 0:
            canvas.setFont("JPFont", 14)
            canvas.drawString(MARGIN, H - IMG_SIZE - MARGIN - 20, f"『{title}』")

        canvas.setFont("JPFont", 11)
        t = canvas.beginText(MARGIN, H - IMG_SIZE - MARGIN - 40)
        t.textLines(textwrap.fill(scene, 38))
        canvas.drawText(t)
        canvas.showPage()

    canvas.save()
    return filename

# ====== HTML テンプレート ============================================
HTML = """
<!doctype html><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>あなただけのえほん</title>
<style>
:root{font-size:18px}@media(min-width:600px){:root{font-size:16px}}
body{font-family:sans-serif;max-width:460px;margin:2rem auto;padding:0 1rem}
label{display:block;margin:.6rem 0}
select,button{font-size:1rem;padding:.4rem .6rem;width:100%}
button{margin-top:1rem}
#msg{margin-top:1.2rem;color:#d00}
.page{margin-top:1.5rem;text-align:center}
.page img{width:100%;border-radius:8px;box-shadow:0 2px 8px #0002}
.page p{margin-top:.8rem;line-height:1.5em;text-align:left}
</style>

<h2>あなただけのえほん</h2>
<form id="f">
  <label>なんさい？
    <select name="age">{% for a in range(0,11) %}<option>{{a}}</option>{% endfor %}</select>
  </label>
  <label>おとこのこ と おんなのこ のどっち？
    <select name="gender"><option>おとこのこ</option><option>おんなのこ</option></select>
  </label>
  <label>しゅじんこう
    <select name="hero">
      <option>ろぼっと</option><option>くるま</option><option>まほうつかい</option><option>じぶん</option>
    </select>
  </label>
  <label>テーマ
    <select name="theme">
      <option>ゆうじょう</option><option>ぼうけん</option><option>ちょうせん</option>
      <option>かぞく</option><option>まなび</option>
    </select>
  </label>
  <button>えほんをつくる</button>
</form>

<p id="msg"></p>
<div id="pages"></div>

<script>
const form  = document.getElementById('f');
const btn   = form.querySelector('button');
const msg   = document.getElementById('msg');
const pages = document.getElementById('pages');

form.onsubmit = async e=>{
  e.preventDefault();
  btn.disabled = true;
  msg.textContent = "🚀 生成中…";
  pages.innerHTML = "";

  const res = await fetch("/api/book",{method:"POST",body:new FormData(form)});
  let data;
  try{ data = await res.json(); }
  catch{ msg.textContent="❌ サーバーエラー"; btn.disabled=false; return; }

  if(data.error){ msg.textContent="❌ "+data.error; btn.disabled=false; return; }

  msg.textContent = "✅ 完了！";
  data.pages.forEach(pg=>{
    pages.insertAdjacentHTML("beforeend",
      `<div class="page"><img src="${pg.img}"><p>${pg.text}</p></div>`);
  });
  btn.disabled = false;
};
</script>
"""

# ====== ルーティング ==================================================
@app.route("/")
def index():
    return render_template_string(HTML)


@app.route("/api/book", methods=["POST"])
def api_book():
    try:
        f = request.form
        rsp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role":"system","content": story_prompt(f['age'], f['gender'], f['hero'], f['theme'])}],
            max_tokens=700,
            response_format={"type":"json_object"}
        )
        story_json = json.loads(rsp.choices[0].message.content)
        hero_tag = f"main character is a {f['hero']}"
        pages = [{"img": dall_e(hero_tag + ", " + sc[:60]), "text": sc} for sc in story_json["story"][:3]]
        return jsonify({"pages": pages})
    except Exception as e:
        traceback.print_exc(file=sys.stderr)
        return jsonify({"error": str(e)}), 500


@app.route("/api/generate", methods=["POST"])
def api_generate():
    """PDF ダウンロード用エンドポイント"""
    try:
        f = request.form
        hero_tag = f"main character is a {f['hero']}"

        # 1. ストーリー JSON を取得
        rsp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{
                "role": "system",
                "content": story_prompt(f['age'], f['gender'], f['hero'], f['theme'])
            }],
            max_tokens=700,
            response_format={"type": "json_object"}
        )

        # 2. 挿絵付き PDF を作成
        story_json = json.loads(rsp.choices[0].message.content)
        pdfname = generate_pdf(story_json, hero_tag)

        # 3. フロントへファイル名を返す
        return jsonify({"file": pdfname})

    except Exception as e:
        traceback.print_exc(file=sys.stderr)
        return jsonify({"error": str(e)}), 500

