"""Durable PostgreSQL queue; each job executes in a separate, cancellable process tree."""
import json
import os
from pathlib import Path
import queue
import signal
import socket
import subprocess
import sys
import threading
import time

from backend.store import Store


def terminate(process):
    if process.poll() is not None:
        return
    if os.name=="nt":
        subprocess.run(["taskkill","/PID",str(process.pid),"/T","/F"],capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW)
    else:
        try:
            os.killpg(process.pid,signal.SIGTERM)
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid,signal.SIGKILL)
        except ProcessLookupError:
            pass
    process.wait(timeout=10)


def execute(store,job,worker_id):
    job_id=str(job["id"]);attempt=job["attempt"]
    payload={k:job[k] for k in ("marketplace","source_url","options","mode")}
    log_root=Path(os.environ.get("LOG_ROOT","backend/data/logs"));log_root.mkdir(parents=True,exist_ok=True)
    messages=queue.Queue();items=None;error=None
    kwargs={"start_new_session":True} if os.name!="nt" else {"creationflags":subprocess.CREATE_NO_WINDOW|subprocess.CREATE_NEW_PROCESS_GROUP}
    with (log_root/f"{job_id}-{attempt}.log").open("w",encoding="utf-8") as stderr:
        process=subprocess.Popen([sys.executable,"-u","-m","backend.collect"],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=stderr,text=True,encoding="utf-8",**kwargs)
        process.stdin.write(json.dumps(payload,default=str)+"\n");process.stdin.close()
        def read():
            for line in process.stdout:
                try:messages.put(json.loads(line))
                except json.JSONDecodeError:messages.put({"type":"event","stage":"parser.log","data":{"message":line[:1000]}})
            messages.put(None)
        reader=threading.Thread(target=read,daemon=True);reader.start()
        start=time.monotonic();heartbeat=0;ended=False
        try:
            while not ended:
                now=time.monotonic()
                if now-start>int(os.environ.get("MAX_JOB_SECONDS","900")):
                    raise TimeoutError("Job time limit exceeded")
                if now-heartbeat>2:
                    if not store.owns(job_id,worker_id,attempt):
                        return
                    store.heartbeat(worker_id,job_id);heartbeat=now
                try:message=messages.get(timeout=.2)
                except queue.Empty:continue
                if message is None:
                    ended=True
                elif message.get("type")=="event":store.event(job_id,message["stage"],message.get("data"))
                elif message.get("type")=="result":items=message["items"]
                elif message.get("type")=="error":error=message["error"]
            code=process.wait(timeout=10)
            if error or code or items is None:
                raise RuntimeError(error or f"Parser exited with code {code} without a result; see worker log")
            store.event(job_id,"database.saving",{"items":len(items)})
            store.publish(job_id,items,worker_id,attempt)
        except Exception as exc:
            store.fail(job_id,worker_id,attempt,str(exc))
        finally:
            terminate(process)
            process.stdout.close()


def run(once=False):
    storage=Store();storage.initialize()
    worker_id=f"{socket.gethostname()}-{os.getpid()}"
    while True:
        storage.heartbeat(worker_id)
        job=storage.claim(worker_id)
        if job:execute(storage,job,worker_id)
        elif once:return
        else:time.sleep(1)


if __name__=="__main__":
    run(once="--once" in sys.argv)
