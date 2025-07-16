# app.py — あなただけのえほんジェネレーター（音声読み上げ対応 Flask アプリ）
# -------------------------------------------------------------
from flask import Flask, render_template_string, request, jsonify, send_from_directory
import os, json, textwrap, datetime, traceback, sys, requests
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

# ====== OpenAI 初期化 ======
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ====== PDF 用フォント設定 ======
pdfmetrics.registerFont(TTFont("JPFont", "fonts/NotoSansJP-Bold.ttf"))
IMG_SIZE, MARGIN = 512, 40

app = Flask(__name__, static_folder="static")

# ====== 画像生成ラッパー ======
def dall_e(prompt: str) -> str:
    rsp = client.images.generate(
        model="dall-e-3",
        prompt=PROMPT_BASE + prompt,
        n=1,
        size="1024x1024",
    )
    return rsp.data[0].url

# ====== プロンプト生成 ======
def story_prompt(age: str, gender: str, hero: str, theme: str) -> str:
    return f"""
あなたは幼児向け児童文学作家です。
・対象年齢:{age}さい ・読者の性別:{gender} ・主人公:{hero} ・テーマ:{theme}
・全3シーン構成(起→承→結)・総文字数300〜400字
JSON={{"title":"タイトル","story":["シーン1","シーン2","シーン3"]}}
"""

# ====== PDF 生成 ======
def generate_pdf(data: dict, hero_tag: str) -> str:
    title, scenes = data["title"], data["story"]
    filename = f"book_{datetime.datetime.now():%Y%m%d_%H%M%S}.pdf"
    path = f"/tmp/{filename}"

    canvas = Canvas(path, pagesize=A4)
    W, H = A4

    for idx, scene in enumerate(scenes[:3]):
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

# ====== HTML UI ======
HTML = """
<!doctype html><meta charset=\"utf-8\">
<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">
<title>あなただけのえほん</title>
<style>
  body { font-family: sans-serif; background: #fff0f5; text-align: center; padding: 1em; }
  label, select, input, button { font-size: 1.2em; display: block; margin: 0.8em auto; width: 90%; max-width: 320px; }
  button { padding: 0.6em 2em; background: #ff69b4; color: white; border: none; border-radius: 10px; }
  button:hover { background: #ff1493; }
  img { max-width: 90%; height: auto; margin-top: 1em; border-radius: 10px; box-shadow: 0 0 6px #ccc; }
  .page p { padding: 0 1em; text-align: left; white-space: pre-wrap; }
  #loading { display: none; margin-top: 2em; }
</style>
<h2>あなただけのえほん</h2>
<form id=\"f\">
  <label>なんさい？<br>
    <select name=\"age\">
      <option value=\"0\">0〜1さい</option>
      <option value=\"2\">2〜3さい</option>
      <option value=\"4\">4〜5さい</option>
      <option value=\"6\">6〜7さい</option>
      <option value=\"8\">8〜9さい</option>
      <option value=\"10\">10さい</option>
    </select>
  </label>
  <label>おとこのこ と おんなのこ のどっち？<br>
    <select name=\"gender\"><option>おとこのこ</option><option>おんなのこ</option></select>
  </label>
  <label>しゅじんこう<br>
    <select name=\"hero\">
      <option>ろぼっと</option><option>くるま</option><option>まほうつかい</option><option>じぶん</option>
    </select>
  </label>
  <label>テーマ<br>
    <select name=\"theme\">
      <option>ゆうじょう</option><option>ぼうけん</option><option>ちょうせん</option><option>かぞく</option><option>まなび</option>
    </select>
  </label>
  <button>えほんをつくる</button>
</form>
<div id=\"loading\">
  <p>うさぎさんが絵をかいているよ…♪</p>
  <img src=\"/static/rabbit_drawing.gif\" alt=\"生成中\" style=\"width:180px;\">
  <audio id=\"bgm\" loop>
    <source src=\"/static/when_you_wish_upon_a_star.mp3\" type=\"audio/mpeg\">
  </audio>
</div>
<audio id=\"player\" controls style=\"display:none\"></audio>
<p id=\"msg\"></p>
<div id=\"pages\"></div>
<script>
const form = document.getElementById('f');
const btn = form.querySelector('button');
const msg = document.getElementById('msg');
const pages = document.getElementById('pages');
const audio = document.getElementById('player');
const loading = document.getElementById('loading');

form.onsubmit = async e => {
  e.preventDefault();
  const bgm = document.getElementById('bgm');
  try { bgm.play(); } catch (e) {}
  btn.disabled = true;
  msg.textContent = "";
  pages.innerHTML = "";
  loading.style.display = "block";

  const res = await fetch("/api/book_with_voice", { method: "POST", body: new FormData(form) });
  const data = await res.json();

  loading.style.display = "none";
  bgm.pause();
  bgm.currentTime = 0;

  if (data.error) {
    msg.textContent = "❌ " + data.error;
    btn.disabled = false;
    return;
  }

  msg.textContent = "✅ 完了！";
  data.pages.forEach(pg => {
    pages.insertAdjacentHTML("beforeend", `
      <div class=\"page\">
        <img src=\"${pg.img}\" />
        <p>${pg.text}</p>
      </div>`);
  });

  if (data.audio_url) {
    audio.src = data.audio_url;
    audio.style.display = "block";
    audio.play();
  }

  btn.disabled = false;
    return;
  }

  msg.textContent = "✅ 完了！";
  data.pages.forEach(pg => {
    pages.insertAdjacentHTML("beforeend", `
      <div class=\"page\">
        <img src=\"${pg.img}\" />
        <p>${pg.text}</p>
      </div>`);
  });

  if (data.audio_url) {
    audio.src = data.audio_url;
    audio.style.display = "block";
    audio.play();
  }

  btn.disabled = false;
};
</script>
"""

# ====== Flask ルーティング ======
@app.route("/")
def index():
    return render_template_string(HTML)

@app.route("/api/book_with_voice", methods=["POST"])
def api_book_with_voice():
    try:
        f = request.form
        rsp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": story_prompt(f['age'], f['gender'], f['hero'], f['theme'])}],
            max_tokens=700,
            response_format={"type": "json_object"}
        )
        story_json = json.loads(rsp.choices[0].message.content)

        story_text = "。".join(story_json["story"])
        filename = f"tts_{datetime.datetime.now():%Y%m%d_%H%M%S}.mp3"
        path = os.path.join("/tmp", filename)

        speech = client.audio.speech.create(
            model="tts-1",
            voice="shimmer",
            input=story_text
        )
        speech.stream_to_file(path)

        hero_tag = f"main character is a {f['hero']}"
        pages = [{"img": dall_e(hero_tag + ", " + sc[:60]), "text": sc} for sc in story_json["story"][:3]]

        return jsonify({"pages": pages, "audio_url": f"/audio/{filename}"})

    except Exception as e:
        traceback.print_exc(file=sys.stderr)
        return jsonify({"error": str(e)}), 500

@app.route("/audio/<filename>")
def serve_audio(filename):
    return send_from_directory("/tmp", filename, mimetype="audio/mpeg")
