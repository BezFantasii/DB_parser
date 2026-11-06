"""Exclusive ownership and safe stale-lock recovery for this backend's browser profiles."""
from contextlib import contextmanager
import os
from pathlib import Path
import socket


@contextmanager
def managed_profile(site):
    if site not in ("ozon","wb"):
        raise ValueError("Unknown marketplace")
    root=Path(os.environ.get("PROFILE_ROOT","backend/data/profiles")).resolve()
    profile=(root/site).resolve()
    if profile.parent!=root:
        raise ValueError("Profile must remain within PROFILE_ROOT")
    profile.mkdir(parents=True,exist_ok=True)
    with (profile/".backend-owner.lock").open("a+b") as ownership:
        if os.name!="nt":
            import fcntl
            # Another managed browser must release ownership before we inspect Chrome locks.
            fcntl.flock(ownership.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        try:
            lock=profile/"SingletonLock"
            if os.name!="nt" and lock.is_symlink():
                target=str(lock.readlink())
                host,separator,pid=target.rpartition("-")
                stale=False
                if separator and pid.isdigit():
                    if host!=socket.gethostname():
                        # Docker recreated the single owner; old hostname cannot own this profile now.
                        stale=True
                    else:
                        try:os.kill(int(pid),0)
                        except ProcessLookupError:stale=True
                        except PermissionError:pass
                if stale:
                    for name in ("SingletonLock","SingletonSocket","SingletonCookie"):
                        path=profile/name
                        if path.is_symlink():
                            path.unlink()  # Remove the symlink itself; never follow its target.
            yield profile
        finally:
            if os.name!="nt":
                fcntl.flock(ownership.fileno(),fcntl.LOCK_UN)
