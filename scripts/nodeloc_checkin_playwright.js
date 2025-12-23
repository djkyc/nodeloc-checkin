const { chromium } = require("playwright");
const axios = require("axios");
const fs = require("fs");

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

    await page.waitForTimeout(5000);

    // 1️⃣ 截图（无论成功/失败都留证据）
    await page.screenshot({ path: "nodeloc_page.png", fullPage: true });

    // 2️⃣ 确认登录态
    const loggedIn = await page
      .locator("img.avatar")
      .first()
      .isVisible()
      .catch(() => false);

    if (!loggedIn) {
      throw new Error("Cookie 失效：未检测到登录态");
    }

    // 3️⃣ 查找“签到相关元素”（更宽松）
    const result = await page.evaluate(() => {
      const textHit = [...document.querySelectorAll("a,button,div,span")]
        .find(el => el.innerText && el.innerText.includes("签到"));

      if (textHit) {
        textHit.click();
        return { status: "clicked" };
      }

      // 没找到按钮，但看看有没有“已签到”提示
      const signed = [...document.body.innerText.split("\n")]
        .some(t => t.includes("已签到") || t.includes("今日已"));

      if (signed) {
        return { status: "already_signed" };
      }

      return { status: "not_found" };
    });

    if (result.status === "clicked") {
      await page.waitForTimeout(3000);
      console.log("✅ NodeLoc 签到成功（点击完成）");
      await sendTG("✅ NodeLoc 已自动签到（Playwright）");
      process.exit(0);
    }

    if (result.status === "already_signed") {
      console.log("🟢 NodeLoc 今日已签到（无需重复）");
      await sendTG("🟢 NodeLoc 今日已签到（跳过）");
      process.exit(0);
    }

    // 都不是 → 真异常
    throw new Error("页面未发现签到入口（请查看截图）");

  } catch (err) {
    console.error("❌ NodeLoc 签到失败：", err.message);
    await sendTG(`❌ NodeLoc 签到失败：${err.message}`);
    process.exit(1);
  } finally {
    await browser.close();
  }
})();
