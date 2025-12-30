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

function formatBeijingTime() {
  const bj = new Date(Date.now() + 8 * 3600 * 1000);
  const p = n => String(n).padStart(2, "0");
  return `${bj.getUTCFullYear()}:${p(bj.getUTCMonth() + 1)}:${p(
    bj.getUTCDate()
  )}:${p(bj.getUTCHours())}:${p(bj.getUTCMinutes())}`;
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
    log("打开 NodeLoc 首页");
    await page.goto(BASE, { waitUntil: "domcontentloaded", timeout: 60000 });
    await page.waitForTimeout(3000);

    const timeStr = formatBeijingTime();
    const accountStr = LOGIN_EMAIL ? maskEmail(LOGIN_EMAIL) : "（邮箱未配置）";

    const btn = await page.$("button.checkin-button");
    if (!btn) {
      log("未发现签到按钮");
      await sendTG(
        `⚠️ NodeLoc 未发现签到入口\n账号：${accountStr}\n时间：${timeStr}`
      );
      process.exit(0);
    }

    // ===== 点击前状态判断 =====
    const before = await btn.evaluate(b => ({
      checked: b.classList.contains("checked-in"),
      disabled: b.disabled,
      text:
        (b.getAttribute("title") || "") +
        (b.getAttribute("aria-label") || ""),
    }));

    if (before.checked || before.disabled || before.text.includes("已签到")) {
      log("点击前检测为已签到状态");
      await sendTG(
        `🟢 NodeLoc 今日已签到\n账号：${accountStr}\n时间：${timeStr}`
      );
      process.exit(0);
    }

    // ===== 核心修复：用页面 JS 触发点击 =====
    log("未签到，使用页面 JS 触发签到点击");

    await page.waitForFunction(() => {
      const b = document.querySelector("button.checkin-button");
      return b && !b.disabled;
    }, { timeout: 3000 });

    await page.evaluate(() => {
      const b = document.querySelector("button.checkin-button");
      if (b) b.click();
    });

    await page.waitForTimeout(500);

    // ===== 等待状态变化 =====
    try {
      await page.waitForFunction(() => {
        const b = document.querySelector("button.checkin-button");
        if (!b) return false;
        const t =
          (b.getAttribute("title") || "") +
          (b.getAttribute("aria-label") || "");
        return (
          b.classList.contains("checked-in") ||
          b.disabled ||
          t.includes("已签到")
        );
      }, { timeout: 8000 });
    } catch {
      log("点击后未进入已签到状态");
      await sendTG(
        `❌ NodeLoc 签到失败（未触发成功）\n账号：${accountStr}\n时间：${timeStr}`
      );
      process.exit(1);
    }

    log("签到状态已更新，签到成功");
    await sendTG(
      `✅ NodeLoc 签到成功\n账号：${accountStr}\n时间：${timeStr}`
    );

  } catch (err) {
    console.error("[NodeLoc] 执行异常：", err.message);
    await sendTG(`❌ NodeLoc 执行异常\n${err.message}`);
    process.exit(1);
  } finally {
    log("关闭浏览器，任务结束");
    await browser.close();
  }
})();
