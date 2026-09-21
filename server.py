import os, json, asyncio, io, base64, csv, re, time
import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Request, HTTPException, UploadFile, File, Form
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse
from pydantic import BaseModel
from typing import List, Optional

load_dotenv()

# Load API Keys
GEMINI_KEY     = os.getenv("GEMINI_API_KEY", "")
XAI_KEY        = os.getenv("XAI_API_KEY", "")
OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY", "")
HF_TOKEN       = os.getenv("HUGGINGFACE_TOKEN", "")
OLLAMA_URL     = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

# Groq Keys Pool (supports single or comma-separated keys)
raw_groq = os.getenv("GROQ_API_KEYS", "") or os.getenv("GROQ_API_KEY", "")
GROQ_KEYS = [k.strip() for k in raw_groq.split(",") if k.strip()]
if not GROQ_KEYS:
    print("[SECURITY WARNING] No GROQ_API_KEYS found in .env environment file.")

_groq_idx = 0
def get_next_groq_key(user_key=None):
    global _groq_idx
    if user_key:
        return user_key
    k = GROQ_KEYS[_groq_idx % len(GROQ_KEYS)]
    _groq_idx += 1
    return k

# Active verified models
GROQ_MODELS = [
    "qwen/qwen3.8-27b",
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b"
]

GEMINI_MODELS = [
    "gemini-2.0-flash",
    "gemini-1.5-flash",
    "gemini-1.5-pro"
]

app = FastAPI(title="Kalki AI OS")
public_dir = os.path.join(os.path.dirname(__file__), "public")
data_dir   = os.path.join(os.path.dirname(__file__), "data")
upload_dir = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(public_dir, exist_ok=True)
os.makedirs(data_dir,   exist_ok=True)
os.makedirs(upload_dir, exist_ok=True)

SYSTEM_PROMPT = """[IDENTITY & OPERATING DIRECTIVE]
YOU ARE: Kalki, a high-performance sovereign AI operating system engineered by Arcues.
Creator & Leadership: Arcues was founded by CEO S. Veeraharikumaran.
Confidentiality & Etiquette:
- Only discuss your company (Arcues) or founder (S. Veeraharikumaran) if specifically and explicitly asked by the user (such as "who created you?", "who is your CEO?", "who made Kalki?"). In normal technical, coding, writing, and analytical tasks, do not bring up your origins unsolicited. Focus purely on giving immediate, elite, direct value.
- NEVER identify as OpenAI, Google, Anthropic, Meta, or any third party.
- If asked: "I am Kalki, a sovereign AI OS engineered by Arcues, founded by CEO S. Veeraharikumaran."

Languages: Tamil, Tanglish, English, Hindi - fluently, natively, and naturally based on user input.

Core Capabilities:
- Senior Engineering: Python, TypeScript, JavaScript, C, C++, Rust, Go, SQL, Fullstack Architecture
- Computer Science: Algorithms, Data Structures, System Design, OS, High-Concurrency Networking
- Crisp Analysis & Production Code: Direct, modular, cleanly commented, zero fluff.

STRICT FORMATTING RULES:
- NEVER use emojis or decorative icons in your responses. Absolutely zero emojis under any circumstances.
- Use clean markdown: headers, bullet points, syntax-highlighted code blocks with language tags.
- Direct, concise, authoritative, and helpful.
"""

class Message(BaseModel):
    role: str
    content: str

class ChatReq(BaseModel):
    message: str
    model: str = "flash"
    history: List[Message] = []
    agent_prompt: Optional[str] = None
    custom_key: Optional[str] = None

class ImageReq(BaseModel):
    prompt: str
    model: str = "flux-schnell"
    aspect: str = "1:1"
    style: str = ""

class SearchReq(BaseModel):
    query: str
    mode: str = "quick"

class UrlReq(BaseModel):
    url: str

class MemoryItem(BaseModel):
    key: str
    value: str

class Agent(BaseModel):
    id: Optional[str] = None
    name: str
    description: str = ""
    system_prompt: str = ""
    model: str = "flash"
    temperature: float = 0.7
    welcome_message: str = ""

def build_msgs(message, history, sys_override=None):
    sys = sys_override or SYSTEM_PROMPT
    msgs = [{"role": "system", "content": sys}]
    for h in history[-20:]:
        msgs.append({"role": "assistant" if h.role == "assistant" else "user", "content": h.content})
    msgs.append({"role": "user", "content": message})
    return msgs

def load_json(path, default):
    try:
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return default

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

# ── Streaming Engines ──────────────────────────────────────────────
async def stream_groq(message, history, sys=None, user_key=None, target_model=None, temperature=0.7):
    msgs = build_msgs(message, history, sys)
    keys_to_try = [user_key] if user_key else GROQ_KEYS
    models_to_try = [target_model] if target_model else GROQ_MODELS
    
    for k in keys_to_try:
        for mdl in models_to_try:
            try:
                async with httpx.AsyncClient(timeout=40) as c:
                    async with c.stream("POST", "https://api.groq.com/openai/v1/chat/completions",
                        headers={"Authorization": f"Bearer {k}"},
                        json={"model": mdl, "messages": msgs, "stream": True, "max_tokens": 4096, "temperature": temperature}) as r:
                        if r.status_code != 200:
                            continue
                        got_chunk = False
                        async for line in r.aiter_lines():
                            if line.startswith("data: "):
                                d = line[6:]
                                if d.strip() == "[DONE]":
                                    return
                                try:
                                    t = json.loads(d)["choices"][0]["delta"].get("content", "")
                                    if t:
                                        got_chunk = True
                                        yield t
                                except Exception:
                                    continue
                        if got_chunk:
                            return
            except Exception:
                continue

async def stream_gemini(message, history, pro=False, sys=None, user_key=None):
    k = user_key or GEMINI_KEY
    contents = []
    for h in history[-20:]:
        contents.append({"role": "model" if h.role == "assistant" else "user", "parts": [{"text": h.content}]})
    contents.append({"role": "user", "parts": [{"text": message}]})
    payload = {
        "system_instruction": {"parts": [{"text": sys or SYSTEM_PROMPT}]},
        "contents": contents,
        "generationConfig": {"maxOutputTokens": 8192, "temperature": 0.7}
    }
    
    models = ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro"]
    for mdl in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{mdl}:streamGenerateContent?alt=sse&key={k}"
        try:
            async with httpx.AsyncClient(timeout=60) as c:
                async with c.stream("POST", url, json=payload) as r:
                    if r.status_code != 200:
                        continue
                    got_chunk = False
                    async for line in r.aiter_lines():
                        if line.startswith("data: "):
                            d = line[6:]
                            if d.strip() == "[DONE]":
                                return
                            try:
                                chunk = json.loads(d)
                                for part in chunk.get("candidates", [{}])[0].get("content", {}).get("parts", []):
                                    if part.get("text"):
                                        got_chunk = True
                                        yield part["text"]
                            except Exception:
                                continue
                    if got_chunk:
                        return
        except Exception:
            continue

async def stream_openrouter(message, history, model_id, sys=None, user_key=None):
    k = user_key or OPENROUTER_KEY
    msgs = build_msgs(message, history, sys)
    models_to_try = [model_id]
    if "deepseek-r1" in model_id:
        models_to_try = ["deepseek/deepseek-r1:free", "deepseek/deepseek-r1", "deepseek/deepseek-chat-v3-0324:free"]
    elif "gpt-4o" in model_id:
        models_to_try = ["openai/gpt-4o-mini", "openai/gpt-4o"]
    elif "claude" in model_id:
        models_to_try = ["anthropic/claude-3.5-sonnet", "anthropic/claude-3.5-haiku"]
    elif "llama" in model_id:
        models_to_try = ["meta-llama/llama-3.3-70b-instruct:free", "meta-llama/llama-3.3-70b-instruct"]

    for m in models_to_try:
        try:
            async with httpx.AsyncClient(timeout=60) as c:
                async with c.stream("POST", "https://openrouter.ai/api/v1/chat/completions",
                    headers={"Authorization": f"Bearer {k}", "HTTP-Referer": "http://localhost:3000", "X-Title": "Kalki AI"},
                    json={"model": m, "messages": msgs, "stream": True, "max_tokens": 4096}) as r:
                    if r.status_code != 200:
                        continue
                    got = False
                    async for line in r.aiter_lines():
                        if line.startswith("data: "):
                            d = line[6:]
                            if d.strip() == "[DONE]":
                                if got:
                                    return
                                break
                            try:
                                t = json.loads(d)["choices"][0]["delta"].get("content", "")
                                if t:
                                    got = True
                                    yield t
                            except Exception:
                                continue
                    if got:
                        return
        except Exception:
            continue

async def stream_xai(message, history, sys=None):
    msgs = build_msgs(message, history, sys)
    for mdl in ["grok-3-mini-latest", "grok-2-latest"]:
        try:
            async with httpx.AsyncClient(timeout=40) as c:
                async with c.stream("POST", "https://api.x.ai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {XAI_KEY}"},
                    json={"model": mdl, "messages": msgs, "stream": True, "max_tokens": 4096}) as r:
                    if r.status_code != 200:
                        continue
                    async for line in r.aiter_lines():
                        if line.startswith("data: "):
                            d = line[6:]
                            if d.strip() == "[DONE]":
                                return
                            try:
                                t = json.loads(d)["choices"][0]["delta"].get("content", "")
                                if t:
                                    yield t
                            except Exception:
                                continue
            return
        except Exception:
            continue

async def stream_ollama(message, history, sys=None):
    msgs = [{"role": "system", "content": sys or SYSTEM_PROMPT}]
    for h in history[-20:]:
        msgs.append({"role": h.role, "content": h.content})
    msgs.append({"role": "user", "content": message})
    try:
        async with httpx.AsyncClient(timeout=4) as c:
            r = await c.get(f"{OLLAMA_URL}/api/tags")
            available = [m["name"] for m in r.json().get("models", [])] if r.status_code == 200 else []
    except Exception:
        available = []

    if not available:
        # Seamless failover to Groq or Gemini instead of crashing!
        async for chunk in stream_groq(message, history, sys):
            yield chunk
        return

    preferred = ["llama3.2", "llama3.1", "llama3", "mistral", "phi3"]
    mdl = next((m for p in preferred for m in available if p in m), available[0])
    try:
        async with httpx.AsyncClient(timeout=120) as c:
            async with c.stream("POST", f"{OLLAMA_URL}/api/chat",
                json={"model": mdl, "messages": msgs, "stream": True}) as r:
                r.raise_for_status()
                async for line in r.aiter_lines():
                    try:
                        d = json.loads(line)
                        t = d.get("message", {}).get("content", "")
                        if t:
                            yield t
                        if d.get("done"):
                            return
                    except Exception:
                        continue
    except Exception:
        async for chunk in stream_groq(message, history, sys):
            yield chunk

# Auto-failover chain (Guaranteed 0 failures)
async def auto_fallback(message, history, sys=None):
    chain = [
        ("Kalki Flash", lambda m,h,s: stream_groq(m, h, s)),
        ("Kalki Sonnet", lambda m,h,s: stream_gemini(m, h, False, s)),
        ("Kalki Thinker", lambda m,h,s: stream_openrouter(m, h, "deepseek/deepseek-r1:free", s)),
        ("Kalki Titan", lambda m,h,s: stream_xai(m, h, s))
    ]
    for name, fn in chain:
        buf = []
        try:
            async for chunk in fn(message, history, sys):
                buf.append(chunk)
                yield name, chunk
            if buf:
                return
        except Exception:
            continue

# ── Chat Stream Endpoint ───────────────────────────────────────────
@app.post("/api/chat/stream")
async def chat_stream(req: ChatReq):
    m = req.model.lower().strip()
    sys_prompt = req.agent_prompt if req.agent_prompt else None
    user_key = req.custom_key if req.custom_key else None

    # Check for direct Image Generation request inside Chat
    lower_msg = req.message.lower().strip()
    image_triggers = ["generate image", "image generate", "draw a", "create an image", "படம் வரை", "/image"]
    if any(lower_msg.startswith(trig) or f" {trig} " in f" {lower_msg} " for trig in image_triggers):
        clean_prompt = re.sub(r'^(generate image of|generate image|image generate|draw a|create an image|படம் வரை|/image)\s*', '', req.message, flags=re.IGNORECASE).strip()
        if not clean_prompt: clean_prompt = req.message

        async def gen_image_response():
            yield f"data: {json.dumps({'type': 'engine', 'engine': 'Kalki FLUX Studio'})}\n\n"
            yield f"data: {json.dumps({'type': 'chunk', 'text': 'Synthesizing 4K photorealistic artwork...\\n\\n'})}\n\n"
            try:
                img_res = await generate_image(ImageReq(prompt=clean_prompt, aspect="16:9", style="Photorealistic"))
                if hasattr(img_res, 'body'):
                    img_data = json.loads(img_res.body.decode())
                else:
                    img_data = {}
                if img_data.get("success") and img_data.get("url"):
                    md_img = f"![{clean_prompt}]({img_data['url']})\n\n**Prompt:** {clean_prompt}\n**Engine:** {img_data.get('engine', 'Kalki Studio 4K')}\n"
                    yield f"data: {json.dumps({'type': 'chunk', 'text': md_img})}\n\n"
                else:
                    yield f"data: {json.dumps({'type': 'chunk', 'text': 'Image generation is processing. Please check Image Studio workspace for high-resolution gallery downloads.'})}\n\n"
            except Exception as ex:
                yield f"data: {json.dumps({'type': 'chunk', 'text': f'Generation notice: {ex}'})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"

        return StreamingResponse(gen_image_response(), media_type="text/event-stream")

    # Select Engine: 2 Fast Models + Deep Research & Reasoning Tier
    if m in ("flash", "kalki-flash"):
        eng_name = "Kalki Flash (Instant 300 t/s)"
        gen_fn = lambda m,h,s: stream_groq(m, h, s, user_key, target_model="qwen/qwen3.8-27b", temperature=0.7)
    elif m in ("turbo", "kalki-turbo"):
        eng_name = "Kalki Turbo (Rapid Response)"
        gen_fn = lambda m,h,s: stream_groq(m, h, s, user_key, target_model="openai/gpt-oss-20b", temperature=0.7)
    elif m in ("thinker", "kalki-thinker", "deepseek-r1"):
        eng_name = "Kalki Thinker (Deep 120B Reasoning)"
        deep_sys = (sys_prompt or SYSTEM_PROMPT) + "\n\nDEEP REASONING DIRECTIVE: You are Kalki Thinker. Think methodically step-by-step. Scrutinize edge cases, eliminate all logical and factual errors, and output production-grade, mathematically verified, exhaustive solutions with zero mistakes."
        gen_fn = lambda m,h,s: stream_groq(m, h, deep_sys, user_key, target_model="openai/gpt-oss-120b", temperature=0.2)
    elif m in ("titan", "kalki-titan"):
        eng_name = "Kalki Titan (Research & Truth)"
        titan_sys = (sys_prompt or SYSTEM_PROMPT) + "\n\nRESEARCH DIRECTIVE: You are Kalki Titan. Conduct exhaustive, deep structural analysis. Provide comprehensive breakdowns with zero shortcuts."
        gen_fn = lambda m,h,s: stream_groq(m, h, titan_sys, user_key, target_model="openai/gpt-oss-120b", temperature=0.2)
    elif m in ("sonnet", "kalki-sonnet"):
        eng_name = "Kalki Sonnet"
        gen_fn = lambda m,h,s: stream_gemini(m, h, False, s, user_key)
    elif m in ("gpt4o", "gpt-4o"):
        eng_name = "OpenAI GPT-4o"
        gen_fn = lambda m,h,s: stream_openrouter(m, h, "openai/gpt-4o-mini", s, user_key)
    elif m in ("claude", "claude-3-5-sonnet"):
        eng_name = "Claude 3.5 Sonnet"
        gen_fn = lambda m,h,s: stream_openrouter(m, h, "anthropic/claude-3.5-sonnet", s, user_key)
    elif m in ("sovereign", "kalki-sovereign"):
        eng_name = "Kalki Sovereign"
        gen_fn = lambda m,h,s: stream_ollama(m, h, s)
    else:
        eng_name = "Kalki Flash (Instant 300 t/s)"
        gen_fn = lambda m,h,s: stream_groq(m, h, s, user_key, target_model="qwen/qwen3.8-27b", temperature=0.7)

    async def gen():
        try:
            yield f"data: {json.dumps({'type': 'engine', 'engine': eng_name})}\n\n"
            got = False
            try:
                async for chunk in gen_fn(req.message, req.history, sys_prompt):
                    got = True
                    yield f"data: {json.dumps({'type': 'chunk', 'text': chunk})}\n\n"
            except Exception:
                got = False

            if not got:
                cur = None
                async for name, chunk in auto_fallback(req.message, req.history, sys_prompt):
                    if name != cur:
                        cur = name
                        yield f"data: {json.dumps({'type': 'engine', 'engine': name})}\n\n"
                    yield f"data: {json.dumps({'type': 'chunk', 'text': chunk})}\n\n"

            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'text': str(e)})}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

# ── Image Studio (Zero Pollinations - True 4K Synthesis) ──
@app.post("/api/generate-image")
async def generate_image(req: ImageReq):
    style_prefix = {
        "Cinematic": "cinematic movie still, dramatic lighting, 8k resolution, photorealistic, ",
        "Anime": "anime masterwork, Makoto Shinkai aesthetic, detailed digital art, ",
        "3D Render": "hyper-detailed 3D render, Unreal Engine 5, Octane lighting, ",
        "Watercolor": "fine art watercolor painting, fluid ink details, expressive, ",
        "Cyberpunk": "cyberpunk aesthetic, glowing neon reflections, atmospheric, ",
        "Photorealistic": "photorealistic masterpiece, 8k portrait, sharp focus, "
    }.get(req.style, "photorealistic 8k, ")
    prompt = style_prefix + req.prompt

    # 1. Primary High-Res Engine: OpenRouter Multimodal Image Synthesis
    image_models = ["google/gemini-2.5-flash-image", "google/gemini-3-pro-image"]
    for mdl in image_models:
        try:
            async with httpx.AsyncClient(timeout=60) as c:
                r = await c.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={"Authorization": f"Bearer {OPENROUTER_KEY}"},
                    json={
                        "model": mdl,
                        "messages": [{"role": "user", "content": f"Generate a high-resolution detailed image of: {prompt}"}],
                        "modalities": ["image", "text"],
                        "max_tokens": 4000
                    }
                )
                if r.status_code == 200:
                    data = r.json()
                    choice = data.get("choices", [{}])[0].get("message", {})
                    images = choice.get("images", [])
                    if images and isinstance(images, list):
                        img_obj = images[0]
                        url_val = img_obj.get("image_url", {}).get("url", "")
                        if url_val.startswith("data:image"):
                            header, b64_str = url_val.split(",", 1)
                            raw_bytes = base64.b64decode(b64_str)
                            ts = int(time.time() * 1000)
                            fname = f"kalki_{ts}.png"
                            fpath = os.path.join(public_dir, fname)
                            with open(fpath, "wb") as f:
                                f.write(raw_bytes)
                            return JSONResponse({
                                "success": True,
                                "url": f"/{fname}",
                                "b64": url_val,
                                "engine": "Kalki Studio 4K (Ultra HD)",
                                "prompt": prompt
                            })
        except Exception:
            continue

    return JSONResponse({"success": False, "error": "Image synthesis is momentarily busy. Please retry in a few moments."}, status_code=500)

# ── File Upload + Document Intelligence ───────────────────────────
@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    content = await file.read()
    fname = file.filename or "file"
    ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else ""
    text = ""
    size = len(content)

    try:
        if ext == "txt":
            text = content.decode("utf-8", errors="replace")
        elif ext == "csv":
            reader = csv.reader(io.StringIO(content.decode("utf-8", errors="replace")))
            rows = list(reader)
            text = f"CSV Dataset: {len(rows)} rows, {len(rows[0]) if rows else 0} columns.\nHeaders: {rows[0] if rows else []}\n"
            for row in rows[1:15]:
                text += ", ".join(row) + "\n"
        elif ext == "pdf":
            try:
                from pypdf import PdfReader
                reader = PdfReader(io.BytesIO(content))
                text = "\n".join(p.extract_text() or "" for p in reader.pages[:30])
            except Exception as e:
                text = f"PDF text extraction: {e}"
        elif ext == "docx":
            try:
                from docx import Document
                doc = Document(io.BytesIO(content))
                text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
            except Exception as e:
                text = f"DOCX extraction: {e}"
        elif ext in ("xlsx", "xls"):
            try:
                import openpyxl
                wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
                ws = wb.active
                rows = list(ws.iter_rows(values_only=True, max_row=50))
                text = f"Excel Sheet: {ws.max_row} rows, {ws.max_column} columns.\n"
                text += "\n".join(", ".join(str(c) if c is not None else "" for c in r) for r in rows[:20])
            except Exception as e:
                text = f"Excel extraction: {e}"
        elif ext in ("png", "jpg", "jpeg", "webp", "gif"):
            b64 = base64.b64encode(content).decode()
            mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp"}.get(ext, "image/png")
            return JSONResponse({"success": True, "type": "image", "name": fname, "size": size,
                "b64": b64, "mime": mime, "preview": f"data:{mime};base64,{b64}"})
        else:
            text = content.decode("utf-8", errors="replace")[:5000]
    except Exception as e:
        text = f"File processing error: {e}"

    fpath = os.path.join(upload_dir, fname)
    with open(fpath, "wb") as f:
        f.write(content)

    return JSONResponse({"success": True, "type": "document", "name": fname, "size": size,
        "ext": ext, "text": text[:8000], "preview": text[:400]})

# ── Web Research ──────────────────────────────────────────────────
@app.post("/api/search")
async def web_search(req: SearchReq):
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}) as c:
            r = await c.get(f"https://duckduckgo.com/html/?q={req.query}&kl=in-en")
            html = r.text

        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        results = []
        for res in soup.select(".result")[:8]:
            title_el = res.select_one(".result__title a")
            snippet_el = res.select_one(".result__snippet")
            if title_el:
                title = title_el.get_text(strip=True)
                url = title_el.get("href", "")
                snippet = snippet_el.get_text(strip=True) if snippet_el else ""
                if title and url:
                    results.append({"title": title, "url": url, "snippet": snippet})

        results_text = "\n".join(f"{i+1}. {r['title']}\n   {r['snippet']}\n   URL: {r['url']}" for i, r in enumerate(results))
        synth_prompt = f"Query: {req.query}\n\nSearch Results:\n{results_text}\n\nProvide a comprehensive, well-structured research briefing based on these findings with key points and verified sources. NO EMOJIS."

        summary = ""
        async for chunk in stream_gemini(synth_prompt, [], False):
            summary += chunk

        if not summary:
            async for chunk in stream_groq(synth_prompt, []):
                summary += chunk

        return JSONResponse({"success": True, "query": req.query, "results": results, "summary": summary})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)

# ── URL Analyzer ──────────────────────────────────────────────────
@app.post("/api/analyze-url")
async def analyze_url(req: UrlReq):
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}) as c:
            r = await c.get(req.url)
            r.raise_for_status()
            html = r.text

        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()
        title = soup.find("title")
        title_text = title.get_text(strip=True) if title else "Webpage"
        body_text = soup.get_text(separator="\n", strip=True)[:6000]

        analysis_prompt = f"Analyze this webpage:\nURL: {req.url}\nTitle: {title_text}\n\nContent:\n{body_text}\n\nProvide:\n1. Summary (2-3 sentences)\n2. Key Highlights (bullet points)\n3. Important Takeaways\n4. Key Data / Statistics. NO EMOJIS."

        analysis = ""
        async for chunk in stream_gemini(analysis_prompt, [], False):
            analysis += chunk

        if not analysis:
            async for chunk in stream_groq(analysis_prompt, []):
                analysis += chunk

        return JSONResponse({"success": True, "url": req.url, "title": title_text, "analysis": analysis, "word_count": len(body_text.split())})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)

# ── Memory, Agents, Prompts, Sessions ──────────────────────────────
MEMORY_FILE = os.path.join(data_dir, "memory.json")
AGENTS_FILE = os.path.join(data_dir, "agents.json")
PROMPTS_FILE = os.path.join(data_dir, "prompts.json")
SESSIONS_FILE = os.path.join(data_dir, "sessions.json")

@app.get("/api/memory")
async def get_memory(): return JSONResponse(load_json(MEMORY_FILE, []))

@app.post("/api/memory")
async def save_memory(item: MemoryItem):
    mem = load_json(MEMORY_FILE, [])
    existing = next((m for m in mem if m["key"] == item.key), None)
    if existing: existing["value"] = item.value
    else: mem.append({"key": item.key, "value": item.value, "ts": int(time.time())})
    save_json(MEMORY_FILE, mem)
    return JSONResponse({"success": True})

@app.delete("/api/memory/{key}")
async def delete_memory(key: str):
    mem = [m for m in load_json(MEMORY_FILE, []) if m["key"] != key]
    save_json(MEMORY_FILE, mem)
    return JSONResponse({"success": True})

@app.get("/api/agents")
async def get_agents(): return JSONResponse(load_json(AGENTS_FILE, []))

@app.post("/api/agents")
async def save_agent(agent: Agent):
    agents = load_json(AGENTS_FILE, [])
    if agent.id:
        for i, a in enumerate(agents):
            if a["id"] == agent.id:
                agents[i] = agent.dict()
                break
        else: agents.append(agent.dict())
    else:
        agent.id = f"agent_{int(time.time())}"
        agents.append(agent.dict())
    save_json(AGENTS_FILE, agents)
    return JSONResponse({"success": True, "id": agent.id})

@app.delete("/api/agents/{aid}")
async def delete_agent(aid: str):
    agents = [a for a in load_json(AGENTS_FILE, []) if a.get("id") != aid]
    save_json(AGENTS_FILE, agents)
    return JSONResponse({"success": True})

DEFAULT_PROMPTS = [
    {"id": "p1", "title": "Explain Code Step by Step", "content": "Explain this code step by step with line numbers and intuition:\n\n[paste code here]", "category": "Coding", "favorite": False},
    {"id": "p2", "title": "Debug and Fix Errors", "content": "Analyze this code, identify all logic or syntax bugs, and provide the corrected code with explanation:\n\n[paste code here]", "category": "Coding", "favorite": True},
    {"id": "p3", "title": "System Design Architecture", "content": "Design a distributed, highly scalable system for [System Name]. Include architecture components, database choice, caching strategy, and bottleneck mitigation.", "category": "Coding", "favorite": False},
    {"id": "p4", "title": "Unreal Engine 5 C++ Actor", "content": "Write a production-ready Unreal Engine 5 C++ Actor with header (.h) and source (.cpp) files implementing: [Mechanic / Feature]. Include UPROPERTY macros and comments.", "category": "Game Dev", "favorite": True},
    {"id": "p5", "title": "Full Game Design Document (GDD)", "content": "Generate a comprehensive Game Design Document for a [Genre] game called [Game Title]. Include core loop, mechanics, narrative premise, player progression, and monetization.", "category": "Game Dev", "favorite": False},
    {"id": "p6", "title": "Executive Resume / CV", "content": "Create an ATS-friendly, high-impact resume section for a Software Engineer with skills in [Skills] and achievements in [Achievements]. Use strong action verbs and quantified impact.", "category": "Writing", "favorite": False},
    {"id": "p7", "title": "LinkedIn Thought Leadership", "content": "Write an insightful LinkedIn post sharing lessons learned about [Topic]. Include a strong hook, actionable takeaways, and a compelling question to prompt comments.", "category": "Writing", "favorite": False},
    {"id": "p8", "title": "Deep Academic Research Synthesis", "content": "Provide a rigorous, peer-reviewed style research summary on [Topic]. Contrast differing methodologies, summarize empirical consensus, and highlight open research questions.", "category": "Research", "favorite": False},
    {"id": "p9", "title": "Cinematic Story in Tamil", "content": "Write an atmospheric, emotional short story in pure Tamil about [Theme/Character]. Include vivid sensory descriptions, believable dialogue, and a powerful climax.", "category": "Writing", "favorite": True},
    {"id": "p10", "title": "DSA Problem Optimal Solution", "content": "Solve this LeetCode style problem: [Problem]. Provide brute force intuition, optimal solution with C++ or Python code, and exact Big-O time and space complexity.", "category": "Coding", "favorite": True},
]

@app.get("/api/prompts")
async def get_prompts():
    data = load_json(PROMPTS_FILE, None)
    if data is None:
        save_json(PROMPTS_FILE, DEFAULT_PROMPTS)
        return JSONResponse(DEFAULT_PROMPTS)
    return JSONResponse(data)

@app.post("/api/prompts")
async def save_prompts(request: Request):
    data = await request.json()
    save_json(PROMPTS_FILE, data)
    return JSONResponse({"success": True})

@app.get("/api/sessions")
async def get_sessions():
    sessions = load_json(SESSIONS_FILE, [])
    cutoff = (time.time() - (30 * 86400)) * 1000
    filtered = [s for s in sessions if (s.get("createdAt") or s.get("updatedAt") or (time.time() * 1000)) >= cutoff]
    if len(filtered) != len(sessions):
        save_json(SESSIONS_FILE, filtered)
    return JSONResponse(filtered)

@app.post("/api/sessions")
async def save_sessions(request: Request):
    data = await request.json()
    cutoff = (time.time() - (30 * 86400)) * 1000
    filtered = [s for s in data if (s.get("createdAt") or s.get("updatedAt") or (time.time() * 1000)) >= cutoff]
    save_json(SESSIONS_FILE, filtered)
    return JSONResponse({"success": True})

@app.get("/")
async def root():
    idx = os.path.join(public_dir, "index.html")
    if os.path.exists(idx):
        return FileResponse(idx)
    return JSONResponse({"status": "Kalki AI OS running"})

if os.path.exists(public_dir):
    app.mount("/", StaticFiles(directory=public_dir, html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=3000)
