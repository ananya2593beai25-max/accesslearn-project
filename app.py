"""AccessLearn AI backend: upload -> Whisper -> Gemini -> MySQL -> search / graph APIs."""
import json, os, re, uuid
from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_from_directory
import mysql.connector

load_dotenv()
BASE = os.path.dirname(os.path.abspath(__file__))
UPLOADS = os.path.join(BASE, "uploads")
os.makedirs(UPLOADS, exist_ok=True)
app = Flask(__name__, static_folder="static", static_url_path="")


def db():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"), user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", ""), database=os.getenv("DB_NAME", "accesslearn"))


# ---------- AI helpers ----------
def transcribe(path):
    """Whisper: returns [(start_seconds, text), ...]"""
    from openai import OpenAI
    with open(path, "rb") as f:
        r = OpenAI().audio.transcriptions.create(
            model="whisper-1", file=f, response_format="verbose_json",
            timestamp_granularities=["segment"])
    get = lambda s, k: s[k] if isinstance(s, dict) else getattr(s, k)
    return [(float(get(s, "start")), get(s, "text").strip()) for s in r.segments]


def extract_concepts(title, segs):
    """Gemini: summary, level, key concepts with definitions, related concept pairs."""
    import google.generativeai as genai
    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
    model = genai.GenerativeModel(os.getenv("GEMINI_MODEL", "gemini-1.5-flash"))
    text = "\n".join(f"@{int(t)}: {x}" for t, x in segs)[:30000]
    prompt = (
        f"You analyse a lecture transcript for students. Title: {title}\n"
        'Return only JSON: {"summary": str (max 55 words), "level": "Beginner|Intermediate|Advanced", '
        '"concepts": [{"name": str (1-3 words, exactly as spoken), "definition": str (max 20 words)}] (8-12 items), '
        '"relationships": [[conceptName, conceptName]] (pairs of related concepts from your list)}\n\n'
        f"TRANSCRIPT:\n{text}")
    resp = model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
    return json.loads(resp.text)


def rx(name):
    return re.compile(r"\b" + r"\s+".join(map(re.escape, name.split())) + r"(?:es|s)?\b", re.I)


# ---------- API ----------
@app.get("/")
def home():
    return app.send_static_file("index.html")


@app.get("/videos/<path:name>")
def videos(name):
    return send_from_directory(UPLOADS, name)


@app.post("/api/lectures")
def upload_lecture():
    """multipart form: title, video (file). Optional: transcript (text file) to skip Whisper."""
    title = request.form.get("title", "Untitled lecture")
    video = request.files.get("video")
    if not video:
        return jsonify(error="video file required"), 400
    fname = f"{uuid.uuid4().hex}_{os.path.basename(video.filename)}"
    path = os.path.join(UPLOADS, fname)
    video.save(path)
    segs = transcribe(path)
    ai = extract_concepts(title, segs)

    con = db(); cur = con.cursor()
    cur.execute("INSERT INTO Lectures(title, video_file, summary, level, duration_sec) VALUES (%s,%s,%s,%s,%s)",
                (title, fname, ai.get("summary"), ai.get("level"), int(segs[-1][0]) + 30 if segs else 0))
    lid = cur.lastrowid
    cur.executemany("INSERT INTO Transcripts(lecture_id, start_sec, text) VALUES (%s,%s,%s)",
                    [(lid, t, x) for t, x in segs])
    ids = {}
    for c in ai.get("concepts", []):
        name = c["name"].strip()
        hits = [(t, x) for t, x in segs if rx(name).search(x)]
        if not hits:
            continue
        cur.execute("INSERT INTO Concepts(name, definition) VALUES (%s,%s) "
                    "ON DUPLICATE KEY UPDATE definition=COALESCE(definition, VALUES(definition))",
                    (name.lower(), c.get("definition")))
        cur.execute("SELECT id FROM Concepts WHERE name=%s", (name.lower(),))
        cid = cur.fetchone()[0]; ids[name.lower()] = cid
        cur.execute("INSERT INTO LectureConcepts(lecture_id, concept_id, first_sec, mentions) VALUES (%s,%s,%s,%s)",
                    (lid, cid, hits[0][0], len(hits)))
    for a, b in ai.get("relationships", []):
        a, b = a.lower(), b.lower()
        if a in ids and b in ids and a != b:
            lo, hi = sorted((ids[a], ids[b]))
            cur.execute("INSERT IGNORE INTO ConceptRelationships(concept_a, concept_b) VALUES (%s,%s)", (lo, hi))
    con.commit(); con.close()
    return jsonify(id=lid, concepts=len(ids), summary=ai.get("summary"), level=ai.get("level")), 201


@app.get("/api/lectures")
def list_lectures():
    con = db(); cur = con.cursor(dictionary=True)
    cur.execute("SELECT l.id, l.title, l.level, l.duration_sec, COUNT(lc.concept_id) AS concepts "
                "FROM Lectures l LEFT JOIN LectureConcepts lc ON lc.lecture_id=l.id GROUP BY l.id ORDER BY l.id")
    rows = cur.fetchall(); con.close()
    return jsonify(rows)


@app.get("/api/lectures/<int:lid>")
def lecture(lid):
    con = db(); cur = con.cursor(dictionary=True)
    cur.execute("SELECT * FROM Lectures WHERE id=%s", (lid,)); l = cur.fetchone()
    if not l:
        return jsonify(error="not found"), 404
    cur.execute("SELECT id, start_sec, text, corrected FROM Transcripts WHERE lecture_id=%s ORDER BY start_sec", (lid,))
    l["transcript"] = cur.fetchall()
    cur.execute("SELECT c.name, c.definition, lc.first_sec, lc.mentions FROM LectureConcepts lc "
                "JOIN Concepts c ON c.id=lc.concept_id WHERE lc.lecture_id=%s ORDER BY lc.mentions DESC", (lid,))
    l["concepts"] = cur.fetchall()
    cur.execute("SELECT o.id, o.title, COUNT(*) AS shared FROM LectureConcepts a "
                "JOIN LectureConcepts b ON a.concept_id=b.concept_id AND b.lecture_id<>a.lecture_id "
                "JOIN Lectures o ON o.id=b.lecture_id WHERE a.lecture_id=%s GROUP BY o.id ORDER BY shared DESC", (lid,))
    l["linked"] = cur.fetchall()
    l["video_url"] = f"/videos/{l['video_file']}" if l.get("video_file") else None
    con.close()
    return jsonify(l)


@app.get("/api/search")
def search():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify(results=[], related=[])
    like = f"%{q}%"
    con = db(); cur = con.cursor(dictionary=True)
    cur.execute("SELECT l.id AS lecture_id, l.title, t.start_sec, t.text FROM Transcripts t "
                "JOIN Lectures l ON l.id=t.lecture_id WHERE t.text LIKE %s ORDER BY l.id, t.start_sec", (like,))
    results = cur.fetchall()
    cur.execute("SELECT DISTINCT c2.name FROM Concepts c1 "
                "JOIN ConceptRelationships r ON c1.id IN (r.concept_a, r.concept_b) "
                "JOIN Concepts c2 ON c2.id IN (r.concept_a, r.concept_b) AND c2.id<>c1.id WHERE c1.name LIKE %s", (like,))
    related = [r["name"] for r in cur.fetchall()]
    con.close()
    return jsonify(results=results, related=related)


@app.get("/api/graph")
def graph():
    con = db(); cur = con.cursor(dictionary=True)
    cur.execute("SELECT id, title FROM Lectures"); lec = cur.fetchall()
    cur.execute("SELECT id, name FROM Concepts"); con_ = cur.fetchall()
    cur.execute("SELECT lecture_id, concept_id FROM LectureConcepts"); lc = cur.fetchall()
    cur.execute("SELECT concept_a, concept_b FROM ConceptRelationships"); rel = cur.fetchall()
    con.close()
    return jsonify(lectures=lec, concepts=con_, lecture_concepts=lc, relationships=rel)


@app.put("/api/transcripts/<int:tid>")
def correct(tid):
    text = (request.get_json(silent=True) or {}).get("text", "").strip()
    if not text:
        return jsonify(error="text required"), 400
    con = db(); cur = con.cursor()
    cur.execute("UPDATE Transcripts SET text=%s, corrected=1 WHERE id=%s", (text, tid))
    con.commit(); con.close()
    return jsonify(ok=True)


if __name__ == "__main__":
    app.run(debug=True, port=5000)
