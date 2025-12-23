const { chromium } = require("playwright");
const axios = require("axios");

const BASE = "https://www.nodeloc.com";

const NODELOC_COOKIE = (process.env.NODELOC_COOKIE || "").trim();
const NODELOC_EMAIL = (process.env.NODELOC_EMAIL || "").trim();

const LOGIN_EMAIL = (process.env.NODELOC_LOGIN_EMAIL || "").trim();
const LOGIN_PASSWORD = (process.env.NODELOC_LOGIN_PASSWORD || "").trim();

const COOKIE_TG_MODE = (process.env.NODELOC_COOKIE_TG_MODE || "safe").toLowerCase();

/* ================== TG ================== */
async function sendTG(message) {
  const TG_TOKEN = process.env.TG_BOT_TOKEN;
  const TG_USER_ID = process.env.TG_USER_ID;
  if (!TG_TOKEN || !TG_USER_ID) return;
  try {
    await axios.post(`https://api.telegram.org/bot${TG_TOKEN}/sendMessage`, {
      chat_id: TG_USER_ID,
      text: message,
    });
  } catch (e) {
    console.error("TG 发送失败：", e.message);
  }
}

/* ================== 工具函数 ================== */
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

function maskEmail(email) {
  if (!email.includes("@")) return "***";
  const [u, d] = email.split("@");
  if (u.length <= 1) return "*@" + d;
  if (u.length === 2) return u[0] + "*@" + d;
  return u.slice(0, 2) + "*".repeat(u.length - 2) + "@" + d;
}

function formatBeijingTime(date = new Date()) {
  const bj = new Date(date.getTime() + 8 * 60 * 60 * 1000);
  const pad = n => String(n).padStart(2, "0");
  return (
    bj.getUTCFullYear() +
    ":" +
    pad(bj.getUTCMonth() + 1) +
    ":" +
    pad(bj.getUTCDate()) +
    ":" +
    pad(bj.getUTCHours()) +
    ":" +
    pad(bj.getUTCMinutes())
  );
}

function cookieSummary(cookieStr) {
  return cookieStr
    .split(";")
    .map(p => {
      const [k, v] = p.split("=");
      if (!v) return k;
      return `${k}=${v.slice(0, 4)}…${v.slice(-3)}`;
    })
    .join("\n");
}

/* ================== 自动登录刷新 Cookie ================== */
async function reloginAndRefresh(page) {
  if (!LOGIN_EMAIL || !LOGIN_PASSWORD) return null;

  await page.goto(`${BASE}/login`, {
    waitUntil: "domcontentloaded",
    timeout: 60000,
  });

  await page.fill('input[name="login"]', LOGIN_EMAIL);
  await page.fill('input[name="password"]', LOGIN_PASSWORD);
  await page.click('button[type="submit"]');

  // 若有验证码/2FA，这里会超时
  await page.waitForSelector("img.avatar", { timeout: 30000 });

  const cookies = await page.context().cookies(BASE);
  return cookies.map(c => `${c.name}=${c.value}`).join("; ");
}

/* ================== 主流程 ================== */
(async () => {
  if (!NODELOC_COOKIE) {
    await sendTG("❌ NodeLoc Cookie 缺失，请先设置 NODELOC_COOKIE");
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
    await page.goto(BASE, { waitUntil: "domcontentloaded", timeout: 60000 });
    await page.waitForTimeout(3000);

    let checkinIcon = await page.$("li.header-dropdown-toggle.checkin-icon");
    let cookieUsed = NODELOC_COOKIE;

    // Cookie 失效 → 自动刷新
    if (!checkinIcon) {
      const newCookie = await reloginAndRefresh(page);
      if (!newCookie) {
        await sendTG("❌ NodeLoc Cookie 已失效，且未配置自动登录");
        process.exit(1);
      }

      await context.clearCookies();
      await context.addCookies(parseCookies(newCookie));
      cookieUsed = newCookie;

      await page.goto(BASE, { waitUntil: "domcontentloaded" });
      await page.waitForTimeout(3000);

      checkinIcon = await page.$("li.header-dropdown-toggle.checkin-icon");
      if (!checkinIcon) {
        await sendTG("❌ NodeLoc 自动登录失败（可能需要验证码/2FA）");
        process.exit(1);
      }

      const timeStr = formatBeijingTime();
      const accountStr = NODELOC_EMAIL ? maskEmail(NODELOC_EMAIL) : "（邮箱未配置）";

      let msg =
        "♻️ NodeLoc Cookie 已自动刷新\n" +
        `账号：${accountStr}\n` +
        `时间：${timeStr}\n\n`;

      if (COOKIE_TG_MODE === "full") {
        msg += "NEW NODELOC_COOKIE：\n" + cookieUsed;
      } else {
        msg +=
          "Cookie 摘要：\n" +
          cookieSummary(cookieUsed) +
          "\n\n请到 Actions 日志复制完整 Cookie 更新 Secrets";
      }

      await sendTG(msg);
      console.log("NEW NODELOC_COOKIE:\n", cookieUsed);
    }

    const timeStr = formatBeijingTime();
    const displayAccount = NODELOC_EMAIL
      ? maskEmail(NODELOC_EMAIL)
      : "（邮箱未配置）";

    const alreadySigned = await page.$(".d-icon-calendar-check");
    if (alreadySigned) {
      await sendTG(
        `🟢 NodeLoc 今日已签到\n账号：${displayAccount}\n时间：${timeStr}`
      );
      process.exit(0);
    }

    const checkinBtn = await page.$("button.checkin-button");
    if (!checkinBtn) {
      await sendTG(
        `⚠️ NodeLoc 未发现签到入口\n账号：${displayAccount}\n时间：${timeStr}`
      );
      process.exit(0);
    }

    await checkinBtn.click();
    await page.waitForTimeout(3000);

    await sendTG(
      `✅ NodeLoc 签到成功\n账号：${displayAccount}\n时间：${timeStr}`
    );

  } catch (err) {
    await sendTG(`❌ NodeLoc 执行异常\n${err.message}`);
    process.exit(1);
  } finally {
    await browser.close();
  }
})();
