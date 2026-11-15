"""Read-only API smoke test against a running server: python tools/smoke_api.py [base_url]  (default http://127.0.0.1:8765)"""
import json, sys, urllib.request, urllib.error
B = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765"
def get(p, data=None):
    try:
        req = urllib.request.Request(B + p, data=json.dumps(data).encode() if data is not None else None, headers={"Content-Type": "application/json"})
        r = urllib.request.urlopen(req, timeout=90); body = r.read()
        return r.status, body
    except urllib.error.HTTPError as e:
        return e.code, e.read()
rows, bad = [], 0
def check(label, status, body, want=(200,)):
    global bad
    ok = status in want
    bad += not ok
    rows.append(("ok " if ok else "BAD") + f" {status} {len(body):>7} {label}" + ("" if ok else "  " + body[:140].decode("utf-8", "replace")))
for p in ["/", "/v4.html", "/api/health", "/api/motion", "/api/models", "/api/sky/bright.bin", "/api/sky/bright.json", "/api/tutorials", "/api/assistant/status", "/api/assistant/commands"]:
    check(p, *get(p))
targets = json.loads(get("/api/targets")[1])["targets"]
check(f"/api/targets ({len(targets)})", 200, b"x" * len(targets))
for t in targets:
    sid = t["ready_sequence_id"]; s, body = get(f"/api/sequences/{sid}"); check(f"{t['id']} sequence", s, body)
    seq = json.loads(body); fr = seq["frames"]; n = len(fr)
    urls = [v for f in (fr[0], fr[-1]) for v in f.values() if isinstance(v, str) and v.startswith("/api/")]
    for u in urls: check(f"{t['id']} {u.rsplit('/', 1)[-1]}", *get(u))
    for sub in ["provenance", f"diff?a=0&b={n-1}", "stack", "track", "track_stack", "overlay?catalog=gaia", f"candidates?a=0&b={n-1}"]:
        check(f"{t['id']} {sub}", *get(f"/api/sequences/{sid}/{sub}"))
    # photometry needs the compiled photutils extension; 200 where it is available, a clean error otherwise
    s, body = get(f"/api/sequences/{sid}/lightcurve?follow_target=true"); rows.append(f"inf {s} {len(body):>7} {t['id']} lightcurve (photometry)")
for q in ["Ne görüyorum?", "Bu sayı nereden geliyor?"]:
    s, body = get("/api/assistant/knowledge", {"message": q, "history": [], "context": {"target_id": "barnard", "lang": "tr"}, "tool_results": []})
    check(f"assistant/knowledge '{q}'", s, body)
    if s == 200:
        for src in (json.loads(body).get("sources") or [])[:2]:
            sid = src["id"] if isinstance(src, dict) else src
            check(f"assistant/sources/{sid}", *get("/api/assistant/sources/" + urllib.request.quote(sid, safe="")))
sys.stdout.reconfigure(encoding="utf-8")
print("\n".join(rows)); print(f"\n{bad} failing of {len(rows)}"); sys.exit(1 if bad else 0)
