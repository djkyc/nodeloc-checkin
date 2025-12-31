import asyncio, time, os
from playwright.async_api import async_playwright

BASE = "https://www.nodeloc.com"
LOGIN = BASE + "/login"
U = os.getenv("NODELOC_USERNAME")
P = os.getenv("NODELOC_PASSWORD")

def log(m): print(time.strftime("[%Y-%m-%d %H:%M:%S]"), m, flush=True)

async def main():
    log("NodeLoc check-in start")
    async with async_playwright() as p:
        b = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        c = await b.new_context()
        page = await c.new_page()

        await page.goto(LOGIN, wait_until="domcontentloaded")
        await page.wait_for_selector("#login-account-name")
        await page.fill("#login-account-name", U)
        await page.fill("#login-account-password", P)
        await page.click("#login-button")
        await page.wait_for_url(BASE + "/")

        btn = await page.wait_for_selector(
            "li.header-dropdown-toggle.checkin-icon > button.checkin-button"
        )
        t1 = await btn.get_attribute("title")
        a1 = await btn.get_attribute("aria-label")
        log(f"Before: {t1}/{a1}")

        await btn.click(delay=120)
        await page.wait_for_timeout(2000)

        btn2 = await page.query_selector(
            "li.header-dropdown-toggle.checkin-icon > button.checkin-button"
        )
        if not btn2:
            log("OK: button disappeared")
        else:
            t2 = await btn2.get_attribute("title")
            a2 = await btn2.get_attribute("aria-label")
            log(f"After: {t2}/{a2}")
            log("OK" if (t1, a1) != (t2, a2) else "No change (maybe already checked in)")

        await b.close()
    log("NodeLoc check-in end")

asyncio.run(main())
