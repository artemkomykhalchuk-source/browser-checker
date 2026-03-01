import os
import time
from typing import List, Optional, Dict, Any

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, AnyHttpUrl
from playwright.async_api import async_playwright

API_KEY = os.environ.get("API_KEY", "")
NAV_TIMEOUT_MS = int(os.environ.get("NAV_TIMEOUT_MS", "30000"))
WAIT_AFTER_LOAD_MS = int(os.environ.get("WAIT_AFTER_LOAD_MS", "1500"))
USER_AGENT = os.environ.get("USER_AGENT", "QA-BrowserChecker/1.0 (+monitoring)")

app = FastAPI()

class RunRequest(BaseModel):
  urls: List[AnyHttpUrl]
  must_contain: Optional[str] = None

@app.get("/health")
def health():
  return {"ok": True}

@app.post("/run")
async def run(req: RunRequest, x_api_key: str = Header(default="")):
  if not API_KEY or x_api_key != API_KEY:
    raise HTTPException(status_code=401, detail="Unauthorized")

  results: List[Dict[str, Any]] = []

  async with async_playwright() as p:
    browser = await p.chromium.launch(headless=True)
    context = await browser.new_context(user_agent=USER_AGENT)

    for url in req.urls:
      item: Dict[str, Any] = {"url": str(url), "ok": False}
      t0 = time.time()
      try:
        page = await context.new_page()
        resp = await page.goto(str(url), wait_until="load", timeout=NAV_TIMEOUT_MS)

        if WAIT_AFTER_LOAD_MS > 0:
          await page.wait_for_timeout(WAIT_AFTER_LOAD_MS)

        title = await page.title()
        final_url = page.url
        status = resp.status if resp else None

        html = await page.content()
        contains_ok = True
        if req.must_contain:
          contains_ok = (req.must_contain in html)

        ms = int((time.time() - t0) * 1000)

        item.update({
          "ok": (status is not None and status < 400 and contains_ok),
          "status": status,
          "title": title[:200],
          "final_url": final_url,
          "load_ms": ms,
          "contains_ok": contains_ok
        })

        await page.close()

      except Exception as e:
        ms = int((time.time() - t0) * 1000)
        item.update({
          "ok": False,
          "status": None,
          "title": "",
          "final_url": "",
          "load_ms": ms,
          "contains_ok": False,
          "error": f"{type(e).__name__}: {str(e)[:240]}"
        })

      results.append(item)

    await context.close()
    await browser.close()

  return {"results": results}
