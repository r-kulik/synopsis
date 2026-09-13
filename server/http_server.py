from __future__ import annotations
import argparse, json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from .application import SynopsisApplication
from storage import FileCourseStorage, StorageError
from shell.page import index_page

def _course(c): return {"id": c.id, "title": c.title, "saved_revision": c.saved_revision}
def _snapshot(s):
    return {"course": _course(s.course), "notes":[{"id":n.id,"kind":n.kind,"title":n.title,"summary":n.summary,"revision":n.revision} for n in s.notes.values()], "cards":[{"id":c.id,"note_id":c.note_id} for c in s.cards.values()]}

def serve(data_dir: Path | str, host="127.0.0.1", port=8765):
    app = SynopsisApplication(FileCourseStorage(data_dir))
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args): pass
        def reply(self, code, body, content_type="application/json"):
            raw = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
            self.send_response(code); self.send_header("Content-Type", content_type); self.send_header("Content-Length", str(len(raw))); self.end_headers(); self.wfile.write(raw)
        def body(self): return json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        def do_GET(self):
            try:
                parts = self.path.split("?")[0].strip("/").split("/")
                if self.path == "/": return self.reply(200, index_page().encode(), "text/html; charset=utf-8")
                if parts == ["api", "courses"]: return self.reply(200, [_course(c) for c in app.list_courses()])
                if len(parts) == 3 and parts[:2] == ["api","courses"]: return self.reply(200, _snapshot(app.snapshot(parts[2])))
                if len(parts) == 5 and parts[:2] == ["api","courses"] and parts[3] == "assets":
                    asset, data = app.storage.get_asset(parts[2], parts[4]); return self.reply(200, data, asset.media_type)
                self.reply(404, {"error":"not found"})
            except (StorageError, ValueError) as exc: self.reply(404, {"error":str(exc)})
        def do_POST(self):
            try:
                parts = self.path.strip("/").split("/")
                if len(parts) == 4 and parts[:2] == ["api","courses"] and parts[3] == "assets":
                    content = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                    asset = app.import_asset(parts[2], self.headers.get("X-Filename", "asset"), self.headers.get("Content-Type", "application/octet-stream"), content)
                    return self.reply(201, {"id":asset.id, "byte_length":asset.byte_length})
                data = self.body()
                if parts == ["api","courses"]: return self.reply(201, _course(app.create_course(data["title"])))
                if len(parts) == 4 and parts[:2] == ["api","courses"] and parts[3] == "notes":
                    n = app.create_note(parts[2], kind=data.get("kind","concept"), title=data["title"], summary=data.get("summary",""), markdown=data.get("markdown",""), with_card=data.get("with_card",False)); return self.reply(201, {"id":n.id,"revision":n.revision})
                self.reply(404, {"error":"not found"})
            except (StorageError, ValueError, KeyError) as exc: self.reply(400, {"error":str(exc)})
    httpd = ThreadingHTTPServer((host, port), Handler); print(f"Synopsis: http://{host}:{port}  data: {Path(data_dir).resolve()}")
    try: httpd.serve_forever()
    except KeyboardInterrupt: pass

if __name__ == "__main__":
    parser=argparse.ArgumentParser(); parser.add_argument("--data-dir", default=".synopsis-data"); parser.add_argument("--port",type=int,default=8765); args=parser.parse_args(); serve(args.data_dir, port=args.port)
