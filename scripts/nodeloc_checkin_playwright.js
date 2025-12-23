const { chromium } = require("playwright");
const axios = require("axios");

const BASE = "https://www.nodeloc.com";
const NODELOC_COOKIE = (process.env.NODELOC_COOKIE || "").trim();

async function sendTG(message) {
  const TG_TOKEN = process.env.TG_BOT_TOKEN;
  const TG_USER_ID = process.env.TG_USER_ID;
  if (!TG_TOKEN || !TG_USER_ID) return;
  try {
    await axios.post(`https://api.telegram.org/bot${TG_TOKEN}/sendMessage`, {
      chat_id: TG_USER_ID,
      text: message,
    });
  } catch {}
}

function parseCookies(cookieStr) {
  return cookieStr
    .split(";")
    .map(s => s.trim())
    .filter(Boolean)
    .map(c => {
      const i = c.indexOf("=");
      return {
        name: c.slice(0, i),
        value: c.slice(i + 1),
        domain: "www.nodeloc.com",
        path: "/",
        secure: true,
        httpOnly: false,
      };
    });
}

(async () => {
  if (!NODELOC_COOKIE) {
    console.error("❌ 缺少 NODELOC_COOKIE");
    process.exit(1);
  }

  const browser = await chromium.launch({
    headless: true,
    args: ["--no-sandbox", "--disable-setuid-sandbox"],
  });

  const context = await browser.newContext({
    viewport: { width: 1280, height: 800 },
  });

  await context.addCookies(parseCookies(NODELOC_COOKIE));

  const page = await context.newPage();

  try {
    // ✅ 关键修复点
    await page.goto(BASE, {
      waitUntil: "domcontentloaded",
      timeout: 60000,
    });

    // 手动等待页面稳定（非常重要）
    await page.waitForTimeout(5000);

    // 校验登录态（头像是否存在）
    const loggedIn = await page
      .locator("img.avatar")
      .first()
      .isVisible()
      .catch(() => false);

    if (!loggedIn) {
      throw new Error("Cookie 已失效：页面未显示登录态");
    }

    // 点击签到按钮（执行页面 JS）
    const clicked = await page.evaluate(() => {
      const btn =
        document.querySelector('[data-action="checkin"]') ||
        [...document.querySelectorAll("button, a")].find(el =>
          el.innerText.includes("签到")
        );

      if (!btn) return false;
      btn.click();
      return true;
    });

    await page.waitForTimeout(3000);

    if (!clicked) {
      throw new Error("未找到签到按钮（可能已签到或页面结构变化）");
    }

    console.log("✅ NodeLoc 签到成功（Playwright）");
    await sendTG("✅ NodeLoc Playwright 签到成功");
  } catch (err) {
    console.error("❌ NodeLoc 签到失败：", err.message);
    await sendTG(`❌ NodeLoc 签到失败：${err.message}`);
    process.exit(1);
  } finally {
    await browser.close();
  }
})();
