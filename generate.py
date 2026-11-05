# -*- coding: utf-8 -*-
"""宇宙・科学・人体の雑学Shorts 自動生成 (Phase 1)
台本→VOICEVOX音声→Pexels映像→字幕→BGM/効果音→MP4→サムネ→メタ情報
"""
import os, re, sys, json, time, random, pathlib, subprocess, datetime, traceback, unicodedata
import requests

try:  # 実行ログをリアルタイムに表示する
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)
except Exception:
    pass

W, H = 1080, 1920
OUT, WORK, DATA = pathlib.Path("output"), pathlib.Path("work"), pathlib.Path("data")
MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")
VV = "http://localhost:50021"
VOICE_NAME = os.environ.get("VOICE_NAME", "ずんだもん")
SPEED = float(os.environ.get("VOICE_SPEED", "1.1"))
VOLUME = float(os.environ.get("VOICE_VOLUME", "1.0"))
UA = {"User-Agent": "science-shorts/0.1 (personal hobby project)"}


class Fail(Exception):
    pass


def clean(t):
    """目に見えない特殊文字・絵文字など、字幕で文字化け(□)の原因になる文字を除去する"""
    t = unicodedata.normalize("NFKC", str(t))
    out, removed = [], []
    for c in t:
        cat = unicodedata.category(c)
        if c == "\n" or cat[0] in "LNP" or cat in ("Zs", "Sm", "Sc", "Sk") and c.isprintable():
            out.append(c)
        else:
            removed.append(f"U+{ord(c):04X}")
    if removed:
        print("   除去した文字:", " ".join(removed))
    return "".join(out)


def git_push(msg):
    for c in (["git", "config", "user.name", "github-actions"], ["git", "config", "user.email", "actions@github.com"],
              ["git", "add", "-A", "data"], ["git", "commit", "-m", msg], ["git", "push"]):
        try:
            subprocess.run(c, capture_output=True, text=True, timeout=60)
        except Exception as e:
            print("   git操作に失敗(無視):", e)


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise Fail("ffmpeg/コマンド失敗: " + " ".join(cmd[:3]) + "\n" + r.stderr[-1500:])
    return r.stdout


def font():
    r = subprocess.run(["fc-match", "-f", "%{file}", "Noto Sans CJK JP:bold"],
                       capture_output=True, text=True)
    if not r.stdout:
        raise Fail("日本語フォントが見つかりません (fonts-noto-cjk)")
    return r.stdout


# ---------- Gemini ----------
def gemini(prompt):
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise Fail("GEMINI_API_KEY が設定されていません")
    models = [m.strip() for m in os.environ.get("GEMINI_MODELS", MODEL + ",gemini-3.1-flash-lite").split(",") if m.strip()]
    body = {"contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": 0.8}}
    last = ""
    for rnd in range(3):
        for m in models:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent"
            try:
                r = requests.post(url, headers={"x-goog-api-key": key}, json=body, timeout=120)
            except requests.RequestException as e:
                last = f"{m}: 通信エラー {e}"
                continue
            if r.status_code in (404, 429, 500, 503):
                last = f"{m}: {r.status_code}"
                print(f"   Gemini {m} が使えません({r.status_code})→次のモデルを試します")
                continue
            if r.status_code != 200:
                raise Fail(f"Gemini APIエラー {m} {r.status_code}: {r.text[:400]}")
            try:
                txt = r.json()["candidates"][0]["content"]["parts"][0]["text"]
                return json.loads(re.sub(r"^```json|```$", "", txt.strip()))
            except Exception as e:
                last = f"{m}: 応答を解析できません {e}"
                continue
        time.sleep(20 * (rnd + 1))
    raise Fail("Geminiの無料枠の上限に達した可能性があります。時間をおいて再実行してください（最後のエラー: " + last + "）")


# ---------- 1. テーマ ----------
def pick_topic(history):
    used = [h["topic"] for h in history][-200:]
    p = f"""あなたは「宇宙の意外な雑学」YouTubeショート動画の企画者です。
テーマは、宇宙・天体・太陽系・地球と宇宙の関わり・探査機・望遠鏡など、NASAの画像や映像で表現できる題材に限ります。
人物（宇宙飛行士など）が主役の話題は避けてください。

日本の一般の大人の多くが「知らなかった！」と驚く題材を選ぶこと。
教科書や雑学本の定番（宇宙は広い、月は少しずつ遠ざかる、太陽は恒星、など）は避ける。
常識の逆を行く事実、桁外れの数字、身近なものに例えると驚く比較（バナナの放射線のような話）が理想。

- topic: 動画テーマ(日本語、驚きが伝わる言い方)
- angle: 動画で伝える一番意外な事実を1文で
- wiki_query: Wikipedia日本語に実在する、天体・探査機・現象などの一般的な記事名(例:「かに星雲」「ボイジャー1号」)。人名は不可。
すでに使ったテーマ（重複・類似は禁止）: {json.dumps(used, ensure_ascii=False)}
JSONのみ: {{"topic":"","angle":"","wiki_query":""}}"""
    t = gemini(p)
    if isinstance(t, list):
        t = t[0] if t else {}
    if not t.get("topic") or not t.get("wiki_query"):
        raise Fail("テーマを決められませんでした")
    return t


# ---------- 2. 調査 ----------
def wiki(query):
    api = "https://ja.wikipedia.org/w/api.php"
    s = requests.get(api, headers=UA, timeout=30, params={
        "action": "query", "list": "search", "srsearch": query, "format": "json", "srlimit": 1}).json()
    hits = s.get("query", {}).get("search", [])
    if not hits:
        return None
    title = hits[0]["title"]
    e = requests.get(api, headers=UA, timeout=30, params={
        "action": "query", "prop": "extracts", "explaintext": 1, "titles": title, "format": "json"}).json()
    page = next(iter(e["query"]["pages"].values()))
    text = (page.get("extract") or "")[:8000]
    if len(text) < 200:
        return None
    return {"title": title, "url": "https://ja.wikipedia.org/wiki/" + requests.utils.quote(title), "text": text}


def wiki_any(queries):
    """検索語を言い換えながら探す(中黒を空白にする、かっこを外す、テーマ文で探す)"""
    tried = []
    for q in queries:
        for v in (q, q.replace("・", " "), re.sub(r"[（(].*?[）)]", "", q).strip()):
            if v and v not in tried:
                tried.append(v)
                r = wiki(v)
                if r:
                    return r
    raise Fail("Wikipediaに資料が見つかりません: " + " / ".join(tried) + "（出典なしでは作成しません）")


# ---------- 3-4. 台本と事実確認 ----------
def write_script(topic, angle, src, feedback=""):
    p = f"""あなたはYouTubeショートの構成作家です。テーマ「{topic}」の台本を作ります。
軸にしたい意外な事実(案): {angle}
※資料で裏付けられない場合は、資料の中から最も意外で具体的な事実に軸を変えてよい。
【資料（これに書かれた事実だけを使うこと。資料にない数字や主張は禁止）】
{src['text']}

条件:
- ナレーション合計 260〜330文字（約45〜55秒）。自然な話し言葉の日本語。
- 構成: 冒頭2秒で驚かせる問いかけ → 意外な事実 → 理由の解説 → 余韻のある結び
- 【質の条件】日本の一般の大人がすでに知っている基本説明で尺を使わない。「みんなが思っていること」→「実は違う／もっと桁外れ」の落差を作る。
- 冒頭は、具体的な数字か、常識を覆す一言で始める（「〇〇って知ってた？」の定型だけにしない）。
- 資料にある具体的な数字を2〜3個使い、身近なものに例えて実感させる。例えは資料の数値からの単純な換算に限り、断定しすぎない。
- 一般論や感想（「神秘的ですね」など）で字数を埋めない。1シーン1情報。
- 数字は資料の値をそのまま使い、丸めるときは「約」を付ける。資料にない比較（〜より大きい、〜をも凌ぐ等）を事実として言わない。例えは「たとえるなら」と分かる形にする。
- 難しい専門用語には短い説明を添える。引き延ばしや繰り返しは禁止。
- 6〜8シーンに分割。1シーンのnarrationは20〜60文字。
- emphasis: 画面に大きく出すキーワード(8文字以内)。
- pexels_query: Pexelsで映像を探す英語の検索語(2〜3語、具体的)。
- nasa_query: NASAの画像・映像ライブラリで見つかりそうな英語の検索語(1〜3語。例: black hole, solar flare, Earth from orbit, Mars surface, nebula)。人物ではなく天体・地球・現象・探査機など、NASAが撮影した一般的な対象にする。そのシーンの内容に近い語にする。
- titles: クリックしたくなるタイトル3案(各30文字以内)
- description: 概要欄(200字程度)  hashtags: 5個(#付き)  pinned_comment: 固定コメント案
- facts: 台本で述べた事実の短いリスト(各々資料のどこに基づくか分かる形で)
{('前回の指摘(必ず修正): ' + feedback) if feedback else ''}
JSONのみで返す:
{{"titles":["","",""],"scenes":[{{"narration":"","emphasis":"","pexels_query":"","nasa_query":""}}],
"description":"","hashtags":["#"],"pinned_comment":"","facts":[""]}}"""
    return gemini(p)


def fact_check(script, src):
    p = f"""次の動画台本を、資料と照合して事実確認してください。
【資料】{src['text']}
【台本】{json.dumps([s['narration'] for s in script['scenes']], ensure_ascii=False)}
次の「重大な問題」だけを problems に挙げる。なければ ok=true。
- 資料と矛盾する内容
- 資料にない数字・固有名詞・出来事を、事実として断定している
- 数字の桁や単位の誤り
次は問題にしない: 「約」「およそ」を付けた丸め、単位の言い換え(万→億など)、資料の内容を言い換えた表現、
「たとえるなら」など比喩だと分かる例え、細かな言い回しの好み。
JSONのみ: {{"ok":true,"problems":[""]}}"""
    return gemini(p)


def repair_script(script, src, problems):
    """指摘された部分だけを、資料に書かれている範囲に直す"""
    p = f"""次の動画台本の JSON を修正してください。
【資料】{src['text']}
【指摘された問題】{problems}
ルール: 指摘された部分は、資料に書かれている表現と数字に直すか、裏付けのない部分を削除する。
断定できない比較や数字は入れない。それ以外の部分・構成・シーン数は変えない。
【台本JSON】{json.dumps(script, ensure_ascii=False)}
同じ形式のJSONのみで返す。"""
    r = gemini(p)
    return r if isinstance(r, dict) and r.get("scenes") else script


# ---------- 5. 音声 ----------
def pick_speaker():
    sp = requests.get(f"{VV}/speakers", timeout=30).json()
    for s in sp:
        if s["name"] == VOICE_NAME:
            st = next((x for x in s["styles"] if x["name"] == "ノーマル"), s["styles"][0])
            return st["id"], s["name"]
    raise Fail(f"VOICEVOXに話者が見つかりません: {VOICE_NAME}")


def tts(text, speaker, path):
    q = requests.post(f"{VV}/audio_query", params={"text": text, "speaker": speaker}, timeout=60)
    if q.status_code != 200:
        raise Fail(f"VOICEVOX audio_query失敗: {q.text[:300]}")
    q = q.json()
    q.update(speedScale=SPEED, volumeScale=VOLUME, prePhonemeLength=0.1, postPhonemeLength=0.2)
    a = requests.post(f"{VV}/synthesis", params={"speaker": speaker}, json=q, timeout=180)
    if a.status_code != 200:
        raise Fail(f"VOICEVOX synthesis失敗: {a.text[:300]}")
    pathlib.Path(path).write_bytes(a.content)
    d = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", str(path)])
    return float(d.strip())


# ---------- 6. 映像素材 ----------
def pexels(query, used):
    key = os.environ.get("PEXELS_API_KEY")
    if not key:
        return None
    try:
        r = requests.get("https://api.pexels.com/videos/search", headers={"Authorization": key},
                         params={"query": query, "orientation": "portrait", "per_page": 10}, timeout=30)
        for v in r.json().get("videos", []):
            if v["id"] in used:
                continue
            files = [f for f in v["video_files"] if f.get("height") and f["height"] >= f["width"]
                     and f["width"] <= 1100] or v["video_files"]
            files.sort(key=lambda f: abs(f["width"] - 720))
            used.add(v["id"])
            return v["id"], files[0]["link"], v.get("user", {}).get("name", "")
    except Exception as e:
        print("Pexels取得失敗:", e)
    return None



NASA_CENTERS = {"HQ", "JPL", "GSFC", "JSC", "MSFC", "ARC", "KSC", "LaRC", "GRC", "AFRC", "SSC"}
BAD = re.compile(r"copyright|©|\besa\b|european space agency|jaxa|roscosmos|cnsa|isro|spacex|boeing|blue origin|"
                 r"northrop|lockheed|virgin|rocket lab|\blogo\b|insignia|emblem|\bpatch\b|\bseal\b|astronaut|"
                 r"cosmonaut|\bcrew\b|portrait|interview|briefing|press conference|administrator|commander|"
                 r"ceremony|\bspeaks?\b|speech|\bteam\b|employee|\bpeople\b|children|student|talks?\b|discuss|explain|"
                 r"\bsays?\b|\bhost\b|presenter|narrat|conversation|panel|lecture|webinar|reporter|anchor|"
                 r"\bnews\b|episode|\bshow\b|poster|lithograph|\bprint\b|\bscan\b|caption|slide|chart|"
                 r"universit|univ\.|\bman\b|\bwoman\b|\bscientist|engineer|\bdr\.", re.I)
VIDEO_OK = re.compile(r"animation|visuali[sz]ation|simulation|time-?lapse|fly-?by|b-?roll", re.I)


def ok_item(d):
    """NASA自身の素材で、他社/他機関の表記・ロゴ・人物が主役のものを除外する(完全ではない)"""
    if d.get("center") not in NASA_CENTERS:
        return False
    blob = " ".join(str(d.get(k, "")) for k in ("title", "description", "secondary_creator", "photographer", "keywords"))
    return not BAD.search(blob)


def nasa_media(query, used):
    """NASA Image and Video Library (APIキー不要)。NASA自身が撮影・制作した素材のみ使う。"""
    api = "https://images-api.nasa.gov"
    for mtype in ("video", "image"):
        try:
            r = requests.get(api + "/search", headers=UA, timeout=30,
                             params={"q": query, "media_type": mtype, "page_size": 30})
            items = r.json().get("collection", {}).get("items", [])
        except Exception as e:
            print("NASA検索失敗:", e); continue
        random.shuffle(items)
        for it in items:
            d = (it.get("data") or [{}])[0]
            nid = d.get("nasa_id")
            if not nid or nid in used or not ok_item(d):
                continue
            if mtype == "video" and not VIDEO_OK.search(" ".join(str(d.get(k, "")) for k in ("title", "description", "keywords"))):
                continue
            try:
                m = requests.get(f"{api}/asset/{requests.utils.quote(nid)}", headers=UA, timeout=30).json()
                hrefs = [x["href"] for x in m["collection"]["items"]]
            except Exception:
                continue
            pref = (["~medium.mp4", "~small.mp4", "~mobile.mp4"] if mtype == "video"
                    else ["~large.jpg", "~medium.jpg"])
            for suf in pref:
                url = next((h for h in hrefs if suf in h), None)
                if url:
                    used.add(nid)
                    return nid, requests.utils.requote_uri(url), mtype, d.get("title", "")
    return None

def download(url, path):
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        if int(r.headers.get("Content-Length", 0)) > 80e6:
            raise ValueError("ファイルが大きすぎるためスキップ")
        with open(path, "wb") as f:
            for c in r.iter_content(1 << 20):
                f.write(c)


# ---------- 字幕・シーン ----------
def wrap(s, n):
    return "\n".join(s[i:i + n] for i in range(0, len(s), n))


def split_lines(s, n):
    """改行記号を使わず1行ずつ描くための分割(新しいffmpegで改行が□になる問題の回避)。
    行の長さをそろえ、助詞や句読点の後ろで区切り、1文字だけ残るのを避ける"""
    s = s.strip()
    if len(s) <= n:
        return [s]
    k = -(-len(s) // n)
    out, rest = [], s
    for left in range(k, 1, -1):
        target = -(-len(rest) // left)
        best = None
        for idx in range(max(2, target - 3), min(n, target + 3) + 1):
            if idx >= len(rest) or len(rest) - idx > n * (left - 1):
                continue
            nxt = rest[idx]
            if nxt in "。、」』）・ーっゃゅょぁぃぅぇぉ":
                continue
            score = abs(idx - target) + (0 if rest[idx - 1] in "、。はがをにでとのもへやて" else 2)
            if best is None or score < best[0]:
                best = (score, idx)
        idx = best[1] if best else min(n, target)
        out.append(rest[:idx])
        rest = rest[idx:]
    out.append(rest)
    return out


def chunks(text, limit=26):
    parts = re.findall(r"[^。、！？!?]+[。、！？!?]?", text) or [text]
    out, buf = [], ""
    for p in parts:
        if buf and len(buf) + len(p) > limit:
            out.append(buf)
            buf = ""
        buf += p
    if buf:
        out.append(buf)
    return out



def probe(path):
    o = run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
             "stream=width,height:format=duration", "-of", "json", str(path)])
    j = json.loads(o)
    st = j["streams"][0]
    return int(st["width"]), int(st["height"]), float(j.get("format", {}).get("duration") or 0)

def render_scene(i, sc, bg, wav, dur, F):
    total = dur + 0.15
    elines = split_lines(sc["emphasis"], 8)
    efs = []
    for k, ln in enumerate(elines):
        ef = WORK / f"s{i}_e{k}.txt"
        ef.write_text(ln, encoding="utf-8")
        efs.append(ef)
    cs = chunks(sc["narration"])
    n_all = sum(len(c) for c in cs)
    t, subs = 0.1, []
    for k, c in enumerate(cs):
        span = (dur - 0.3) * len(c) / n_all
        lns = split_lines(c, 14)
        fl = []
        for j, ln in enumerate(lns):
            f = WORK / f"s{i}_c{k}_{j}.txt"
            f.write_text(ln, encoding="utf-8")
            fl.append(f)
        subs.append((fl, t, t + span))
        t += span
    is_img = bool(bg) and str(bg).lower().endswith((".jpg", ".jpeg", ".png"))
    ss = []
    land = False
    if bg:
        w0, h0, d0 = probe(bg)
        land = w0 > h0
        if not is_img and d0 > total + 8:
            ss = ["-ss", f"{random.uniform(3, d0 - total - 1):.2f}"]
    if land:
        fgw = "scale=w='trunc(1080*(1+0.012*t)/2)*2':h=-2:eval=frame" if is_img else "scale=1080:-2"
        base = ("[0:v]split=2[a][b];[a]scale=1242:2208:force_original_aspect_ratio=increase,"
                "crop=1080:1920,boxblur=30:5,eq=brightness=-0.18[bg];"
                f"[b]{fgw}[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,fps=30,setsar=1,")
    else:
        base = ("[0:v]scale=1242:2208:force_original_aspect_ratio=increase,"
                "crop=1080:1920:x='(iw-1080)/2+sin(t*0.8)*40':y='(ih-1920)/2+cos(t*0.6)*40',"
                "fps=30,setsar=1,")
    vf = base + "drawbox=x=0:y=0:w=iw:h=ih:color=black@0.28:t=fill"
    for k, ef in enumerate(efs):
        vf += (f",drawtext=fontfile={F}:textfile='{ef}':fontsize=104:fontcolor=0xFFE14D:borderw=8:"
               f"bordercolor=black:x=(w-text_w)/2:y={260 + k * 124}:alpha='min(1,t/0.25)'")
    if subs:
        vf += f",drawbox=x=0:y=1330:w=iw:h=250:color=black@0.55:t=fill:enable='between(t,0.05,{subs[-1][2] + 0.1:.2f})'"
    for fl, a, b in subs:
        y0 = 1455 - 42 * len(fl)
        for j, f in enumerate(fl):
            vf += (f",drawtext=fontfile={F}:textfile='{f}':fontsize=58:fontcolor=white:borderw=3:bordercolor=black:"
                   f"x=(w-text_w)/2:y={y0 + j * 84}:enable='between(t,{a:.2f},{b:.2f})'")
    vf += ",format=yuv420p[v]"
    if not bg:
        inp = ["-f", "lavfi", "-i", "gradients=s=1080x1920:c0=0x02030a:c1=0x0a3550:x0=0:y0=0:x1=1080:y1=1920:speed=0.02"]
    elif is_img:
        inp = ["-loop", "1", "-framerate", "30", "-i", str(bg)]
    elif ss:
        inp = [*ss, "-i", str(bg)]
    else:
        inp = ["-stream_loop", "-1", "-i", str(bg)]
    out = WORK / f"scene{i}.mp4"
    run(["ffmpeg", "-y", *inp, "-i", str(wav), "-filter_complex", vf, "-map", "[v]", "-map", "1:a",
         "-af", "apad", "-t", f"{total:.2f}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
         "-r", "30", "-c:a", "aac", "-ar", "44100", "-ac", "2", "-b:a", "160k", str(out)])
    return out, total


# ---------- 9-11. 合成 ----------
def make_audio_assets(total):
    run(["ffmpeg", "-y", "-f", "lavfi", "-i", f"sine=f=220:d={total}", "-f", "lavfi", "-i", f"sine=f=277.18:d={total}",
         "-f", "lavfi", "-i", f"sine=f=329.63:d={total}", "-f", "lavfi", "-i", f"sine=f=110:d={total}",
         "-filter_complex",
         f"amix=inputs=4:normalize=0,tremolo=f=0.25:d=0.5,lowpass=f=900,volume=0.06,"
         f"afade=t=in:d=1.5,afade=t=out:st={total - 2:.2f}:d=2",
         "-ar", "44100", str(WORK / "bgm.wav")])
    run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anoisesrc=d=0.5:c=pink:a=0.5", "-af",
         "highpass=f=400,lowpass=f=3000,afade=t=in:d=0.1,afade=t=out:st=0.1:d=0.4,volume=0.35",
         "-ar", "44100", str(WORK / "sfx.wav")])


def assemble(scenes_files, starts, total):
    lst = WORK / "list.txt"
    lst.write_text("".join(f"file '{p.resolve()}'\n" for p in scenes_files))
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(WORK / "concat.mp4")])
    make_audio_assets(total + 1)
    n = len(starts)
    fc = [f"[2:a]asplit={n}" + "".join(f"[x{i}]" for i in range(n))]
    for i, s in enumerate(starts):
        ms = int(s * 1000)
        fc.append(f"[x{i}]adelay={ms}|{ms}[d{i}]")
    fc.append("[0:a][1:a]" + "".join(f"[d{i}]" for i in range(n)) +
              f"amix=inputs={2 + n}:normalize=0:duration=first,alimiter=limit=0.95[a]")
    run(["ffmpeg", "-y", "-i", str(WORK / "concat.mp4"), "-i", str(WORK / "bgm.wav"), "-i", str(WORK / "sfx.wav"),
         "-filter_complex", ";".join(fc), "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac",
         "-b:a", "192k", "-movflags", "+faststart", str(OUT / "video.mp4")])


# ---------- 12. サムネイル ----------
def thumbnail(title, F):
    lns = split_lines(title, 11)[:3]
    vf = "scale=1280:-1,crop=1280:720,eq=brightness=-0.15"
    y0 = 360 - 60 * len(lns)
    for k, ln in enumerate(lns):
        tf = WORK / f"thumb{k}.txt"
        tf.write_text(ln, encoding="utf-8")
        vf += (f",drawtext=fontfile={F}:textfile='{tf}':fontsize=96:fontcolor=0xFFE14D:borderw=8:"
               f"bordercolor=black:x=(w-text_w)/2:y={y0 + k * 120}")
    run(["ffmpeg", "-y", "-ss", "1.0", "-i", str(OUT / "video.mp4"), "-frames:v", "1", "-vf", vf,
         "-q:v", "3", str(OUT / "thumbnail.jpg")])


def preflight():
    """Geminiを使う前に、後工程で必要なものがそろっているか確認する(失敗なら無駄な呼び出しをしない)"""
    print("0) 事前チェック（Geminiは使いません）")
    def step(name, fn):
        try:
            r = fn()
            print(f"   OK: {name}")
            return r
        except Fail as e:
            raise Fail(f"【事前チェック失敗】{name}: {e}（Geminiは使っていません）")
        except Exception as e:
            raise Fail(f"【事前チェック失敗】{name}: {e}（Geminiは使っていません）")
    if not os.environ.get("GEMINI_API_KEY"):
        raise Fail("【事前チェック失敗】GEMINI_API_KEY が設定されていません")
    F = step("日本語フォント", font)
    tf = WORK / "pf.txt"
    tf.write_text("事前チェック「テスト」・ー", encoding="utf-8")
    step("動画合成(字幕の描画)", lambda: run(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=black:s=320x120", "-vf",
         f"drawtext=fontfile={F}:textfile='{tf}':fontsize=30:fontcolor=white", "-frames:v", "1", str(WORK / "pf.png")]))
    def vv():
        sp, _ = pick_speaker()
        return tts("事前チェックです。", sp, WORK / "pf.wav")
    step("VOICEVOX(音声合成)", vv)
    try:
        r = requests.get("https://images-api.nasa.gov/search", headers=UA, timeout=30,
                         params={"q": "nebula", "media_type": "image", "page_size": 1})
        print("   OK: NASA素材ライブラリ" if r.status_code == 200 else f"   警告: NASAが応答しません({r.status_code})→背景のみで作成します")
    except Exception as e:
        print("   警告: NASAに接続できません→背景のみで作成します:", e)
    return F


def main():
    OUT.mkdir(exist_ok=True); WORK.mkdir(exist_ok=True); DATA.mkdir(exist_ok=True)
    hist_path = DATA / "history.json"
    history = json.loads(hist_path.read_text(encoding="utf-8")) if hist_path.exists() else []
    F = preflight()

    pend_path = DATA / "pending.json"
    pend = None
    if pend_path.exists():
        try:
            pend = json.loads(pend_path.read_text(encoding="utf-8"))
        except Exception:
            pend = None
    if pend and pend.get("tries", 0) < 2:
        topic, script, src = pend["topic"], pend["script"], pend["src"]
        pend["tries"] = pend.get("tries", 0) + 1
        pend_path.write_text(json.dumps(pend, ensure_ascii=False), encoding="utf-8")
        print("前回の台本を再利用します（Geminiは使いません）:", topic)
    else:
        print("1) テーマ選定"); t = pick_topic(history); topic = t["topic"]; angle = t.get("angle", "")
        print("   ", topic, "/", angle)
        print("2) 資料取得"); src = wiki_any([t["wiki_query"], topic]); print("   ", src["title"], src["url"])
        print("3) 台本作成と事実確認")
        script, fb = None, ""
        for attempt in range(3):
            sc = write_script(topic, angle, src, fb)
            chk = fact_check(sc, src)
            if chk.get("ok"):
                script = sc
                break
            fb = " / ".join(chk.get("problems", []))
            print("   事実確認NG→再生成:", fb)
        else:
            print("   3回確認しても指摘が残るため、指摘箇所を資料の範囲に自動修正します")
            script = repair_script(sc, src, fb)
            script["check_notes"] = fb
        pend_path.write_text(json.dumps({"topic": topic, "script": script, "src": src, "tries": 1},
                                        ensure_ascii=False), encoding="utf-8")
        git_push("台本を一時保存")
    scenes = script["scenes"]
    for sc in scenes:
        sc["narration"] = clean(sc["narration"]); sc["emphasis"] = clean(sc["emphasis"])
    script["titles"] = [clean(x) for x in script["titles"]]
    script["description"] = clean(script.get("description", ""))
    script["pinned_comment"] = clean(script.get("pinned_comment", ""))

    print("4) ナレーション生成")
    speaker, vname = pick_speaker()
    items, used, used_nasa, credits = [], set(), set(), []
    for i, sc in enumerate(scenes):
        wav = WORK / f"s{i}.wav"
        dur = tts(sc["narration"], speaker, wav)
        bg = None
        p = pexels(sc["pexels_query"], used)
        if p:
            bg = WORK / f"bg{i}.mp4"
            try:
                download(p[1], bg); credits.append(f"Pexels: {p[2]} (video {p[0]})")
            except Exception as e:
                print("   Pexels DL失敗:", e); bg = None
        if not bg:
            for q in dict.fromkeys([sc.get("nasa_query"), sc.get("pexels_query")]):
                if not q:
                    continue
                n = nasa_media(q, used_nasa)
                if n:
                    ext = ".mp4" if n[2] == "video" else ".jpg"
                    bg = WORK / f"bg{i}{ext}"
                    try:
                        download(n[1], bg); credits.append(f"NASA: {n[3]} https://images.nasa.gov/details/{n[0]}")
                        break
                    except Exception as e:
                        print("   NASA DL失敗:", e); bg = None
        print(f"   シーン{i}: {'素材あり' if bg else '背景のみ'} ({sc.get('nasa_query')})")
        items.append((sc, bg, wav, dur))
    voice_total = sum(d for *_, d in items)
    print(f"   ナレーション合計 {voice_total:.1f} 秒")

    print("5) シーン合成")
    files, starts, t0 = [], [], 0.0
    for i, (sc, bg, wav, dur) in enumerate(items):
        f, total = render_scene(i, sc, bg, wav, dur, F)
        files.append(f); starts.append(t0); t0 += total
    print("6) 全体合成"); assemble(files, starts, t0)
    print("7) サムネイル"); thumbnail(script["titles"][0], F)

    credit_voice = f"VOICEVOX:{vname}"
    md = [f"# {script['titles'][0]}", "", "## タイトル案"] + [f"- {x}" for x in script["titles"]]
    md += ["", "## 概要欄（コピーして使用）", script["description"], "",
           "出典: " + src["title"] + " (Wikipedia) " + src["url"],
           "音声: " + credit_voice, "映像・画像: NASA Image and Video Library（NASAが本動画を承認・推薦するものではありません） / BGM・効果音: 自動生成のオリジナル音",
           "※ナレーションはAI音声を使用しています。", "", " ".join(script["hashtags"]), "",
           "## 固定コメント案", script["pinned_comment"], "",
           "## 事実確認メモ（投稿前に目視確認してください）"] + [f"- {x}" for x in script.get("facts", [])]
    if script.get("check_notes"):
        md += ["", "## 要確認（自動チェックで指摘が残った点。投稿前に必ず確認）", script["check_notes"]]
    md += ["", "## 映像クレジット（投稿前に、NASAロゴ・人物・他社の表記が映っていないか目視確認）"] + [f"- {c}" for c in credits]
    md += ["", f"長さ(ナレーション): {voice_total:.1f}秒 / 合成後: {t0:.1f}秒"]
    (OUT / "metadata.md").write_text("\n".join(md), encoding="utf-8")
    (OUT / "title.txt").write_text(script["titles"][0], encoding="utf-8")
    history.append({"date": datetime.date.today().isoformat(), "topic": topic,
                    "title": script["titles"][0], "source": src["url"]})
    hist_path.write_text(json.dumps(history, ensure_ascii=False, indent=1), encoding="utf-8")
    pend_path.unlink(missing_ok=True)
    git_push("履歴更新")
    print("完了:", OUT / "video.mp4")


if __name__ == "__main__":
    try:
        main()
    except Fail as e:
        print(f"::error::【失敗】{e}"); sys.exit(1)
    except Exception:
        print("::error::【想定外のエラー】\n" + traceback.format_exc()); sys.exit(1)
