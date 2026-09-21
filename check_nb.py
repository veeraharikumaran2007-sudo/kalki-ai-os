import urllib.request

url = "https://huggingface.co/spaces/multimodalart/nano-banana/raw/main/app.py"
try:
    with urllib.request.urlopen(url) as r:
        txt = r.read().decode("utf-8")
        for line in txt.split("\n"):
            line_l = line.lower()
            if any(k in line_l for k in ["gemini", "imagen", "model", "generate_content", "client."]):
                if len(line.strip()) < 120:
                    print(line.strip())
except Exception as e:
    print("Error:", e)
