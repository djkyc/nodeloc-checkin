const { chromium } = require("playwright");
const axios = require("axios");

const BASE = "https://www.nodeloc.com";

// 必需：登录后的 Cookie
const NODELOC_COOKIE = (process.env.NODELOC_COOKIE || "").trim();

// 可选：邮箱（只用于展示，自动打码）
const NODELOC_EMAIL = (process.env.NODELOC_EMAIL || "").trim();

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

/* ================== 打码规则 ================== */
// 邮箱：保留前 2 位 + 域名
function maskEmail(email) {
  if (!email.includes("@")) return "";
  const [user, domain] = email.split("@");
  if (user.length <= 1) return "*@" + domain;
  if (user.length === 2) return user[0] + "*@" + domain;
  return user.slice(0, 2) + "*".repeat(user.length - 2) + "@" + domain;
}

// 用户名：首尾保留
function maskName(name) {
  if (!name) return "***";
  if (name.length === 1) return "*";
  if (name.length === 2) return name[0] + "*";
  return name[0] + "*".repeat(name.length - 2) + name[name.length - 1];
}

/* ================== 北京时间 ================== */
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
    await page.goto(BASE, {
      waitUntil: "domcontentloaded",
      timeout: 60000,
    });

    await page.waitForSelector("header", { timeout: 20000 });
    await page.waitForTimeout(3000);

    // 判断 Cookie 是否有效（是否存在签到入口）
    const checkinIcon = await page.$(
      "li.header-dropdown-toggle.checkin-icon"
    );

    const timeStr = formatBeijingTime();

    if (!checkinIcon) {
      await sendTG(
        `❌ NodeLoc Cookie 已失效\n时间：${timeStr}`
      );
      process.exit(1);
    }

    // 读取页面账号身份（username）
    const rawAccount = await page.evaluate(() => {
      const img = document.querySelector("img.avatar");
      return (
        img?.getAttribute("alt") ||
        img?.getAttribute("title") ||
        ""
      );
    });

    // 展示账号逻辑：邮箱优先，其次 username（全部打码）
    let displayAccount = "";
    if (NODELOC_EMAIL) {
      displayAccount = maskEmail(NODELOC_EMAIL);
    } else {
      displayAccount = maskName(rawAccount);
    }

    // 已签到
    const alreadySigned = await page.$(".d-icon-calendar-check");
    if (alreadySigned) {
      await sendTG(
        `🟢 NodeLoc 今日已签到\n` +
        `账号：${displayAccount}\n` +
        `时间：${timeStr}`
      );
      process.exit(0);
    }

    // 未签到 → 点击
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
    await sendTG(
      `❌ NodeLoc 签到异常\n` +
      `错误：${err.message}`
    );
    process.exit(1);
  } finally {
    await browser.close();
  }
})();
