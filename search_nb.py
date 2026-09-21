import urllib.request
import urllib.parse
import re

query = "nano banana ai image generator"
url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
try:
    with urllib.request.urlopen(req) as resp:
        html = resp.read().decode("utf-8", errors="ignore")
        snippets = re.findall(r'<a class="result__snippet[^>]*>(.*?)</a>', html)
        for s in snippets[:8]:
            clean = re.sub('<[^<]+?>', '', s)
            print("-", clean.strip())
except Exception as e:
    print("Error:", e)
