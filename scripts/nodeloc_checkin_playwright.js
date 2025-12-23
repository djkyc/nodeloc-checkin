/**
 * NodeLoc Playwright 自动签到（真浏览器）
 *
 * 必需环境变量：
 *   NODELOC_COOKIE = 浏览器登录后的 Cookie（整串）
 *
 * 可选：
 *   TG_BOT_TOKEN / TG_USER_ID
 */

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
    .map(c => c.trim())
    .filter(Boolean)
    .map(c => {
      const i = c.indexOf("=");
      return {
        name: c.slice(0, i),
        value: c.slice(i + 1),
        domain: "www.nodeloc.com",
        path: "/",
        httpOnly: false,
        secure: true,
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

  const context = await browser.newContext();

  // 写入 Cookie
  await context.addCookies(parseCookies(NODELOC_COOKIE));

  const page = await context.newPage();

  try {
    // 打开首页（必须）
    await page.goto(BASE, { waitUntil: "networkidle" });

    // 等页面加载完成
    await page.waitForTimeout(3000);

    // 判断是否已登录
    const loggedIn = await page.locator("img.avatar").first().isVisible().catch(() => false);
    if (!loggedIn) {
      throw new Error("Cookie 无效：页面未显示登录态");
    }

    // 点击签到按钮
    // NodeLoc 签到一般在页面右上角/用户菜单
    // 直接执行页面 JS（最稳）
    const result = await page.evaluate(async () => {
      const btn =
        document.querySelector('[data-action="checkin"]') ||
        [...document.querySelectorAll("button, a")].find(el =>
          el.innerText.includes("签到")
        );

      if (!btn) return { ok: false, msg: "未找到签到按钮（可能已签到）" };

      btn.click();
      return { ok: true };
    });

    await page.waitForTimeout(3000);

    if (!result.ok) {
      throw new Error(result.msg);
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
