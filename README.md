# AccessLearn AI

Lectures become a searchable, connected knowledge base.

## Pieces
- `static/index.html`: the web console (works on its own: upload a transcript, get concepts, links, graph, JSON).
- `app.py`: Flask backend: video upload -> Whisper transcript -> Gemini concepts -> MySQL -> search/graph APIs.
- `schema.sql`: the six tables (Users, Lectures, Transcripts, Concepts, LectureConcepts, ConceptRelationships).

## Run the console only (no setup)
Open `static/index.html` in a browser. Click "New lecture", then "Load sample Java course".
Without Claude, analysis uses local keyword extraction; AI definitions, quiz and Ask-AI need an AI backend.

## Run the full backend
1. `pip install -r requirements.txt`
2. Create the database: `mysql -u root -p < schema.sql`
3. Copy `.env.example` to `.env` and fill in DB password, OPENAI_API_KEY (Whisper), GEMINI_API_KEY.
4. `python app.py`, then open http://localhost:5000

## API
| Method | Route | Purpose |
|---|---|---|
| POST | /api/lectures | form: title, video -> transcribe + extract + store |
| GET | /api/lectures | list lectures |
| GET | /api/lectures/<id> | transcript, concepts, linked lectures, video url |
| GET | /api/search?q=inheritance | timestamps + related concepts |
| GET | /api/graph | nodes and edges for the knowledge graph |
| PUT | /api/transcripts/<id> | save a corrected transcript line |

## Status
Backend is a hackathon starter and has not been run against live keys. Check the Gemini model name in `.env`
(`GEMINI_MODEL`) since model names change. Next step: point the console's upload and Ask panels at these routes.
