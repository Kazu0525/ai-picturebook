# app.py  ─ Flask 1ファイル構成
from flask import Flask, render_template_string, request, jsonify, send_file
import os, json, textwrap, datetime, requests, traceback, sys
from dotenv import load_dotenv
from openai import OpenAI
from PIL import Image
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen.canvas import Canvas
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# ── DALL·E 共通プロンプト ───────────────────────────
PROMPT_BASE = (
    "Soft watercolor children’s picture-book illustration, "
    "kawaii Japanese style, gentle pastel color palette, "
    "no text, no captions, consistent protagonist, "
)

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

pdfmetrics.registerFont(TTFont("JPFont", "fonts/NotoSansJP-Bold.ttf"))
IMG_SIZE, MARGIN = 512, 40

app = Flask(__name__)

# ── HTML テンプレート ───────────────────────────────
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
  <label>年齢:
    <select name="age">{% for a in range(0,11) %}<option>{{a}}</option>{% endfor %}</select>
  </label>
  <label>性別:
    <select name="gender"><option>おとこのこ</option><option>おんなのこ</option></select>
  </label>
  <label>主人公:
    <select name="hero"><option>ロボット</option><option>くるま</option><option>魔法使い</option><option>子ども本人</option></select>
  </label>
  <label>テーマ:
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
const form = document.getElementById('f');
const btn  = form.querySelector('button');
const msg  = document.getElementById('msg');
const pages= document.getElementById('pages');

form.onsubmit = async e=>{
  e.preventDefault();
  btn.disabled=true; msg.textContent="🚀 生成中…"; pages.innerHTML="";

  const res = await fetch("/api/book",{method:"POST",body:new FormData(form)});
  let data;
  try{ data = await res.json(); }catch{ msg.textContent="❌ サーバーエラー"; btn.disabled=false; return;}
  if(data.error){ msg.textContent="❌ "+data.error; btn.disabled=false; return;}

  msg.textContent="✅ 完了！";
  data.pages.forEach(pg=>{
    pages.insertAdjacentHTML("beforeend",
      `<div class="page"><img src="${pg.img}"><p>${pg.text}</p></div>`);
  });
  btn.disabled=false;
};
</script>
"""

# ── GPT プロンプト ────────────────────────────────
def story_prompt(age, gender, hero, theme):
    return f"""
あなたは幼児向け児童文学作家です。
・対象年齢:{age}歳 ・読者の性別:{gender} ・主人公:{hero} ・テーマ:{theme}  ※テーマはひらがな表記
・全3シーン構成(起→承→結)・総文字数300〜400字
JSON={{"title":"タイトル","story":["シーン1","シーン2","シーン3"]}}
"""

# ── PDF 作成（必要ならダウンロード用） ───────────────
def generate_pdf(data):
    title, scenes = data["title"], data["story"]
    filename = f"book_{datetime.datetime.now():%Y%m%d_%H%M%S}.pdf"
    path     = f"/tmp/{filename}"
    c = Canvas(path, pagesize=A4)
    W, H = A4

    for idx, scene in enumerate(scenes[:3]):      # ★3枚
        url = client.images.generate(
            model="dall-e-3",
            prompt=PROMPT_BASE + scene[:60],
            n=1, size="1024x1024"
        ).data[0].url

        with Image.open(requests.get(url,stream=True).raw) as img:
            img = img.resize((IMG_SIZE,IMG_SIZE), Image.LANCZOS)
            c.drawImage(ImageReader(img), MARGIN, H-IMG_SIZE-MARGIN, IMG_SIZE, IMG_SIZE)

        if idx==0:
            c.setFont("JPFont",14)
            c.drawString(MARGIN, H-IMG_SIZE-MARGIN-20, f"『{title}』")

        c.setFont("JPFont",11)
        t=c.beginText(MARGIN, H-IMG_SIZE-MARGIN-40)
        t.textLines(textwrap.fill(scene,38))
        c.drawText(t)
        c.showPage()

    c.save()
    return filename

# ── ルーティング ────────────────────────────────
@app.route("/")
def index(): return render_template_string(HTML)

@app.route("/api/book", methods=["POST"])
def api_book():
    try:
        f = request.form
        rsp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role":"system","content":story_prompt(f['age'],f['gender'],f['hero'],f['theme'])}],
            max_tokens=700,
            response_format={"type":"json_object"})
        story = json.loads(rsp.choices[0].message.content)["story"][:3]

        pages=[]
        for sc in story:
            url = client.images.generate(
                model="dall-e-3",
                prompt=PROMPT_BASE + sc[:60],
                n=1, size="1024x1024"
            ).data[0].url
            pages.append({"img":url,"text":sc})

        return jsonify({"pages":pages})
    except Exception as e:
        traceback.print_exc(file=sys.stderr)
        return jsonify({"error":str(e)}),500

# PDF ダウンロードが必要なら /api/generate と /pdf/<name> を残す
@app.route("/api/generate", methods=["POST"])
def api_generate():
    f=request.form
    rsp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role":"system","content":story_prompt(f['age'],f['gender'],f['hero'],f['theme'])}],
        max_tokens=700,
        response_format={"type":"json_object"})
    pdfname = generate_pdf(json.loads(rsp.choices[0].message.content))
    return jsonify({"file":pdfname})

@app.route("/pdf/<name>")
def download(name): return send_file(f"/tmp/{name}", as_attachment=True)

if __name__ == "__main__":
    port = int(os.getenv("PORT",8000))
    app.run(host="0.0.0.0",port=port)
