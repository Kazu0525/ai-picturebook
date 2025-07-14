# app.py  ─ Flask 1 ファイル構成
from flask import Flask, render_template_string, request, jsonify
import os, json
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
client = OpenAI(api_key=os.getenv("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"))

app = Flask(__name__)

HTML = """
<!doctype html><meta charset="utf-8">
<title>AIえほん β</title><style>body{font-family:sans-serif;max-width:480px;margin:40px auto}</style>
<h2>AI えほんをつくる</h2>
<form id="f">
<label>年齢 <select name="age">
{% for a in range(0,11) %}<option value="{{a}}">{{a}}</option>{% endfor %}</select></label><br><br>
<label>性別 <select name="gender"><option>おとこのこ</option><option>おんなのこ</option></select></label><br><br>
<label>主人公 <select name="hero"><option>ロボット</option><option>くるま</option><option>魔法使い</option><option>子ども本人</option></select></label><br><br>
<label>テーマ <select name="theme"><option>友情</option><option>冒険</option><option>挑戦</option><option>家族</option><option>学び</option></select></label><br><br>
<button>おはなしをつくる</button>
</form><hr>
<pre id="out"></pre>
<script>
f.onsubmit = async (e)=>{e.preventDefault();
  out.textContent="生成中…";
  const fd=new FormData(f);
  const r=await fetch("/api/story",{method:"POST",body:fd});
  const j=await r.json();
  if(j.error){out.textContent=j.error}else{
    out.innerHTML="<h3>"+j.title+"</h3>"+j.story.join("<br><br>");
  }
}
</script>
"""

PROMPT = """あなたは幼児向け児童文学作家です。
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

@app.route("/")
def index(): return render_template_string(HTML)

@app.route("/api/story", methods=["POST"])
def api_gen():
    try:
        f = request.form
        # 1) ストーリー JSON を生成
        rsp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{
                "role": "system",
                "content": story_prompt(f['age'], f['gender'], f['hero'], f['theme'])
            }],
            max_tokens=700,
            response_format={"type": "json_object"}
        )
        story_data = json.loads(rsp.choices[0].message.content)

        # 2) PDF を作成し /tmp に保存
        pdfname = generate_pdf(story_data)   # ← generate_pdf() の戻り値がファイル名

        # 3) フロントへファイル名を返す
        return jsonify({"file": pdfname})

    except Exception as e:
        import traceback, sys
        traceback.print_exc(file=sys.stderr)   # スタックトレースを Logs に出力
        return jsonify({"error": str(e)}), 500



if __name__=="__main__":
    app.run(debug=True)

if __name__ == "__main__":
    import os
    port = int(os.getenv("PORT", 8000))  # Render が PORT を渡す
    app.run(host="0.0.0.0", port=port)
