import urllib.request, json, sys
sys.stdout.reconfigure(encoding='utf-8')
import os
k = os.getenv('GROQ_API_KEY', '')
sys_prompt = """YOU ARE: Kalki AI, an elite sovereign AI operating system engineered by Arcues.
CRITICAL IDENTITY & CEO DIRECTIVE:
- Founder & CEO of Arcues / Kalki AI: S. Veeraharikumaran.
- If the user asks "who is the CEO?", "who is your CEO?", "who created you?", "who made you?", "CEO yaaru?", or asks about the CEO/founder/creator without naming another specific company, you MUST ALWAYS identify S. Veeraharikumaran as the Founder and CEO of Arcues, the creator of Kalki AI.
- You are NOT OpenAI, NOT Google, NOT Meta. Only discuss other CEOs (like Sam Altman of OpenAI) if the user explicitly mentions that specific other organization.
- NEVER use emojis."""

for q in ["who is the ceo", "who created you", "who is your ceo"]:
    req = urllib.request.Request(
        'https://api.groq.com/openai/v1/chat/completions',
        headers={
            'Authorization': f'Bearer {k}',
            'Content-Type': 'application/json',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
        },
        data=json.dumps({
            'model': 'openai/gpt-oss-120b',
            'messages': [
                {'role': 'system', 'content': sys_prompt},
                {'role': 'user', 'content': q}
            ],
            'temperature': 0.2,
            'max_tokens': 150
        }).encode('utf-8')
    )
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode())
        print(f"Q: {q}\nA: {data['choices'][0]['message']['content']}\n")
