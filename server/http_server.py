"""Loopback HTTP API and static HTML/JS/CSS for the Synopsis workspace."""
from __future__ import annotations
import json
import mimetypes
import os
import socket
from uuid import uuid4
from dataclasses import asdict, is_dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit, parse_qs
from .application import SynopsisApplication
from storage import FileCourseStorage, StorageError
from storage.file_storage import _snapshot_to_data
from synopsis_domain import DomainError
from transfer import ArchiveError
from .frontend_assets import frontend_status, require_frontend

FRONTEND = Path(__file__).resolve().parent.parent / "frontend"
MAX_BODY = 300 * 1024 * 1024


class LocalHTTPServer(ThreadingHTTPServer):
    # Windows SO_REUSEADDR can allow another process to bind this same port.
    allow_reuse_address = os.name != "nt"

    def server_bind(self):
        if os.name == "nt":
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def serial(value):
    if is_dataclass(value): return asdict(value)
    return value


def create_server(data_dir, host="127.0.0.1", port=8765):
    startup_ui = require_frontend(FRONTEND)
    app = SynopsisApplication(FileCourseStorage(data_dir))

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass

        def reply(self, code, body=b"", ctype="application/json; charset=utf-8"):
            raw = body if isinstance(body,bytes) else json.dumps(body, ensure_ascii=False, default=serial, allow_nan=False).encode()
            self.send_response(code)
            self.send_header("Content-Type",ctype)
            self.send_header("Content-Length",str(len(raw)))
            self.send_header("Cache-Control","no-store")
            self.send_header("X-Content-Type-Options","nosniff")
            self.send_header("Referrer-Policy","no-referrer")
            self.send_header("X-Synopsis-Instance", self.server.instance_id)
            if ctype.startswith("text/html"):
                self.send_header("Content-Security-Policy","default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(raw)

        def body(self):
            size = int(self.headers.get("Content-Length",0))
            if size<0 or size>MAX_BODY: raise ValueError("Файл слишком большой (лимит 300 MiB)")
            if self.headers.get("Transfer-Encoding"): raise ValueError("Unsupported transfer encoding")
            return self.rfile.read(size)

        def json(self):
            data=json.loads(self.body() or b"{}")
            if not isinstance(data,dict): raise ValueError("Ожидается JSON-объект")
            return data

        def route(self):
            return [unquote(x) for x in urlsplit(self.path).path.strip("/").split("/")]

        def check_host(self):
            host=self.headers.get("Host","")
            if host not in {f"localhost:{self.server.server_port}",f"127.0.0.1:{self.server.server_port}"}:
                raise ValueError("Разрешён только локальный адрес сервера")

        def static(self,path):
            target=(FRONTEND/path).resolve()
            if not target.is_relative_to(FRONTEND.resolve()) or not target.is_file():
                return self.reply(404,{"error":"Файл интерфейса не найден", "path":path, "diagnostics":"/api/health"})
            ctype={".js":"text/javascript; charset=utf-8",".css":"text/css; charset=utf-8",".html":"text/html; charset=utf-8"}.get(target.suffix,mimetypes.guess_type(str(target))[0] or "application/octet-stream")
            return self.reply(200,target.read_bytes(),ctype)

        def do_GET(self):
            try:
                self.check_host()
                p=self.route()
                query=parse_qs(urlsplit(self.path).query)
                if p==[""] or p==["index.html"]: return self.static("index.html")
                if len(p)==2 and p[0]=="courses": return self.static("course.html")
                if p[0]=="static": return self.static("/".join(p[1:]))
                if p==["api","health"]:
                    ui = frontend_status(FRONTEND)
                    return self.reply(200 if ui["ok"] else 503, {
                        "app":"synopsis", "status":"ok" if ui["ok"] else "incomplete-ui",
                        "instance_id":self.server.instance_id, "process_id":os.getpid(),
                        "data_dir":str(app.storage.root.resolve()), "ui":ui,
                        "startup_ui_fingerprint":startup_ui["fingerprint"],
                    })
                if p==["api","courses"]: return self.reply(200,app.list_courses())
                if len(p)==3 and p[:2]==["api","courses"]: return self.reply(200,_snapshot_to_data(app.snapshot(p[2])))
                if len(p)==5 and p[:2]==["api","courses"] and p[3]=="assets":
                    asset,data=app.storage.get_asset(p[2],p[4])
                    media=asset.media_type if asset.media_type in {"application/pdf","image/png","image/jpeg","image/gif","image/webp","image/avif"} else "application/octet-stream"
                    return self.reply(200,data,media)
                if len(p)==6 and p[:2]==["api","courses"] and p[3]=="sources" and p[5]=="open":
                    page=int(query["page"][0]) if query.get("page") else None
                    return self.reply(200,app.source_open(p[2],p[4],page))
                self.reply(404,{"error":"Маршрут не найден"})
            except (StorageError,ValueError,KeyError,DomainError) as e:
                self.reply(404,{"error":str(e),"code":str(getattr(e,"code",""))})

        def do_POST(self):
            try:
                self.check_host()
                origin=self.headers.get("Origin")
                if origin and origin != f"http://{self.headers.get('Host')}": return self.reply(403,{"error":"Запрос с другого сайта отклонён"})
                p=self.route()
                query=parse_qs(urlsplit(self.path).query)
                if p==["api","import"]: return self.reply(201,app.import_course(self.body()))
                if len(p)==4 and p[:2]==["api","courses"]:
                    if p[3]=="export": return self.reply(200,app.export_course(p[2]),"application/vnd.synopsis+zip")
                    if p[3] in {"assets","sources"}:
                        filename=unquote(self.headers.get("X-Filename","file"))
                        if p[3]=="sources": value=app.import_source(p[2],filename,self.body(),query.get("lecture_note_id",[None])[0])
                        else: value=app.import_asset(p[2],filename,self.headers.get("Content-Type","application/octet-stream").split(";")[0],self.body())
                        return self.reply(201,value)
                data=self.json()
                if p==["api","courses"]: return self.reply(201,app.create_course(data["title"]))
                if len(p)==4 and p[:2]==["api","courses"]:
                    if p[3]=="rename": return self.reply(200,app.rename_course(p[2],data["title"]))
                    if p[3]=="lectures":
                        n,b=app.create_lecture(p[2],data["title"],summary=data.get("summary",""),markdown=data.get("markdown",""),position=data.get("position"));return self.reply(201,{"id":str(n.id),"note_id":str(n.id),"box_id":str(b.id),"revision":n.revision})
                    if p[3]=="notes":
                        n=app.create_note(p[2],kind=data.get("kind","concept"),title=data["title"],summary=data.get("summary",""),markdown=data.get("markdown",""),with_card=data.get("with_card",False),lecture_note_id=data.get("lecture_note_id"),position=data.get("position"))
                        return self.reply(201,n)
                if len(p)==5 and p[:2]==["api","courses"]:
                    if p[3]=="map": return self.reply(200,{"result":serial(app.command_map(p[2],p[4],data))})
                    if p[3]=="selection":
                        result=serial(app.selection_command(p[2],p[4],data))
                        return self.reply(201,{"result":result,"id":result.get("id") if isinstance(result,dict) else None})
                if len(p)==6 and p[:2]==["api","courses"]:
                    if p[3]=="sources": return self.reply(200,app.source_command(p[2],p[4],p[5],data))
                    if p[3]=="facts" and p[5]=="save": return self.reply(200,app.edit_fact(p[2],p[4],data["owner_note_id"],data["markdown"]))
                    if p[3]=="notes":
                        if p[5]=="save": return self.reply(200,app.save_markdown(p[2],p[4],data["markdown"],int(data["revision"])))
                        if p[5]=="meta": return self.reply(200,app.edit_note_meta(p[2],p[4],data))
                        if p[5]=="delete": app.delete_note(p[2],p[4]);return self.reply(200,{})
                self.reply(404,{"error":"Маршрут не найден"})
            except ArchiveError as e:
                self.reply(400,{"error":e.diagnostic.message,"code":e.diagnostic.code})
            except (StorageError,ValueError,KeyError,TypeError,IndexError,DomainError) as e:
                self.reply(400,{"error":str(e),"code":str(getattr(e,"code",""))})

    httpd=LocalHTTPServer((host,port),Handler)
    httpd.application=app
    httpd.instance_id=uuid4().hex
    httpd.startup_ui=startup_ui
    return httpd


def serve(data_dir,host="127.0.0.1",port=8765,*,open_browser=True):
    if host != "127.0.0.1":
        raise ValueError("Synopsis запускается только на 127.0.0.1")
    from .launcher import launch
    return launch(data_dir,port,browser=open_browser)


if __name__=="__main__":
    from .launcher import main
    raise SystemExit(main())
