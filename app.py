import os, random, sys, traceback, json
from flask import Flask, request, jsonify, send_from_directory, render_template_string
from openai import OpenAI
from reportlab.pdfgen.canvas import Canvas
from reportlab.lib.pagesizes import A4
from PIL import Image
from io import BytesIO
import requests
from datetime import datetime

client = OpenAI()
app = Flask(__name__)

HTML = """
<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <title>あなただけのえほん</title>
  <style>
    body { font-family: sans-serif; background: #fff0f5; text-align: center; padding: 1em; }
    label, select, input { font-size: 1.2em; margin: 0.5em; }
    button { font-size: 1.3em; padding: 0.6em 2em; background: #ff69b4; color: white; border: none; border-radius: 10px; }
    button:hover { background: #ff1493; }
    .error { color: red; margin-top: 1em; }
  </style>
</head>
<body>
  <h2>あなただけのえほん</h2>
  <form id="form">
    <div><label>なんさい？<select name="age">
      <option>3</option><option>4</option><option>5</option><option>6</option><option>7</option>
    </select></label></div>
    <div><label>おとこのこ と おんなのこ のどっち？<select name="gender">
      <option>おとこのこ</option><option>おんなのこ</option>
    </select></label></div>
    <div><label>しゅじんこうは？<select name="hero">
      <option>ロボット</option><option>くるま</option><option>まほうつかい</option><option>じぶん</option>
    </select></label></div>
    <div><label>テーマは？<select name="theme">
      <option>ゆうじょう</option><option>ぼうけん</option><option>ちょうせん</option><option>かぞく</option><option>まなび</option>
    </select></label></div>
    <button type="submit">えほんをつくる</button>
    <div class="error" id="err"></div>
  </form>

  <script>
    form.onsubmit = async e => {
      e.preventDefault();
      err.textContent = "";
      const fd = new FormData(form);
      const res = await fetch("/api/book", { method: "POST", body: fd });
      if (res.headers.get("content-type").includes("application/json")) {
        const j = await res.json();
        if (j.error) err.textContent = "エラー: " + j.error;
      } else {
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = "ehon.pdf";
        a.click();
      }
    };
  </script>
</body>
</html>
"""

@app.route("/")
def index():
    return render_template_string(HTML)

def story_prompt(age, gender, hero, theme):
    return f"""あなたは子ども向け絵本のストーリー作家です。
すべて「ひらがな」で、{age}さいの{gender}のために、しゅじんこうが「{hero}」で、テーマは「{theme}」のストーリーをかいてください。

さいごはこころがあたたかくなるハッピーエンドにしてください。
こたえは「ストーリー」というキーでJSONオブジェクトにしてください。
"""

def dall_e(prompt):
    rsp = client.images.generate(
        model="dall-e-3",
        prompt=prompt + "\n（日本のこどもがすきなやわらかいタッチ、かわいい）",
        size="1024x1024",
        quality="standard",
        n=1,
    )
    return rsp.data[0].url

def generate_pdf(story_list):
    dt = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = f"output/book_{dt}.pdf"
    os.makedirs("output", exist_ok=True)
    c = Canvas(path, pagesize=A4)

    for scene in story_list:
        try:
            # 画像を生成・取得
            url = dall_e(scene[:60])
            img_data = requests.get(url).content
            img = Image.open(BytesIO(img_data))

            # サイズ調整
            w, h = A4
            img = img.resize((int(w), int(w)))
            img_io = BytesIO()
            img.save(img_io, format='PNG')
            img_io.seek(0)
            c.drawImage(ImageReader(img_io), 0, h - w)

            # テキスト描画
            c.setFont("Helvetica", 20)
            c.drawString(50, h - w - 40, scene[:60])

            # ページ切り替え
            c.showPage()
            img.close()
        except Exception as e:
            print("画像生成エラー:", e)

    c.save()
    return path

@app.route("/api/book", methods=["POST"])
def api_book():
    try:
        f = request.form
        prompt = story_prompt(f["age"], f["gender"], f["hero"], f["theme"])
        rsp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": prompt}],
            max_tokens=800,
            temperature=0.8,
            response_format={"type": "json_object"}
        )
        res = json.loads(rsp.choices[0].message.content)
        story = res.get("ストーリー")
        if not story:
            raise ValueError("ストーリーの生成に失敗しました")
        pdfname = generate_pdf(story)
        return send_from_directory("output", os.path.basename(pdfname), as_attachment=True)
    except Exception as e:
        traceback.print_exc(file=sys.stderr)
        return jsonify({"error": str(e)}), 500
