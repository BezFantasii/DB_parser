"""Browser compatibility check; uses data: HTML, never substitutes for a live-site test."""
from pathlib import Path
from parsers import ParserOzon,ParserWildberries
from contracts import normalize_item,dumps
import tempfile
import os
from backend.profiles import managed_profile

root=Path(__file__).resolve().parents[2]
for site,kind,file,url in [("ozon",ParserOzon,"ozon_product.html","https://www.ozon.ru/product/test-123/"),("wb",ParserWildberries,"wb_current.html","https://www.wildberries.ru/catalog/456/detail.aspx")]:
    parser=kind(url,headed=True)
    driver=parser._create_browser()
    try:
        driver.get("data:text/html;charset=utf-8,"+__import__('urllib.parse',fromlist=['quote']).quote((root/"tests/fixtures"/file).read_text(encoding="utf-8")))
        item=normalize_item(parser._parse_data(driver.page_source,url),site)
        assert item["price"] is not None
        print(dumps({"site":site,"engine":"real Chromium / UC / Selenium","item":item}),flush=True)
    finally:
        driver.quit()

if os.name!="nt":
    # Chromium may finish asynchronous profile writes after quit; cleanup is best-effort in /tmp.
    with tempfile.TemporaryDirectory(prefix="profile-recovery-",ignore_cleanup_errors=True) as directory:
        previous=os.environ.get("PROFILE_ROOT")
        os.environ["PROFILE_ROOT"]=directory
        profile=Path(directory)/"ozon";profile.mkdir()
        (profile/"SingletonLock").symlink_to("previous-stopped-container-99999999")
        (profile/"SingletonSocket").symlink_to("/tmp/old-nonexistent-socket")
        with managed_profile("ozon") as recovered:
            assert not (recovered/"SingletonLock").is_symlink()
            parser=ParserOzon("https://www.ozon.ru/product/test-123/",profile=recovered)
            driver=parser._create_browser()
            try:driver.get("data:text/html,<h1>profile recovery</h1>");assert "profile recovery" in driver.title or "profile recovery" in driver.page_source
            finally:driver.quit()
        if previous is None:os.environ.pop("PROFILE_ROOT",None)
        else:os.environ["PROFILE_ROOT"]=previous
        print("PASS stale profile from a recreated container safely opens again",flush=True)
