"""Real HTTP job check. No fixtures, no network response substitution."""
import argparse
import json
import os
from pathlib import Path
import time
import httpx


def main():
    cli=argparse.ArgumentParser()
    cli.add_argument("--base",default="http://127.0.0.1:8000")
    cli.add_argument("--source",default="наушники")
    cli.add_argument("--wait",type=int,default=180)
    cli.add_argument("--marketplace",choices=["both","ozon","wb"],default="both")
    args=cli.parse_args()
    root=Path(__file__).parent/"test-results";root.mkdir(exist_ok=True)
    with httpx.Client(base_url=args.base,headers={"Authorization":"Bearer "+os.environ.get("API_TOKEN","local-development-token")},timeout=20) as client:
        ids=[]
        for site in (("ozon","wb") if args.marketplace=="both" else (args.marketplace,)):
            r=client.post("/api/v1/jobs",json={"marketplace":site,"source":args.source,"limit":1,"pages":1,"scrolls":2,"delay":2,"timeout":20,"headed":True})
            r.raise_for_status();ids.append(r.json()["id"])
        cursors={i:0 for i in ids};end=time.monotonic()+args.wait
        while time.monotonic()<end:
            jobs=[]
            for job_id in ids:
                j=client.get(f"/api/v1/jobs/{job_id}").json();jobs.append(j)
                events=client.get(f"/api/v1/jobs/{job_id}/events",params={"after_id":cursors[job_id]}).json()
                for event in events["items"]:print(j["marketplace"],event["stage"],json.dumps(event["data"],ensure_ascii=False),flush=True)
                cursors[job_id]=events["next_cursor"]
            if all(j["status"] in ("succeeded","failed","blocked","cancelled") for j in jobs):break
            time.sleep(2)
        report={"jobs":[client.get(f"/api/v1/jobs/{i}").json() for i in ids],"results":{i:client.get(f"/api/v1/jobs/{i}/results").json() for i in ids}}
        for j in report["jobs"]:
            if j["status"] in ("running","queued"):
                client.post(f"/api/v1/jobs/{j['id']}/cancel")
        report_name="live-backend.json" if args.marketplace=="both" else f"live-backend-{args.marketplace}.json"
        (root/report_name).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
        print(json.dumps({"statuses":{j["marketplace"]:j["status"] for j in report["jobs"]}},ensure_ascii=False))


if __name__=="__main__":main()
