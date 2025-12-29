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

/* ========= 核心：检测签到结果（不依赖 toast DOM） ========= */
async function detectCheckinResult(page, timeoutMs = 3000) {
  const start = Date.now();

  while (Date.now() - start < timeoutMs) {
    const text = await page.evaluate(() => document.body.innerText || "");

    if (text.includes("签到成功") || text.includes("获得了")) {
      return "SUCCESS";
    }
    if (text.includes("已签到") || text.includes("无效的请求")) {
      return "ALREADY";
    }

    await page.waitForTimeout(300);
  }

  return "UNKNOWN";
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
      log("未发现签到按钮");
      await sendTG(
        `⚠️ NodeLoc 未发现签到入口\n账号：${accountStr}\n时间：${timeStr}`
      );
      process.exit(0);
    }

    log("执行签到点击（无论是否已签到）");
    await checkinBtn.click();

    log("检测签到结果（扫描页面文本）");
    const result = await detectCheckinResult(page);

    if (result === "SUCCESS") {
      log("检测到新签到成功");
      await sendTG(
        `✅ NodeLoc 签到成功\n账号：${accountStr}\n时间：${timeStr}`
      );
      process.exit(0);
    }

    if (result === "ALREADY") {
      log("检测到今日已签到");
      await sendTG(
        `🟢 NodeLoc 今日已签到\n账号：${accountStr}\n时间：${timeStr}`
      );
      process.exit(0);
    }

    // ===== 兜底：检查按钮状态 =====
    const isCheckedIn = await page.$eval(
      "button.checkin-button",
      btn => btn.classList.contains("checked-in")
    );

    if (isCheckedIn) {
      log("按钮已是 checked-in 状态，视为已签到");
      await sendTG(
        `🟢 NodeLoc 今日已签到\n账号：${accountStr}\n时间：${timeStr}`
      );
      process.exit(0);
    }

    // 真异常
    log("未识别页面结果，判定异常");
    await sendTG(
      `❌ NodeLoc 签到异常（未识别页面结果）\n账号：${accountStr}\n时间：${timeStr}`
    );
    process.exit(1);

  } catch (err) {
    console.error("[NodeLoc] 执行异常：", err.message);
    await sendTG(`❌ NodeLoc 执行异常\n${err.message}`);
    process.exit(1);
  } finally {
    log("关闭浏览器，任务结束");
    await browser.close();
  }
})();
