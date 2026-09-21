import os
import base64
import requests
import json
import urllib.parse

api_key = os.getenv("GEMINI_API_KEY")
with open("sketch_clean.png", "rb") as f:
    b64 = base64.b64encode(f.read()).decode("utf-8")

url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
instruction = (
    "You are Valkeria Studio's elite Creative Art Director. The user attached this hand-drawn sketch and requested: 'create logo'. "
    "Carefully analyze the subject, posture (rearing mythical horned creature/beast), anatomy, curved horns, hooves, and silhouette of this sketch. "
    "Write a single concise, ultra-detailed text-to-image prompt (under 60 words) to transform this sketch into an elite luxury 3D metallic logo emblem. "
    "Specify: luxury 3D metallic chrome silver and gold heraldic crest emblem logo of the rearing horned beast from the sketch, sharp bevels, glowing cyan accents, dark obsidian carbon background, 8k render, octane render, Unreal Engine 5 aesthetic. "
    "Output ONLY the prompt text. No commentary, no quotes."
)
payload = {
    "contents": [{
        "role": "user",
        "parts": [
            {"inline_data": {"mime_type": "image/png", "data": b64}},
            {"text": instruction}
        ]
    }]
}
resp = requests.post(url, json=payload, timeout=25)
if resp.ok:
    prompt = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip().strip('"\'')
    print("EXPANDED PROMPT:")
    print(prompt)
    encoded = urllib.parse.quote(prompt)
    img_url = f"https://image.pollinations.ai/prompt/{encoded}?width=1024&height=1024&nologo=true&seed=42&model=flux"
    print("\nIMAGE URL:")
    print(img_url)
    # Download and save preview
    r = requests.get(img_url, timeout=30)
    if r.ok:
        with open("generated_sketch_logo.jpg", "wb") as img_f:
            img_f.write(r.content)
        print("Successfully generated and saved generated_sketch_logo.jpg!")
else:
    print("Error:", resp.status_code, resp.text)
