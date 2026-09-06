import subprocess,shutil,json,base64,pathlib,sys
label,name=sys.argv[1:3]
js='''(async()=>{const a=[...document.querySelectorAll('a')].find(a=>a.textContent.trim().endsWith(LABEL)); if(!a) throw new Error('Download link not visible'); const r=await fetch(a.href); if(!r.ok) throw new Error('HTTP '+r.status); const b=new Uint8Array(await r.arrayBuffer()); let s=''; for(let i=0;i<b.length;i+=32768)s+=String.fromCharCode(...b.subarray(i,i+32768)); return {status:r.status,type:r.headers.get('content-type'),data:btoa(s)};})()'''.replace('LABEL',json.dumps(label))
r=subprocess.run([shutil.which('agent-browser'),'--session','book-dogfood','eval','-b',base64.b64encode(js.encode()).decode()],capture_output=True,text=True,encoding='utf-8')
if r.returncode: print('Browser fetch failed');sys.exit(1)
d=json.loads(r.stdout)
p=pathlib.Path('dogfood-output/book-20260906/downloads')/name
p.write_bytes(base64.b64decode(d['data']))
print(json.dumps({'file':str(p),'bytes':p.stat().st_size,'status':d['status'],'type':d['type']}))

