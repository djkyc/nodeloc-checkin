const { chromium } = require("playwright");
const axios = require("axios");

const BASE = "https://www.nodeloc.com";

/* ========== 环境变量 ========== */
const NODELOC_COOKIE = (process.env.NODELOC_COOKIE || "").trim();
const LOGIN_EMAIL = (process.env.NODELOC_LOGIN_EMAIL || "").trim();

/* ========== 日志 ========= */
function log(msg) {
  console.log(`[NodeLoc] ${msg}`);
}

/* ========== TG ========= */
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
    console.error("[NodeLoc][TG] 发送失败：", e.message);
  }
}

/* ========== 工具 ========= */
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
  if (!email || !email.includes("@")) return "***";
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

/* ===== 新增：Cookie 剩余天数 ===== */
async function getCookieRemainDays(context) {
  const cookies = await context.cookies(BASE);
  const now = Date.now() / 1000;

  const target =
    cookies.find(c => c.name === "_t") ||
    cookies.find(c => c.name === "_forum_session");

  if (!target || !target.expires || target.expires < now) {
    return 0;
  }

  return Math.floor((target.expires - now) / 86400);
}

/* ========== 主流程 ========= */
(async () => {
  log("启动 NodeLoc 签到任务");

  if (!NODELOC_COOKIE) {
    await sendTG("❌ NodeLoc Cookie 缺失");
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

    const timeStr = formatBeijingTime();
    const accountStr = LOGIN_EMAIL ? maskEmail(LOGIN_EMAIL) : "（邮箱未配置）";

    const checkinBtn = await page.$("button.checkin-button");
    if (!checkinBtn) {
      await sendTG(`⚠️ NodeLoc 未发现签到入口\n账号：${accountStr}\n时间：${timeStr}`);
      process.exit(0);
    }

    // ===== Cookie 存活天数统计 =====
    const remainDays = await getCookieRemainDays(context);
    log(`Cookie 剩余有效期：${remainDays} 天`);

    if (remainDays > 0 && remainDays <= 3) {
      await sendTG(
        `⚠️ NodeLoc Cookie 即将过期\n剩余：${remainDays} 天`
      );
    }

    // ===== 已签到判断 =====
    const alreadySigned = await checkinBtn.evaluate(btn => {
      const text =
        (btn.getAttribute("title") || "") +
        (btn.getAttribute("aria-label") || "");
      return btn.classList.contains("checked-in") || text.includes("已签到");
    });

    if (alreadySigned) {
      await sendTG(
        `🟢 NodeLoc 今日已签到\n账号：${accountStr}\n时间：${timeStr}`
      );
      process.exit(0);
    }

    // ===== 执行签到 =====
    await checkinBtn.click();

    await page.waitForFunction(() => {
      const btn = document.querySelector("button.checkin-button");
      if (!btn) return false;
      const text =
        (btn.getAttribute("title") || "") +
        (btn.getAttribute("aria-label") || "");
      return btn.classList.contains("checked-in") || text.includes("已签到");
    }, { timeout: 10000 });

    await sendTG(
      `✅ NodeLoc 签到成功\n账号：${accountStr}\n时间：${timeStr}`
    );

  } catch (err) {
    await sendTG(`❌ NodeLoc 执行异常\n${err.message}`);
    process.exit(1);
  } finally {
    log("关闭浏览器，任务结束");
    await browser.close();
  }
})();
