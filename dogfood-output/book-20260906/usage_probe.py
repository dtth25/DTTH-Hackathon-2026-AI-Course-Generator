import json, os, datetime, urllib.request
key=os.environ['OPENROUTER_API_KEY']
out={'timestamp_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
for endpoint in ['key','credits']:
 try:
  req=urllib.request.Request('https://openrouter.ai/api/v1/'+endpoint,headers={'Authorization':'Bearer '+key})
  data=json.load(urllib.request.urlopen(req,timeout=25))['data']
  allowed=['limit','limit_remaining','usage','usage_daily','usage_weekly','usage_monthly','is_free_tier','total_credits','total_usage']
  out[endpoint]={k:data.get(k) for k in allowed if k in data}
 except Exception as e: out[endpoint]={'error':str(e)}
print(json.dumps(out,indent=2))
