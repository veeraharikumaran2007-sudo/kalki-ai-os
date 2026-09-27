import { MsEdgeTTS, OUTPUT_FORMAT } from "msedge-tts";

export default async function handler(req, res) {
  // CORS configuration for universal access
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  if (req.method === 'OPTIONS') {
    return res.status(200).end();
  }

  let text = '';
  let voice = 'en-GB-RyanNeural';

  if (req.method === 'GET') {
    text = req.query.text || '';
    if (req.query.voice) voice = req.query.voice;
  } else {
    text = req.body?.text || req.body?.prompt || req.body?.message || '';
    if (req.body?.voice) voice = req.body?.voice;
  }

  if (!text || !text.trim()) {
    return res.status(400).json({ error: 'Text parameter required' });
  }

  // Pre-process and clean text for natural spoken cadence
  const cleanText = text
    .replace(/https?:\/\/\S+/gi, '')
    .replace(/[*#`_~[\]()]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();

  // Language auto-detection (Tamil vs British English JARVIS)
  const hasTamil = /[\u0B80-\u0BFF]/.test(cleanText);
  const selectedVoice = hasTamil ? 'ta-IN-ValluvarNeural' : voice;

  try {
    const tts = new MsEdgeTTS();
    await tts.setMetadata(selectedVoice, OUTPUT_FORMAT.AUDIO_24KHZ_48KBITRATE_MONO_MP3);
    const { audioStream } = tts.toStream(cleanText.slice(0, 3000));

    res.setHeader('Content-Type', 'audio/mpeg');
    res.setHeader('Cache-Control', 'public, max-age=3600');

    audioStream.pipe(res);
  } catch (err) {
    console.error('[Vercel TTS Error]', err);
    res.status(500).json({ error: 'TTS Synthesis failed: ' + err.message });
  }
}
