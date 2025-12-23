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
    await page.goto(BASE, {
      waitUntil: "domcontentloaded",
      timeout: 60000,
    });

    // 等页面和头部完全就绪
    await page.waitForSelector(".header-dropdown-toggle", { timeout: 20000 });
    await page.waitForTimeout(3000);

    // ① 是否存在签到图标（判断是否登录）
    const hasCheckinIcon = await page.$("li.header-dropdown-toggle.checkin-icon");
    if (!hasCheckinIcon) {
      throw new Error("未检测到签到入口（可能未登录）");
    }

    // ② 是否已签到（calendar-check）
    const alreadySigned = await page.$(".d-icon-calendar-check");
    if (alreadySigned) {
      console.log("🟢 NodeLoc 今日已签到");
      await sendTG("🟢 NodeLoc 今日已签到");
      process.exit(0);
    }

    // ③ 未签到 → 点击签到按钮
    const checkinBtn = await page.$("button.checkin-button");
    if (!checkinBtn) {
      throw new Error("未找到签到按钮（DOM 结构异常）");
    }

    await checkinBtn.click();
    await page.waitForTimeout(3000);

    console.log("✅ NodeLoc 签到成功");
    await sendTG("✅ NodeLoc 签到成功");

  } catch (err) {
    console.error("❌ NodeLoc 签到失败：", err.message);
    await sendTG(`❌ NodeLoc 签到失败：${err.message}`);
    process.exit(1);
  } finally {
    await browser.close();
  }
})();
