"""Explicit live API check; creates and saves one real parsing job."""
import argparse
import json
import os
from pathlib import Path
import time
from urllib.request import Request, urlopen


def run():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url",default="http://127.0.0.1:8000")
    parser.add_argument("--query",default="худи мужское")
    parser.add_argument("--site",choices=("ozon","wb"),default="ozon")
    args=parser.parse_args()
    def api(path,body=None):
        request=Request(args.url+path,data=json.dumps(body).encode() if body is not None else None,headers={"Authorization":"Bearer "+os.environ.get("API_TOKEN","local-development-token"),"Content-Type":"application/json"})
        with urlopen(request,timeout=10) as response:return json.load(response)
    job=api("/api/v1/jobs",{"marketplace":args.site,"source":args.query,"limit":5,"engine":"chrome-session" if args.site=="ozon" else "selenium","timeout":30})
    print("Job created:",job["id"],flush=True)
    deadline=time.monotonic()+150
    while job["status"] in ("queued","running") and time.monotonic()<deadline:
        time.sleep(1);job=api("/api/v1/jobs/"+job["id"])
    result=api("/api/v1/jobs/"+job["id"]+"/results")
    report={"job":job,"items":result["items"],"events":api("/api/v1/jobs/"+job["id"]+"/events")["items"]}
    target=Path("backend/test-results/backend-search-live.json");target.parent.mkdir(exist_ok=True,parents=True)
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"status":job["status"],"saved":job["saved"],"error":job.get("error")},ensure_ascii=True),flush=True)
    if job["status"]!="succeeded":
        if job["status"] in ("queued","running"):api("/api/v1/jobs/"+job["id"]+"/cancel",{})
        raise RuntimeError("Live job did not succeed; see "+str(target))
    if not result["items"]:raise RuntimeError("No saved offers")


if __name__=="__main__":run()
