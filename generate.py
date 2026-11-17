# -*- coding: utf-8 -*-
"""宇宙・科学・人体の雑学Shorts 自動生成 (Phase 1)
台本→VOICEVOX音声→Pexels映像→字幕→BGM/効果音→MP4→サムネ→メタ情報
"""
import os, re, sys, json, time, random, math, pathlib, subprocess, datetime, traceback, unicodedata
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

【身近さ（最重要）】日本人の誰もが名前を知っている対象（月・太陽・地球・火星・ブラックホール・流れ星・天の川・国際宇宙ステーションなど）か、
日常の物や感覚（バナナ、1円玉、東京〜大阪の距離、1日の長さなど）と結びつけられる題材にする。
マニアックな天体名・型番・専門用語・研究者名が主役の題材は避ける。
その身近な対象について、日本人の多くが「知らなかった！」と驚く意外な事実を選ぶこと。
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
SPACE_WORDS = re.compile(r"宇宙|天体|惑星|恒星|銀河|太陽|月面|衛星|探査|望遠鏡|軌道|星雲|彗星|小惑星|ブラックホール|NASA|光年|天文")


def wiki(query):
    """検索上位5件のうち、宇宙・天文の記事だけを採用する(鉄道や人名など無関係な記事を避ける)"""
    api = "https://ja.wikipedia.org/w/api.php"
    s = requests.get(api, headers=UA, timeout=30, params={
        "action": "query", "list": "search", "srsearch": query, "format": "json", "srlimit": 5}).json()
    for h in s.get("query", {}).get("search", []):
        title = h["title"]
        e = requests.get(api, headers=UA, timeout=30, params={
            "action": "query", "prop": "extracts", "explaintext": 1, "titles": title, "format": "json"}).json()
        page = next(iter(e["query"]["pages"].values()))
        text = (page.get("extract") or "")[:8000]
        if len(text) < 200:
            continue
        if len(SPACE_WORDS.findall(text[:4000])) < 6:
            print(f"   除外(宇宙と無関係な記事): {title}")
            continue
        return {"title": title, "url": "https://ja.wikipedia.org/wiki/" + requests.utils.quote(title), "text": text}
    return None


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
- ナレーション合計 170〜210文字（約28〜33秒）。これより長くしない。自然な話し言葉の日本語。
- テンポ重視: 前置きや言い換えの繰り返しを入れず、1文ごとに新しい情報を出す。
- 構成: 冒頭2秒で驚かせる問いかけ → 意外な事実 → 理由の解説 → 余韻のある結び
- 【1シーン目の形】narrationは、最も意外な事実を1文で述べ、「〜なのを知っていましたか？」または「〜ことを知っていましたか？」で終える(20〜35文字。短く、冒頭の2秒で引き込む)。1シーン目はこの一文だけにする。
  1シーン目のemphasisは、その事実の核心を短い言葉にする(12文字以内)。この画面が動画のサムネイルになる。
- 【質の条件】日本の一般の大人がすでに知っている基本説明で尺を使わない。「みんなが思っていること」→「実は違う／もっと桁外れ」の落差を作る。
- 資料にある具体的な数字を2〜3個使い、身近なものに例えて実感させる。例えは資料の数値からの単純な換算に限り、断定しすぎない。
- 一般論や感想（「神秘的ですね」など）で字数を埋めない。1シーン1情報。
- 専門用語や天体の型番・固有名詞は、冒頭では使わない。使うときは、身近な言葉で言い換えてから出す。
- 数字は資料の値をそのまま使い、丸めるときは「約」を付ける。資料にない比較（〜より大きい、〜をも凌ぐ等）を事実として言わない。例えは「たとえるなら」と分かる形にする。
- 難しい専門用語には短い説明を添える。引き延ばしや繰り返しは禁止。
- 4〜6シーンに分割。1シーンのnarrationは20〜45文字。
- emphasis: 画面に大きく出すキーワード(8文字以内)。
- pexels_query: Pexelsで映像を探す英語の検索語(2〜3語、具体的)。
- nasa_query: NASAの画像・映像ライブラリで見つかりそうな英語の検索語(1〜3語。例: black hole, solar flare, Earth from orbit, Mars surface, nebula)。人物ではなく天体・地球・現象・探査機など、NASAが撮影した一般的な対象にする。そのシーンの内容に近い語にする。
- pixel: そのシーンの映像（ピクセルアート）の指定。type は次のどれか:
  single(aの天体を1つ見せる) / orbit(aの周りをbが回る。例: a=earth,b=moon) / compare(aとbの大きさ比べ。太陽・惑星・月だけ) / travel(ロケットがaへ向かう。距離や到達の話)。
  a と b は次の名前から選ぶ: sun, mercury, venus, earth, moon, mars, jupiter, saturn, uranus, neptune, black_hole, rocket, satellite, comet, galaxy, asteroid, meteor。
  場面の内容に合うものを選ぶ。1シーン目は必ず type=single。同じ指定を連続させない。内容に合う名前がなければ、a を空にする（星空だけの背景になる）。無理に当てはめない。
  流れ星・隕石の話は a=meteor、彗星は a=comet、ロケットの打ち上げは a=rocket を使う。
- titles: クリックしたくなるタイトル3案(各30文字以内。専門用語や数字の羅列だけにせず、誰でも気になる疑問や驚きの形にする。誤字・誤変換がないか確認する)
- description: 概要欄(200字程度)  hashtags: 5個(#付き)  pinned_comment: 固定コメント案
- facts: 台本で述べた事実の短いリスト(各々資料のどこに基づくか分かる形で)
{('前回の指摘(必ず修正): ' + feedback) if feedback else ''}
JSONのみで返す:
{{"titles":["","",""],"scenes":[{{"narration":"","emphasis":"","pexels_query":"","nasa_query":"","pixel":{{"type":"","a":"","b":""}}}}],
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
# ---------- ピクセルアート映像(自作・無料・著作権の心配なし) ----------
PX_OK = False
for _extra in (None, [], ["--break-system-packages"]):  # None=そのまま試す。無ければ自動でインストール
    if _extra is not None:
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "pillow", "numpy", *_extra],
                       capture_output=True)
    try:
        import numpy as np
        from PIL import Image
        PX_OK = True
        break
    except ImportError:
        continue

PX_W, PX_H, PX_FPS = 135, 240, 15
PX_BG = (6, 8, 26)
VISUAL_MODE = os.environ.get("VISUAL_MODE", "pixel")  # pixel=ピクセルアート / nasa=NASA素材
PX_NAMES = {"sun": "太陽", "mercury": "水星", "venus": "金星", "earth": "地球", "moon": "月", "mars": "火星",
            "jupiter": "木星", "saturn": "土星", "uranus": "天王星", "neptune": "海王星", "black_hole": "ブラックホール",
            "rocket": "ロケット", "satellite": "人工衛星", "comet": "彗星", "galaxy": "銀河", "asteroid": "小惑星",
            "meteor": "流れ星"}
# 直径(km)。大きさ比べは、この表から正確な倍率を計算する
PX_DIAM = {"sun": 1392700, "mercury": 4879, "venus": 12104, "earth": 12742, "moon": 3474, "mars": 6779,
           "jupiter": 139820, "saturn": 116460, "uranus": 50724, "neptune": 49244}
_PAT = {
    "rocket": (["...WW...", "..WWWW..", ".WWBBWW.", ".WWBBWW.", ".WWWWWW.", "WWRRRRWW", "W.RRRR.W", "..R..R.."],
               {"W": (235, 235, 240), "B": (80, 160, 255), "R": (220, 60, 60)}),
    "satellite": (["BBB.G.BBB", "BBB.G.BBB", "BBBGGGBBB", "BBB.G.BBB", "BBB.G.BBB"],
                  {"B": (60, 110, 200), "G": (205, 205, 210)}),
}
_SPR = {}


def _snoise(size, grid, seed):
    rng = np.random.default_rng(seed)
    g = Image.fromarray((rng.random((grid, grid)) * 255).astype("uint8")).resize((size, size), Image.BICUBIC)
    return np.asarray(g) / 255.0


def _rgba(col, mask):
    out = np.zeros(col.shape[:2] + (4,), np.uint8)
    out[..., :3] = np.clip(col, 0, 255)
    out[..., 3] = np.where(mask, 255, 0)
    return Image.fromarray(out, "RGBA")


def _planet(name, r):
    n = 2 * r + 1
    seed = sum(map(ord, name))
    yy, xx = np.mgrid[0:n, 0:n]
    dx, dy = xx - r, yy - r
    d = np.hypot(dx, dy)
    ns, ns2 = _snoise(n, 5, seed), _snoise(n, 9, seed + 1)
    col = np.zeros((n, n, 3), float)
    if name == "earth":
        col[:] = (47, 111, 219)
        col[(ns > 0.52) & (np.hypot(dx + 3, dy - 2) < r * 0.85)] = (70, 170, 90)
    elif name == "moon":
        col[:] = (190, 190, 195); col[ns2 > 0.78] = (140, 140, 148)
    elif name == "mars":
        col[:] = (205, 95, 55); col[ns > 0.55] = (150, 62, 38); col[dy < -r * 0.78] = (240, 240, 245)
    elif name == "mercury":
        col[:] = (150, 140, 130); col[ns2 > 0.75] = (110, 102, 95)
    elif name == "venus":
        col[:] = (232, 200, 130); col[ns > 0.55] = (210, 170, 100)
    elif name == "uranus":
        col[:] = (130, 212, 222); col[ns > 0.6] = (110, 190, 205)
    elif name == "neptune":
        col[:] = (60, 92, 222); col[ns > 0.58] = (90, 130, 240)
    elif name in ("jupiter", "saturn"):
        bands = (np.sin(dy / max(r, 1) * 9 + ns * 2.5) + 1) / 2
        c1, c2 = ((226, 190, 150), (172, 120, 84)) if name == "jupiter" else ((236, 214, 160), (200, 168, 112))
        col[:] = np.array(c1)[None, None, :] * bands[..., None] + np.array(c2)[None, None, :] * (1 - bands[..., None])
        if name == "jupiter":
            spot = (((dx - r * 0.3) / (r * 0.28 + 0.5)) ** 2 + ((dy - r * 0.32) / (r * 0.17 + 0.5)) ** 2) < 1
            col[spot] = (200, 80, 60)
    elif name == "sun":
        col[:] = (255, 190, 40); col[ns > 0.5] = (255, 225, 90)
    if name != "sun":
        k = (dx + dy) / (2 * r + 1e-9)
        col *= (1.12 - 0.40 * (k + 0.5))[..., None]
    col[d > r - 1.2] *= 0.82
    return _rgba(col, d <= r)


def _ring_layer(n, r, rx, ry, c_in, c_out, front):
    yy, xx = np.mgrid[0:n, 0:n]
    dx, dy = xx - r, yy - r
    e = (dx / max(rx, 1)) ** 2 + (dy / max(ry, 1)) ** 2
    m = (e >= 0.5) & (e <= 1.0) & ((dy > 0) if front else (dy <= 0))
    t = np.clip((e - 0.5) / 0.5, 0, 1)[..., None]
    col = np.array(c_in)[None, None, :] * (1 - t) + np.array(c_out)[None, None, :] * t
    return _rgba(col, m)


def _compose(layers):
    base = layers[0].copy()
    for im in layers[1:]:
        base.alpha_composite(im)
    return base


def _make_sprite(name, r):
    if name in _PAT:
        rows, pal = _PAT[name]
        im = Image.new("RGBA", (len(rows[0]), len(rows)), (0, 0, 0, 0)); px = im.load()
        for y, row in enumerate(rows):
            for x, ch in enumerate(row):
                if ch in pal:
                    px[x, y] = pal[ch] + (255,)
        s = max(1, r // 5)
        return im.resize((im.width * s, im.height * s), Image.NEAREST)
    n = 2 * r + 1
    if name == "saturn":
        rb = max(2, int(r * 0.62))
        body = _planet("saturn", rb)
        canvas = Image.new("RGBA", (n, n), (0, 0, 0, 0))
        back = _ring_layer(n, r, r, max(1, int(r * 0.28)), (150, 130, 100), (215, 195, 150), False)
        front = _ring_layer(n, r, r, max(1, int(r * 0.28)), (150, 130, 100), (215, 195, 150), True)
        canvas.alpha_composite(back)
        canvas.alpha_composite(body, (r - rb, r - rb))
        canvas.alpha_composite(front)
        return canvas
    if name == "black_hole":
        rc = max(2, int(r * 0.5))
        canvas = Image.new("RGBA", (n, n), (0, 0, 0, 0))
        back = _ring_layer(n, r, r, max(1, int(r * 0.32)), (255, 235, 150), (255, 120, 30), False)
        front = _ring_layer(n, r, r, max(1, int(r * 0.32)), (255, 235, 150), (255, 120, 30), True)
        yy, xx = np.mgrid[0:n, 0:n]
        d = np.hypot(xx - r, yy - r)
        core = _rgba(np.zeros((n, n, 3)), d <= rc)
        halo = _rgba(np.full((n, n, 3), (255, 230, 170), float), (d > rc) & (d <= rc + 1.2))
        canvas.alpha_composite(back); canvas.alpha_composite(halo); canvas.alpha_composite(core)
        canvas.alpha_composite(front)
        return canvas
    if name == "galaxy":
        arr = np.zeros((n, n, 4), np.uint8)
        rng = np.random.default_rng(11)
        for arm in (0, 1):
            for t in np.linspace(0.05, 1, 320):
                ang = arm * math.pi + t * 3 * math.pi
                x = int(r + t * r * math.cos(ang) + rng.integers(-1, 2))
                y = int(r + t * r * 0.55 * math.sin(ang) + rng.integers(-1, 2))
                if 0 <= x < n and 0 <= y < n:
                    c = np.array((255, 235, 170)) * (1 - t) + np.array((120, 170, 255)) * t
                    arr[y, x] = (*c.astype(int), 255)
        yy, xx = np.mgrid[0:n, 0:n]
        arr[(np.hypot(xx - r, (yy - r) * 1.6) < max(2, r * 0.18))] = (255, 245, 200, 255)
        return Image.fromarray(arr, "RGBA")
    if name == "asteroid":
        rng = np.random.default_rng(5)
        vals = rng.random(8)
        yy, xx = np.mgrid[0:n, 0:n]
        dx, dy = xx - r, yy - r
        ang = np.mod(np.arctan2(dy, dx), 2 * np.pi)
        rad = np.interp(ang, np.linspace(0, 2 * np.pi, 9), np.append(vals, vals[0]))
        d = np.hypot(dx, dy)
        col = np.zeros((n, n, 3)); col[:] = (150, 135, 120)
        col[_snoise(n, 8, 3) > 0.7] = (110, 98, 88)
        return _rgba(col, d <= r * (0.62 + 0.38 * rad))
    if name == "comet":
        m = 4 * r + 1
        arr = np.zeros((m, m, 4), np.uint8)
        hx, hy, L = r, 3 * r, int(3.2 * r)
        for s in range(L):
            w = max(0, int(r * 0.9 * (1 - s / L)))
            a = int(255 * (1 - s / L))
            for k in range(-w, w + 1):
                x, y = hx + s + k, hy - s + k
                if 0 <= x < m and 0 <= y < m:
                    arr[y, x] = (200, 225, 255, a)
        yy, xx = np.mgrid[0:m, 0:m]
        arr[np.hypot(xx - hx, yy - hy) <= max(2, r * 0.6)] = (235, 245, 255, 255)
        return Image.fromarray(arr, "RGBA")
    if name == "meteor":
        m = 6 * r + 1
        arr = np.zeros((m, m, 4), np.uint8)
        hx, hy, L = r, 5 * r, int(5 * r)
        for k in range(L):
            f = 1 - k / L
            w = max(0, int(r * 0.35 * f))
            c = (255, int(150 + 100 * f), int(60 + 170 * f))
            for q in range(-w, w + 1):
                x, y = hx + k + q, hy - k + q
                if 0 <= x < m and 0 <= y < m:
                    arr[y, x] = (*c, int(255 * f ** 0.7))
        yy, xx = np.mgrid[0:m, 0:m]
        arr[np.hypot(xx - hx, yy - hy) <= max(2, r * 0.45)] = (255, 250, 230, 255)
        return Image.fromarray(arr, "RGBA")
    if name == "star":
        im = Image.new("RGBA", (5, 5), (0, 0, 0, 0)); px = im.load()
        for x, y in [(2, 0), (2, 1), (0, 2), (1, 2), (2, 2), (3, 2), (4, 2), (2, 3), (2, 4)]:
            px[x, y] = (255, 240, 150, 255)
        return im.resize((5 * max(1, r // 5), 5 * max(1, r // 5)), Image.NEAREST)
    return _planet(name, r)


PIXEL_FONT_URLS = ["https://github.com/google/fonts/raw/main/ofl/dotgothic16/DotGothic16-Regular.ttf",
                   "https://raw.githubusercontent.com/google/fonts/main/ofl/dotgothic16/DotGothic16-Regular.ttf"]


def get_pixel_font():
    """日本語のドット文字(DotGothic16 / SIL OFL・商用利用可)を取得する。失敗したらNone"""
    path = WORK / "DotGothic16-Regular.ttf"
    if path.exists() and path.stat().st_size > 100000:
        return str(path.resolve())
    for u in PIXEL_FONT_URLS:
        try:
            r = requests.get(u, headers=UA, timeout=60)
            if r.status_code == 200 and len(r.content) > 100000 and r.content[:4] in (b"\x00\x01\x00\x00", b"true", b"OTTO"):
                path.write_bytes(r.content)
                return str(path.resolve())
        except Exception as e:
            print("   フォント取得失敗:", e)
    return None


def sprite(name, r):
    key = (name, r)
    if key not in _SPR:
        _SPR[key] = _make_sprite(name, r)
    return _SPR[key]


def blit(arr, spr, cx, cy):
    a = np.asarray(spr)
    h, w = a.shape[:2]
    x0, y0 = int(cx - w // 2), int(cy - h // 2)
    xs, ys = max(0, -x0), max(0, -y0)
    xe, ye = min(w, PX_W - x0), min(h, PX_H - y0)
    if xe <= xs or ye <= ys:
        return
    src = a[ys:ye, xs:xe]
    reg = arr[y0 + ys:y0 + ye, x0 + xs:x0 + xe]
    al = (src[..., 3:4] / 255.0)
    reg[:] = (src[..., :3] * al + reg * (1 - al)).astype(np.uint8)


def _stars(n=70):
    rnd = random.Random(7)
    return [(rnd.randrange(PX_W), rnd.randrange(PX_H), rnd.random() * 6.28) for _ in range(n)]


def px_spec(raw, first):
    """AIが選んだ映像の指定を検証する(おかしければ、星空だけの背景にする)"""
    if not isinstance(raw, dict):
        return {"type": "none"}
    typ = str(raw.get("type", "single"))
    a = raw.get("a") if raw.get("a") in PX_NAMES else None
    b = raw.get("b") if raw.get("b") in PX_NAMES else None
    if not a:
        return {"type": "none"}
    if first:
        return {"type": "single", "a": a, "first": True}
    if typ == "compare" and b and a in PX_DIAM and b in PX_DIAM and a != b:
        return {"type": "compare", "a": a, "b": b}
    if typ == "orbit" and b and a != b and a not in _PAT and b not in _PAT:
        return {"type": "orbit", "a": a, "b": b}
    if typ == "travel" and a not in _PAT:
        return {"type": "travel", "a": a}
    return {"type": "single", "a": a}


def px_labels(spec):
    """文字は、くっきり表示するため、動画合成の段階で重ねる: (文字, 中心x, y, サイズ, 色)"""
    typ, a, b = spec["type"], spec.get("a"), spec.get("b")
    if typ == "single" and not spec.get("first"):
        return [(PX_NAMES[a], 540, 1110, 56, "white")]
    if typ == "compare":
        da, db = PX_DIAM[a], PX_DIAM[b]
        big, small = (a, b) if da >= db else (b, a)
        n = PX_DIAM[big] / PX_DIAM[small]
        out = [(PX_NAMES[a], 36 * 8, 1100, 52, "white"), (PX_NAMES[b], 100 * 8, 1100, 52, "white")]
        if n >= 1.5:
            nt = f"{n:.1f}" if n < 10 else f"{round(n)}"
            out.append((f"直径は{PX_NAMES[big]}が{PX_NAMES[small]}の約{nt}倍", 540, 1190, 48, "0xFFE14D"))
        return out
    return []


def px_frame(spec, t, stars):
    arr = np.empty((PX_H, PX_W, 3), np.uint8)
    arr[:] = PX_BG
    typ, a, b = spec["type"], spec.get("a"), spec.get("b")
    speed = 22 if typ == "travel" else 3
    for sx, sy, ph in stars:
        v = 140 + int(100 * math.sin(t * 2.2 + ph))
        arr[int(sy + t * speed) % PX_H, sx] = (v, v, min(255, v + 40))
    if typ == "single" and a in ("meteor", "comet"):
        r = 10 if a == "meteor" else 12
        ph = (t % 2.6) / 2.6
        y0, y1 = (110, 160) if spec.get("first") else (80, 160)
        blit(arr, sprite(a, r), 150 + (-15 - 150) * ph, y0 + (y1 - y0) * ph)
    elif typ == "single" and a == "rocket":
        ph = (t % 3.0) / 3.0
        ry = 158 - 80 * ph
        blit(arr, sprite("rocket", 15), 67, ry)
        fl = 4 + (int(t * 12) % 2) * 3
        y1 = int(ry) + 12
        arr[y1:y1 + fl, 64:70] = (255, 190, 60)
        arr[y1:y1 + max(1, fl - 2), 65:69] = (255, 245, 170)
    elif typ == "single" and a == "satellite":
        ph = (t % 6.0) / 6.0
        blit(arr, sprite(a, 20), 15 + 105 * ph, (140 if spec.get("first") else 105) + int(round(2 * math.sin(t * 2))))
    elif typ == "single":
        r = 24 if spec.get("first") else 30
        cy = 140 if spec.get("first") else 105
        blit(arr, sprite(a, r), PX_W // 2, cy + int(round(2 * math.sin(t * 1.6))))
    elif typ == "orbit":
        cx, cy, orr = 67, 112, 46
        for deg in range(0, 360, 6):
            x, y = int(cx + orr * math.cos(math.radians(deg))), int(cy + orr * math.sin(math.radians(deg)))
            if 0 <= x < PX_W and 0 <= y < PX_H:
                arr[y, x] = (70, 80, 130)
        ra = 18
        rb = 6
        if a in PX_DIAM and b in PX_DIAM:
            rb = int(min(9, max(2, round(ra * PX_DIAM[b] / PX_DIAM[a]))))
        blit(arr, sprite(a, ra), cx, cy)
        ang = t * 2 * math.pi / 5.0 - math.pi / 2
        blit(arr, sprite(b, rb), cx + orr * math.cos(ang), cy + orr * math.sin(ang))
    elif typ == "compare":
        big = max(PX_DIAM[a], PX_DIAM[b])
        for nm, cx in ((a, 36), (b, 100)):
            r = max(1, int(round(28 * PX_DIAM[nm] / big)))
            blit(arr, sprite(nm, r), cx, 112 + int(round(1.5 * math.sin(t * 1.6 + cx))))
    elif typ == "travel":
        blit(arr, sprite(a, 18), 67, 86)
        prog = min(1.0, t / 5.0)
        ry = 158 - (158 - 118) * (1 - (1 - prog) ** 2)
        blit(arr, sprite("rocket", 15), 67, ry)
        fl = 4 + (int(t * 12) % 2) * 3
        y1 = int(ry) + 12
        arr[y1:y1 + fl, 64:70] = (255, 190, 60)
        arr[y1:y1 + max(1, fl - 2), 65:69] = (255, 245, 170)
    return arr


def px_render(spec, dur, path):
    """ピクセルの動画(音なし)を作る。低解像度のまま送り、ffmpegで8倍に拡大してドットをくっきり保つ"""
    stars = _stars()
    n = int(math.ceil(dur * PX_FPS)) + 1
    logf = open(str(path) + ".log", "w")
    p = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                          "-s", f"{PX_W}x{PX_H}", "-r", str(PX_FPS), "-i", "-",
                          "-vf", "scale=1080:1920:flags=neighbor,fps=30,format=yuv420p",
                          "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", str(path)],
                         stdin=subprocess.PIPE, stderr=logf)
    try:
        for k in range(n):
            p.stdin.write(px_frame(spec, k / PX_FPS, stars).tobytes())
        p.stdin.close()
    except BrokenPipeError:
        pass
    p.wait()
    logf.close()
    if p.returncode != 0:
        raise Fail("ピクセル映像の作成に失敗: " + pathlib.Path(str(path) + ".log").read_text()[-500:])
    return px_labels(spec) if spec["type"] != "none" else []


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
    res = []
    for c in out:  # 長すぎる区切りは、2行に収まるよう半分ずつに分ける
        if len(c) > 28:
            res += split_lines(c, -(-len(c) // 2))
        else:
            res.append(c)
    return res



def probe(path):
    o = run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
             "stream=width,height:format=duration", "-of", "json", str(path)])
    j = json.loads(o)
    st = j["streams"][0]
    return int(st["width"]), int(st["height"]), float(j.get("format", {}).get("duration") or 0)

def render_scene(i, sc, bg, wav, dur, F, pixel=False, labels=None):
    total = dur + 0.15
    elines = split_lines(sc["emphasis"], 7 if i == 0 else 8)
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
    if bg and not pixel:
        w0, h0, d0 = probe(bg)
        land = w0 > h0
        if not is_img and d0 > total + 8:
            ss = ["-ss", f"{random.uniform(3, d0 - total - 1):.2f}"]
    if pixel:
        base = "[0:v]setsar=1,fps=30,"
    elif land:
        fgw = "scale=w='trunc(1080*(1+0.012*t)/2)*2':h=-2:eval=frame" if is_img else "scale=1080:-2"
        base = ("[0:v]split=2[a][b];[a]scale=1242:2208:force_original_aspect_ratio=increase,"
                "crop=1080:1920,boxblur=30:5,eq=brightness=-0.18[bg];"
                f"[b]{fgw}[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,fps=30,setsar=1,")
    else:
        base = ("[0:v]scale=1242:2208:force_original_aspect_ratio=increase,"
                "crop=1080:1920:x='(iw-1080)/2+sin(t*0.8)*40':y='(ih-1920)/2+cos(t*0.6)*40',"
                "fps=30,setsar=1,")
    vf = base + f"drawbox=x=0:y=0:w=iw:h=ih:color=black@{0.08 if pixel else 0.28}:t=fill"
    if i == 0:
        y0 = 430
        for k, ef in enumerate(efs):
            vf += (f",drawtext=fontfile={F}:textfile='{ef}':fontsize=124:fontcolor=0xFFE14D:borderw=10:"
                   f"bordercolor=black:x=(w-text_w)/2:y={y0 + k * 150}")
        tg = WORK / "s0_tag.txt"
        tg.write_text("知っていましたか？", encoding="utf-8")
        vf += (f",drawtext=fontfile={F}:textfile='{tg}':fontsize=84:fontcolor=white:borderw=8:"
               f"bordercolor=black:x=(w-text_w)/2:y={y0 + len(efs) * 150 + 20}")
    else:
        for k, ef in enumerate(efs):
            vf += (f",drawtext=fontfile={F}:textfile='{ef}':fontsize=104:fontcolor=0xFFE14D:borderw=8:"
                   f"bordercolor=black:x=(w-text_w)/2:y={260 + k * 124}:alpha='min(1,t/0.25)'")
    for li, (ltxt, lcx, ly, lsz, lcol) in enumerate(labels or []):
        lf = WORK / f"s{i}_l{li}.txt"
        lf.write_text(ltxt, encoding="utf-8")
        vf += (f",drawtext=fontfile={F}:textfile='{lf}':fontsize={lsz}:fontcolor={lcol}:borderw=5:"
               f"bordercolor=black:x={lcx}-text_w/2:y={ly}")
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
    elif pixel:
        inp = ["-i", str(bg)]
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
    """動画の冒頭の画面(縦 1080x1920)をそのままサムネイル画像にする"""
    run(["ffmpeg", "-y", "-ss", "0.6", "-i", str(OUT / "video.mp4"), "-frames:v", "1", "-q:v", "2",
         str(OUT / "thumbnail.jpg")])


def preflight():
    """Geminiを使う前に、後工程で必要なものがそろっているか確認する(失敗なら無駄な呼び出しをしない)"""
    print("プログラムのバージョン: ピクセルアート版 v4 / 映像モード:", VISUAL_MODE)
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
    if VISUAL_MODE == "pixel":
        pf = get_pixel_font()
        if pf:
            F = pf
            print("   OK: ドット文字フォント(DotGothic16)")
        else:
            print("   警告: ドット文字フォントを取得できません→通常のフォントで作成します")
    tf = WORK / "pf.txt"
    tf.write_text("事前チェック「テスト」・ー", encoding="utf-8")
    step("動画合成(字幕の描画)", lambda: run(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=black:s=320x120", "-vf",
         f"drawtext=fontfile={F}:textfile='{tf}':fontsize=30:fontcolor=white", "-frames:v", "1", str(WORK / "pf.png")]))
    def vv():
        sp, _ = pick_speaker()
        return tts("事前チェックです。", sp, WORK / "pf.wav")
    step("VOICEVOX(音声合成)", vv)
    if VISUAL_MODE == "pixel":
        if PX_OK:
            step("ピクセルアート描画", lambda: [px_frame({"type": t, "a": "earth", "b": "moon"}, 0.5, _stars())
                                            for t in ("single", "orbit", "compare", "travel")])
        else:
            raise Fail("【事前チェック失敗】ピクセル描画の部品(Pillow/numpy)が入りません（Geminiは使っていません）。"
                       "ワークフローの「pip install requests」の行を「pip install requests pillow numpy」に変えてください")
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
    px_labels_map = {}
    for i, sc in enumerate(scenes):
        wav = WORK / f"s{i}.wav"
        dur = tts(sc["narration"], speaker, wav)
        if VISUAL_MODE == "pixel":
            spec = px_spec(sc.get("pixel"), i == 0)
            pxp = WORK / f"px{i}.mp4"
            px_labels_map[i] = px_render(spec, dur + 0.5, pxp)
            print(f"   シーン{i}: ピクセルアート {spec}")
            items.append((sc, pxp, wav, dur))
            continue
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
    if voice_total > 40:
        print("   注意: 目標の30秒前後より長めです。次回の改善の参考にしてください")

    print("5) シーン合成")
    files, starts, t0 = [], [], 0.0
    for i, (sc, bg, wav, dur) in enumerate(items):
        f, total = render_scene(i, sc, bg, wav, dur, F, pixel=(i in px_labels_map), labels=px_labels_map.get(i))
        files.append(f); starts.append(t0); t0 += total
    print("6) 全体合成"); assemble(files, starts, t0)
    print("7) サムネイル"); thumbnail(script["titles"][0], F)

    credit_voice = f"VOICEVOX:{vname}"
    md = [f"# {script['titles'][0]}", "", "## タイトル案"] + [f"- {x}" for x in script["titles"]]
    md += ["", "## 概要欄（コピーして使用）", script["description"], "",
           "出典: " + src["title"] + " (Wikipedia) " + src["url"],
           "音声: " + credit_voice, ("映像: プログラムで描いたピクセルアート（イメージ図です。実際の見た目とは異なります） / BGM・効果音: 自動生成のオリジナル音"
            if px_labels_map else "映像・画像: NASA Image and Video Library（NASAが本動画を承認・推薦するものではありません） / BGM・効果音: 自動生成のオリジナル音"),
           "※ナレーションはAI音声を使用しています。", "", " ".join(script["hashtags"]), "",
           "## 固定コメント案", script["pinned_comment"], "",
           "## 事実確認メモ（投稿前に目視確認してください）"] + [f"- {x}" for x in script.get("facts", [])]
    if script.get("check_notes"):
        md += ["", "## 要確認（自動チェックで指摘が残った点。投稿前に必ず確認）", script["check_notes"]]
    if credits:
        md += ["", "## 映像クレジット（投稿前に、NASAロゴ・人物・他社の表記が映っていないか目視確認）"] + [f"- {c}" for c in credits]
    md += ["", "## サムネイルのヒント",
           "YouTubeの投稿画面でサムネイル(フレーム)を選ぶとき、動画の最初(0〜3秒)を選ぶと、大きな文字の問いかけ画面になります。"]
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
