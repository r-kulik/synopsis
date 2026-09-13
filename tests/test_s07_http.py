"""Black-box localhost regression for the S07 command routes."""
import json, shutil, socket, subprocess, sys, tempfile, time, unittest, uuid
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

class HttpIntegrationTests(unittest.TestCase):
 def setUp(self):
  self.root=Path.cwd() / ("_s07_http_"+uuid.uuid4().hex);self.root.mkdir();sock=socket.socket();sock.bind(("127.0.0.1",0));self.port=sock.getsockname()[1];sock.close()
  self.p=subprocess.Popen([sys.executable,"-m","server.http_server","--data-dir",str(self.root),"--port",str(self.port)],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
  for _ in range(30):
   try:urlopen(f"http://127.0.0.1:{self.port}/",timeout=.2);break
   except Exception:time.sleep(.05)
  if self.p.poll() is not None: raise RuntimeError(self.p.stderr.read().decode(errors="replace"))
 def tearDown(self): self.p.terminate();self.p.wait(timeout=3);self.p.stderr.close();shutil.rmtree(self.root,ignore_errors=True)
 def request(self,path,body=None,ctype="application/json"):
  data = body if isinstance(body,bytes) else (json.dumps(body).encode() if body is not None else None)
  req=Request(f"http://127.0.0.1:{self.port}/api/{path}",data=data,headers={"content-type":ctype},method="POST" if body is not None else "GET")
  try:
   with urlopen(req) as r:return r.status,r.read(),r.headers.get_content_type()
  except HTTPError as e:
   try:return e.code,e.read(),e.headers.get_content_type()
   finally:e.close()
 def test_course_note_save_card_export_import_and_rejections(self):
  _,raw,_=self.request("courses",{"title":"A"});course=json.loads(raw);cid=course["id"]
  _,raw,_=self.request(f"courses/{cid}/notes",{"title":"N","markdown":"alpha beta","with_card":True});nid=json.loads(raw)["id"]
  state=json.loads(self.request(f"courses/{cid}")[1]);note=state["notes"][0]
  self.assertEqual(self.request(f"courses/{cid}/notes/{nid}/save",{"markdown":"saved","revision":note["revision"]})[0],200)
  self.assertEqual(self.request(f"courses/{cid}/notes/{nid}/save",{"markdown":"lost","revision":note["revision"]})[0],400)
  card=json.loads(self.request(f"courses/{cid}")[1])["cards"][0]
  self.assertEqual(self.request(f"courses/{cid}/map/remove-card",{"card_id":card["id"]})[0],200)
  self.assertEqual(self.request(f"courses/{cid}/map/show-card",{"note_id":nid,"position":{"x":90,"y":90}})[0],200)
  status,archive,kind=self.request(f"courses/{cid}/export",{})
  self.assertEqual((status,kind),(200,"application/vnd.synopsis+zip"))
  self.assertEqual(self.request("import",archive,"application/octet-stream")[0],201)
  self.assertEqual(self.request("import",b"broken","application/octet-stream")[0],400)
