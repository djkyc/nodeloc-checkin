const { chromium } = require("playwright");
const axios = require("axios");

const BASE = "https://www.nodeloc.com";

/* ========== 环境变量 ========== */
const NODELOC_COOKIE = (process.env.NODELOC_COOKIE || "").trim();
const LOGIN_EMAIL = (process.env.NODELOC_LOGIN_EMAIL || "").trim();
const LOGIN_PASSWORD = (process.env.NODELOC_LOGIN_PASSWORD || "").trim();
const COOKIE_TG_MODE = (process.env.NODELOC_COOKIE_TG_MODE || "safe").toLowerCase();

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

/* ========== 工具函数 ========= */
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
      log("未找到签到按钮");
      await sendTG(`⚠️ NodeLoc 未发现签到入口\n账号：${accountStr}\n时间：${timeStr}`);
      process.exit(0);
    }

    // 🔑 关键：点击前判断是否已签到
    const alreadyCheckedIn = await checkinBtn.evaluate(btn =>
      btn.classList.contains("checked-in")
    );

    if (alreadyCheckedIn) {
      log("按钮已处于 checked-in 状态，今日已签到");
      await sendTG(`🟢 NodeLoc 今日已签到\n账号：${accountStr}\n时间：${timeStr}`);
      process.exit(0);
    }

    // 未签到，执行点击
    log("检测到未签到状态，执行签到点击");
    await checkinBtn.click();

    // 🔑 关键：等待按钮进入 checked-in 状态
    try {
      await page.waitForFunction(
        () => {
          const btn = document.querySelector("button.checkin-button");
          return btn && btn.classList.contains("checked-in");
        },
        { timeout: 10000 }
      );
    } catch {
      log("点击后按钮未进入 checked-in 状态，签到失败");
      await sendTG(`❌ NodeLoc 签到失败（状态未变化）\n账号：${accountStr}\n时间：${timeStr}`);
      process.exit(1);
    }

    log("检测到按钮进入 checked-in 状态，签到成功");
    await sendTG(`✅ NodeLoc 签到成功\n账号：${accountStr}\n时间：${timeStr}`);

  } catch (err) {
    console.error("[NodeLoc] 执行异常：", err.message);
    await sendTG(`❌ NodeLoc 执行异常\n${err.message}`);
    process.exit(1);
  } finally {
    log("关闭浏览器，任务结束");
    await browser.close();
  }
})();
