const { chromium } = require("playwright");
const axios = require("axios");

const BASE = "https://www.nodeloc.com";

// 必需：登录后的 Cookie
const NODELOC_COOKIE = (process.env.NODELOC_COOKIE || "").trim();

// 可选：仅用于 TG 展示的邮箱（打码显示）
const DISPLAY_EMAIL = (process.env.NODELOC_EMAIL || "").trim();

/* ================== TG 推送 ================== */
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

/* ================== Cookie 解析 ================== */
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

/* ================== 打码逻辑 ================== */
function maskEmail(email) {
  if (!email || !email.includes("@")) return "";
  const [user, domain] = email.split("@");
  if (user.length <= 2) return user[0] + "*@" + domain;
  return (
    user.slice(0, 2) +
    "*".repeat(Math.max(1, user.length - 2)) +
    "@" +
    domain
  );
}

function maskName(name) {
  if (!name) return "***";
  if (name.length === 1) return "*";
  if (name.length === 2) return name[0] + "*";
  return name[0] + "*".repeat(name.length - 2) + name[name.length - 1];
}

/* ================== 时间格式 ================== */
function formatTime(date = new Date()) {
  const pad = n => String(n).padStart(2, "0");
  return (
    date.getFullYear() +
    ":" +
    pad(date.getMonth() + 1) +
    ":" +
    pad(date.getDate()) +
    ":" +
    pad(date.getHours()) +
    ":" +
    pad(date.getMinutes())
  );
}

/* ================== 主流程 ================== */
(async () => {
  if (!NODELOC_COOKIE) {
    await sendTG("❌ NodeLoc Cookie 缺失，请重新登录并更新");
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
    // 打开首页
    await page.goto(BASE, {
      waitUntil: "domcontentloaded",
      timeout: 60000,
    });

    // 等 header 就绪
    await page.waitForSelector("header", { timeout: 20000 });
    await page.waitForTimeout(3000);

    // 检测是否登录（签到图标是否存在）
    const checkinIcon = await page.$(
      "li.header-dropdown-toggle.checkin-icon"
    );

    if (!checkinIcon) {
      await sendTG("❌ NodeLoc Cookie 已失效，请重新无痕登录并更新");
      process.exit(1);
    }

    // 读取登录后的账号身份（username）
    const rawAccount = await page.evaluate(() => {
      const img = document.querySelector("img.avatar");
      return (
        img?.getAttribute("alt") ||
        img?.getAttribute("title") ||
        ""
      );
    });

    // 账号展示逻辑：邮箱优先，否则 username
    let displayAccount = "";
    if (DISPLAY_EMAIL) {
      displayAccount = maskEmail(DISPLAY_EMAIL);
    } else {
      displayAccount = maskName(rawAccount);
    }

    const timeStr = formatTime();

    // 判断是否已签到
    const alreadySigned = await page.$(".d-icon-calendar-check");
    if (alreadySigned) {
      await sendTG(
        `🟢 NodeLoc 今日已签到\n` +
        `账号：${displayAccount}\n` +
        `时间：${timeStr}`
      );
      process.exit(0);
    }

    // 未签到 → 点击签到
    const checkinBtn = await page.$("button.checkin-button");
    if (!checkinBtn) {
      await sendTG(
        `⚠️ NodeLoc 未发现签到入口\n` +
        `账号：${displayAccount}\n` +
        `时间：${timeStr}`
      );
      process.exit(0);
    }

    await checkinBtn.click();
    await page.waitForTimeout(3000);

    await sendTG(
      `✅ NodeLoc 签到成功\n` +
      `账号：${displayAccount}\n` +
      `时间：${timeStr}`
    );

  } catch (err) {
    await sendTG(`❌ NodeLoc 签到异常\n${err.message}`);
    process.exit(1);
  } finally {
    await browser.close();
  }
})();
