import subprocess,shutil,json,base64,pathlib,urllib.request,urllib.parse
js="(()=>{const a=[...document.querySelectorAll('a')].find(a=>a.textContent.trim().endsWith('MP4'));if(!a)throw new Error('No visible MP4 link');return a.href;})()"
r=subprocess.run([shutil.which('agent-browser'),'--session','book-dogfood','eval','-b',base64.b64encode(js.encode()).decode()],capture_output=True,text=True,encoding='utf-8')
u=json.loads(r.stdout)
assert urllib.parse.urlparse(u).hostname in ['localhost','127.0.0.1']
p=pathlib.Path('dogfood-output/book-20260906/downloads/video.mp4')
with urllib.request.urlopen(u,timeout=120) as response,p.open('wb') as out:
 shutil.copyfileobj(response,out)
 print(json.dumps({'status':response.status,'type':response.headers.get('content-type'),'file':str(p),'bytes':p.stat().st_size}))
