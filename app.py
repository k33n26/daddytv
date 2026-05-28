import re
import base64
from urllib.parse import urlparse, quote
from flask import Flask, request, Response, redirect
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

SESSION = requests.Session()
SESSION.verify = False

HEADERS_TV = {
    "user-agent": "Mozilla/5.0 (WebOS; SmartTV)",
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/jxl,image/avif,image/webp,image/apng,*/*;q=0.8",
    "accept-language": "tr-TR,tr;q=0.6",
}

HEADERS_PROXY = {
    "User-Agent": "Mozilla/5.0 (compatible; Proxy/1.0)",
}

def get_self_url():
    scheme = request.scheme
    host = request.host
    path = request.path
    return f"{scheme}://{host}{path}"

@app.route("/health", methods=["GET"])
def health():
    return Response("OK", status=200, content_type="text/plain")

@app.route("/", methods=["GET"])
def index():
    cdn = request.args.get("CDN")
    live_id = request.args.get("ID")

    if cdn:
        resp = SESSION.get(cdn, headers=HEADERS_PROXY, allow_redirects=True, timeout=15)
        content_type = resp.headers.get("Content-Type", "")

        is_m3u8 = (
            "application/vnd.apple.mpegurl" in content_type
            or "application/x-mpegURL" in content_type
            or re.search(r"\.m3u8", cdn)
        )

        if is_m3u8:
            self_url = get_self_url()
            base_url = cdn[: cdn.rfind("/") + 1]
            lines = resp.text.split("\n")
            rewritten = []

            for line in lines:
                line = line.strip()
                if line == "" or line.startswith("#"):
                    rewritten.append(line)
                    continue

                if not re.match(r"^https?://", line):
                    if line.startswith("/"):
                        parsed = urlparse(cdn)
                        base_url = f"{parsed.scheme}://{parsed.netloc}"
                    line = base_url + line

                line = f"{self_url}?CDN={quote(line, safe='')}"
                rewritten.append(line)

            return Response(
                "\n".join(rewritten),
                content_type="application/vnd.apple.mpegurl",
                headers={"Access-Control-Allow-Origin": "*"},
            )

        ct = content_type if content_type else "video/mp2t"
        return Response(
            resp.content,
            content_type=ct,
            headers={"Access-Control-Allow-Origin": "*"},
        )

    if live_id:
        stream_url = f"https://dlhd.pk/stream/stream-{live_id}.php"
        headers = {**HEADERS_TV, "referer": f"https://dlhd.pk/watch.php?id={live_id}"}

        r1 = SESSION.get(stream_url, headers=headers, timeout=15)
        site = r1.text

        iframe = re.search(r'iframe[^>]+src=["\']([^"\']+)["\']', site, re.I)
        if iframe:
            data_url = iframe.group(1)
            r2 = SESSION.get(data_url, headers=headers, timeout=15)
            site2 = r2.text

            patterns = [
                r"source:\s*window\.atob\('([^']+)'\)",
                r"atob\('([^']+)'\)",
                r'file:\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
                r'source:\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
            ]

            for pat in patterns:
                m = re.search(pat, site2)
                if m:
                    try:
                        link = base64.b64decode(m.group(1)).decode("utf-8") if "atob" in pat else m.group(1)
                    except Exception:
                        link = m.group(1)
                    return redirect(f"?CDN={quote(link, safe='')}")

        return Response("Stream linki bulunamadı", status=404)

    return Response("Kullanım: ?ID=<no> veya ?CDN=<url>", status=400)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
