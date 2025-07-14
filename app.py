# app.py ─ Flask 1 ファイル構成
from flask import Flask, render_template_string, request, jsonify, send_file
import os, io, json, textwrap, datetime, requests, traceback, sys
from dotenv import load_dotenv
from openai import OpenAI
from PIL import Image
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen.canvas import Canvas
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

load_dotenv()                          # .env を読む
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))  # ★ ハードコード禁止

pdfmetrics.registerFont(
    TTFont("JPFont", "fonts/NotoSansJP-Bold.ttf")
)
IMG_SIZE, MARGIN = 512, 40

app = Flask(__name__)

HTML = """
<!doctype html><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">   <!-- ★追加 -->
<title>AIえほん β</title>
<style>
:root{font-size:18px}                /* ★全体の基準フォント ↑ */
@media (min-width:600px){:root{font-size:16px}} /* PCでは元に戻す */

body{font-family:sans-serif;max-width:460px;margin:2rem auto;padding:0 1rem}
label{display:block;margin:.6rem 0}
select,button{font-size:1rem;padding:.4rem .6rem;width:100%}
button{margin-top:1rem}
#msg{margin-top:1.2rem;color:#d00}
.page{margin-top:1.5rem;text-align:center}
.page img{width:100%;border-radius:8px;box-shadow:0 2px 8px #0002}
.page p{margin-top:.8rem;line-height:1.5em;text-align:left}
nav{display:flex;justify-content:space-between;margin-top:1rem}
nav button{width:48%}
</style>


<h2>AI えほんをつくる</h2>
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
    <select name="theme"><option>友情</option><option>冒険</option><option>挑戦</option><option>家族</option><option>学び</option></select>
  </label>
  <button>PDF を生成</button>
</form>

<p id="msg"></p>
<a id="dl" style="display:none"></a>
<hr>

<script>
const form = document.getElementById('f');
const btn  = form.querySelector('button');
const msg  = document.getElementById('msg');
const viewer = document.createElement('div'); document.body.appendChild(viewer);

form.onsubmit = async e=>{
  e.preventDefault(); btn.disabled=true; viewer.innerHTML=""; msg.textContent="🚀 生成中…";

  const res = await fetch("/api/book", {method:"POST", body:new FormData(form)});
  const data = await res.json().catch(()=>msg.textContent="❌ JSONエラー");
  if(data.error){msg.textContent="❌ "+data.error;btn.disabled=false;return;}

  msg.textContent="✅ 完了！ 画面をスクロールして読んでね";
  data.pages.forEach((pg,i)=>{
    const div=document.createElement('div');div.className="page";
    div.innerHTML=`<img src="${pg.img}"><p>${pg.text}</p>`;
    viewer.appendChild(div);
  });
  btn.disabled=false;
};
</script>

"""

def story_prompt(age, gender, hero, theme):
    return f"""
あなたは幼児向け児童文学作家です。
・対象年齢:{age}歳 ・読者の性別:{gender} ・主人公:{hero} ・テーマ:{theme}
・**全3シーン構成**(起→承→結)・総文字数300〜400字
JSON={{"title":"タイトル","story":["シーン1","シーン2","シーン3"]}}
"""


def generate_pdf(data):
    """ストーリーJSON → 挿絵付きPDF を /tmp に保存しファイル名を返す"""
    title, scenes = data["title"], data["story"]

    filename = f"book_{datetime.datetime.now():%Y%m%d_%H%M%S}.pdf"
    path = f"/tmp/{filename}"

    canvas = Canvas(path, pagesize=A4)
    W, H = A4

    for idx, scene in enumerate(scenes[:3]):        # ← 画像3枚だけ
        # -- 1) 画像を生成して即開放 -----------------------------------
        url = client.images.generate(
            model="dall-e-3",
            prompt=f"Children's picture-book illustration, {scene[:80]}",
            n=1,
            size="1024x1024"
        ).data[0].url

        with Image.open(requests.get(url, stream=True).raw) as img:
            img = img.resize((IMG_SIZE, IMG_SIZE), Image.LANCZOS)
            canvas.drawImage(ImageReader(img),
                             MARGIN, H - IMG_SIZE - MARGIN,
                             IMG_SIZE, IMG_SIZE)

        # -- 2) テキスト配置 -------------------------------------------
        if idx == 0:
            canvas.setFont("JPFont", 14)
            canvas.drawString(MARGIN,
                              H - IMG_SIZE - MARGIN - 20,
                              f"『{title}』")

        canvas.setFont("JPFont", 11)
        txt = canvas.beginText(MARGIN,
                               H - IMG_SIZE - MARGIN - 40)
        txt.textLines(textwrap.fill(scene, 38))
        canvas.drawText(txt)

        canvas.showPage()

    canvas.save()
    return filename



@app.route("/")
def index(): return render_template_string(HTML)

@app.route("/api/generate", methods=["POST"])
def api_generate():
    try:
        f = request.form
        rsp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role":"system",
                       "content": story_prompt(f['age'],f['gender'],f['hero'],f['theme'])}],
            max_tokens=700,
            response_format={"type":"json_object"})
        pdfname = generate_pdf(json.loads(rsp.choices[0].message.content))
        return jsonify({"file": pdfname})
    except Exception as e:
        traceback.print_exc(file=sys.stderr)
        return jsonify({"error": str(e)}), 500

@app.route("/pdf/<name>")
def download(name): return send_file(f"/tmp/{name}", as_attachment=True)

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    app.run(host="0.0.0.0", port=port)

@app.route("/api/book", methods=["POST"])
def api_book():
    try:
        f = request.form
        # 1) ストーリー 3 シーン
        rsp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role":"system",
                       "content": story_prompt(f['age'],f['gender'],f['hero'],f['theme'])}],
            max_tokens=700,
            response_format={"type":"json_object"})
        story = json.loads(rsp.choices[0].message.content)["story"][:3]

        # 2) 各シーンの挿絵 URL
        pages=[]
        for sc in story:
            url = client.images.generate(
                model="dall-e-3",
                prompt=f"Children's picture book illustration, {sc[:80]}",
                n=1,size="1024x1024").data[0].url
            pages.append({"img":url,"text":sc})

        return jsonify({"pages":pages})
    except Exception as e:
        traceback.print_exc(file=sys.stderr)
        return jsonify({"error":str(e)}),500
