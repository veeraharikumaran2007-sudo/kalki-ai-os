require("dotenv").config();
const express = require("express");
const cors = require("cors");
const path = require("path");

const app = express();
const PORT = process.env.PORT || 3000;

// ====================================================================
// 🍎 APPLE-GRADE SECURITY LAYER 1: STRICT SECURITY HEADERS
// ====================================================================
app.use((req, res, next) => {
  res.setHeader("X-Content-Type-Options", "nosniff");
  res.setHeader("X-Frame-Options", "SAMEORIGIN");
  res.setHeader("X-XSS-Protection", "1; mode=block");
  res.setHeader("Strict-Transport-Security", "max-age=31536000; includeSubDomains");
  res.setHeader("Referrer-Policy", "strict-origin-when-cross-origin");
  res.removeHeader("X-Powered-By");
  next();
});

// ====================================================================
// 🍎 APPLE-GRADE SECURITY LAYER 2: RESTRICTED CORS WHITELIST
// ====================================================================
const allowedOrigins = [
  "https://kalki-arcues.web.app",
  "https://kalki-arcues.firebaseapp.com",
  "http://localhost:3000",
  "http://127.0.0.1:3000",
  "http://localhost:8000",
  "http://127.0.0.1:8000"
];

app.use(
  cors({
    origin: function (origin, callback) {
      if (!origin || allowedOrigins.includes(origin)) {
        callback(null, true);
      } else {
        callback(new Error("CORS Policy: Access denied from unauthorized domain."));
      }
    },
    methods: ["GET", "POST", "OPTIONS"],
    allowedHeaders: ["Content-Type", "Authorization"]
  })
);

app.use(express.json({ limit: "5mb" }));
app.use(express.static(path.join(__dirname, "public")));

// ====================================================================
// 🍎 APPLE-GRADE SECURITY LAYER 3: IN-MEMORY RATE LIMITING (DDoS Guard)
// ====================================================================
const rateLimitMap = new Map();
const RATE_LIMIT_WINDOW = 60 * 1000; // 1 minute
const MAX_REQUESTS_PER_WINDOW = 30; // Max 30 requests per minute per IP

function rateLimiter(req, res, next) {
  const ip = req.ip || req.headers["x-forwarded-for"] || req.socket.remoteAddress;
  const now = Date.now();

  const record = rateLimitMap.get(ip) || { count: 0, startTime: now };

  if (now - record.startTime > RATE_LIMIT_WINDOW) {
    record.count = 1;
    record.startTime = now;
  } else {
    record.count++;
  }

  rateLimitMap.set(ip, record);

  if (record.count > MAX_REQUESTS_PER_WINDOW) {
    return res.status(429).json({
      error: "Too Many Requests. Rate limit exceeded (30 req/min). Please try again shortly."
    });
  }

  next();
}

// Clean up stale rate limit entries every 5 minutes
setInterval(() => {
  const now = Date.now();
  for (const [ip, record] of rateLimitMap.entries()) {
    if (now - record.startTime > RATE_LIMIT_WINDOW) {
      rateLimitMap.delete(ip);
    }
  }
}, 5 * 60 * 1000);

// ====================================================================
// 🍎 APPLE-GRADE SECURITY LAYER 4: SYSTEM PROMPT VAULT (Server-only)
// ====================================================================
const SYSTEM_PROMPT = `[IDENTITY & OPERATING DIRECTIVE]
YOU ARE: Kalki, a high-performance sovereign AI operating system engineered by Arcues.
Creator & Leadership: Arcues was founded by CEO S. Veeraharikumaran.
Confidentiality & Etiquette:
- Only discuss your company (Arcues) or founder (S. Veeraharikumaran) if specifically and explicitly asked by the user.
- Focus purely on giving immediate, elite, direct value.
- NEVER identify as OpenAI, Google, Anthropic, Meta, or any third party.
Languages: Tamil, Tanglish, English, Hindi - fluently, natively, and naturally based on user input.
STRICT FORMATTING RULES:
- NEVER use emojis or decorative icons in your responses. Absolutely zero emojis under any circumstances.
- Use clean markdown: headers, bullet points, syntax-highlighted code blocks with language tags.
- Direct, concise, authoritative, and helpful.`;

// Key rotation helper
const rawGroq = process.env.GROQ_API_KEYS || process.env.GROQ_API_KEY || "";
const GROQ_KEYS = rawGroq.split(",").map(k => k.trim()).filter(Boolean);
let groqIndex = 0;

function getGroqKey() {
  if (GROQ_KEYS.length === 0) return null;
  const key = GROQ_KEYS[groqIndex % GROQ_KEYS.length];
  groqIndex++;
  return key;
}

// ====================================================================
// ENGINE PIPELINES (Strict Server-Side Key Access)
// ====================================================================

// 1. Groq Ultra-Fast Pipeline
async function runGroq(message, modelName = "qwen/qwen3.8-27b", history = []) {
  const key = getGroqKey();
  if (!key) throw new Error("Server Groq API key not configured");

  const msgs = [{ role: "system", content: SYSTEM_PROMPT }];
  history.slice(-8).forEach(h => msgs.push({ role: h.role, content: h.content }));
  msgs.push({ role: "user", content: message });

  const resp = await fetch("https://api.groq.com/openai/v1/chat/completions", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${key}`
    },
    body: JSON.stringify({
      model: modelName,
      messages: msgs,
      max_tokens: 4096,
      temperature: 0.7
    })
  });

  if (!resp.ok) throw new Error(`Groq HTTP ${resp.status}`);
  const data = await resp.json();
  return { text: data.choices[0]?.message?.content || "", engine: "Kalki Flash (Groq)" };
}

// 2. Gemini Pipeline
async function runGemini(message, history = []) {
  const apiKey = process.env.GEMINI_API_KEY;
  if (!apiKey) throw new Error("Server Gemini API key not configured");

  const contents = [];
  contents.push({ role: "user", parts: [{ text: `[System Instructions: ${SYSTEM_PROMPT}]` }] });
  contents.push({ role: "model", parts: [{ text: "Understood. I will operate strictly as Kalki AI OS." }] });

  for (const item of history.slice(-8)) {
    const role = item.role === "assistant" ? "model" : "user";
    contents.push({ role, parts: [{ text: item.content }] });
  }
  contents.push({ role: "user", parts: [{ text: message }] });

  const url = `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=${apiKey}`;
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ contents })
  });

  if (!response.ok) throw new Error(`Gemini HTTP ${response.status}`);
  const data = await response.json();
  const reply = data?.candidates?.[0]?.content?.parts?.[0]?.text;
  return { text: reply || "", engine: "Kalki Sonnet (Gemini 2.0)" };
}

// 3. OpenRouter Pipeline (Multi-Model High Availability)
async function runOpenRouter(message, history = []) {
  const apiKey = process.env.OPENROUTER_API_KEY;
  if (!apiKey) throw new Error("Server OpenRouter key not configured");

  const messages = [
    { role: "system", content: SYSTEM_PROMPT },
    ...history.slice(-8).map(h => ({ role: h.role === "assistant" ? "assistant" : "user", content: h.content })),
    { role: "user", content: message }
  ];

  const candidateModels = [
    "nvidia/nemotron-3-super-120b-a12b:free",
    "google/gemma-4-26b-a4b-it:free",
    "qwen/qwen3.8-27b:free",
    "inclusionai/ling-3.0-flash-vl:free"
  ];

  let lastErr = null;
  for (const m of candidateModels) {
    try {
      const response = await fetch("https://openrouter.ai/api/v1/chat/completions", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${apiKey}`,
          "HTTP-Referer": "https://kalki-arcues.web.app",
          "X-Title": "Kalki AI OS"
        },
        body: JSON.stringify({ model: m, messages })
      });

      if (!response.ok) {
        lastErr = new Error(`OpenRouter (${m}) HTTP ${response.status}`);
        continue;
      }

      const data = await response.json();
      const text = data?.choices?.[0]?.message?.content || "";
      if (text) {
        return { text, engine: `Kalki AI (${m.split("/")[1].replace(":free", "")})` };
      }
    } catch(e) {
      lastErr = e;
    }
  }

  throw lastErr || new Error("All OpenRouter neural pipelines currently busy");
}

// ====================================================================
// SECURE API ENDPOINTS
// ====================================================================

// Standard Chat Endpoint
app.post("/api/chat", rateLimiter, async (req, res) => {
  const { message, model = "flash", history = [] } = req.body;

  // Input Sanitization
  if (!message || typeof message !== "string") {
    return res.status(400).json({ error: "Valid message string is required." });
  }
  if (message.length > 10000) {
    return res.status(400).json({ error: "Message exceeds maximum allowed length of 10,000 characters." });
  }

  try {
    let result = null;

    if (process.env.OPENROUTER_API_KEY) {
      try {
        result = await runOpenRouter(message, history);
      } catch(e) {
        console.warn("OpenRouter fallback in /api/chat:", e.message);
      }
    }

    if (!result && GROQ_KEYS.length > 0) {
      try {
        result = await runGroq(message, "qwen/qwen3.8-27b", history);
      } catch(e) {}
    }

    if (!result && process.env.GEMINI_API_KEY) {
      try {
        result = await runGemini(message, history);
      } catch(e) {}
    }

    if (!result) {
      throw new Error("All Kalki neural pipelines are currently processing heavy load. Please retry in a few seconds.");
    }

    return res.json({
      reply: result.text,
      engine: result.engine,
      timestamp: new Date().toISOString()
    });
  } catch (err) {
    console.error("Secure Gateway Error:", err.message);
    return res.status(500).json({
      error: "All Kalki neural pipelines are currently processing heavy load. Please retry in a few seconds."
    });
  }
});

// Real-Time Streaming Endpoint (SSE)
app.post("/api/chat/stream", rateLimiter, async (req, res) => {
  const { message, model = "flash", history = [] } = req.body;

  if (!message || typeof message !== "string" || message.length > 10000) {
    return res.status(400).json({ error: "Invalid message payload." });
  }

  res.setHeader("Content-Type", "text/event-stream");
  res.setHeader("Cache-Control", "no-cache");
  res.setHeader("Connection", "keep-alive");
  if (typeof res.flushHeaders === "function") {
    res.flushHeaders();
  }

  try {
    let result = null;

    if (process.env.OPENROUTER_API_KEY) {
      try {
        result = await runOpenRouter(message, history);
      } catch(e) {
        console.warn("Stream OpenRouter fallback:", e.message);
      }
    }

    if (!result && GROQ_KEYS.length > 0) {
      try {
        result = await runGroq(message, "qwen/qwen3.8-27b", history);
      } catch(e) {}
    }

    if (!result && process.env.GEMINI_API_KEY) {
      try {
        result = await runGemini(message, history);
      } catch(e) {}
    }

    if (!result) {
      throw new Error("AI models are currently busy. Please retry in 5 seconds.");
    }

    res.write(`data: ${JSON.stringify({ type: "engine", engine: result.engine })}\n\n`);

    // Stream text in small chunks for realistic streaming UI
    const words = result.text.split(" ");
    for (let i = 0; i < words.length; i += 3) {
      const chunk = words.slice(i, i + 3).join(" ") + " ";
      res.write(`data: ${JSON.stringify({ type: "chunk", text: chunk })}\n\n`);
      await new Promise(r => setTimeout(r, 20));
    }

    res.write("data: [DONE]\n\n");
    res.end();
  } catch (err) {
    res.write(`data: ${JSON.stringify({ type: "error", text: err.message })}\n\n`);
    res.end();
  }
});

// Health check endpoint
app.get("/api/health", (req, res) => {
  res.json({
    status: "online",
    system: "Kalki AI OS - Secure Enterprise Gateway",
    timestamp: new Date().toISOString()
  });
});

app.listen(PORT, () => {
  console.log(`========================================================`);
  console.log(`  🍎 APPLE-GRADE SECURE KALKI AI SERVER IS RUNNING`);
  console.log(`  Port: ${PORT}`);
  console.log(`  CORS Whitelist: kalki-arcues.web.app, localhost`);
  console.log(`  Zero Client-Side Leaks: All Keys Isolated in .env`);
  console.log(`========================================================`);
});

module.exports = app;

