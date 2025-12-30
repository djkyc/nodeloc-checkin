const { chromium } = require("playwright");
const axios = require("axios");

const BASE = "https://www.nodeloc.com";

/* ===== 环境变量 ===== */
const NODELOC_COOKIE = (process.env.NODELOC_COOKIE || "").trim();
const LOGIN_EMAIL = (process.env.NODELOC_LOGIN_EMAIL || "").trim();

/* ===== 日志 ===== */
function log(msg) {
  console.log(`[NodeLoc] ${msg}`);
}

/* ===== TG ===== */
async function sendTG(message) {
  const TG_TOKEN = process.env.TG_BOT_TOKEN;
  const TG_USER_ID = process.env.TG_USER_ID;
  if (!TG_TOKEN || !TG_USER_ID) return;
  await axios.post(`https://api.telegram.org/bot${TG_TOKEN}/sendMessage`, {
    chat_id: TG_USER_ID,
    text: message,
  });
}

/* ===== 工具 ===== */
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
  return `${bj.getUTCFullYear()}:${p(bj.getUTCMonth()+1)}:${p(bj.getUTCDate())}:${p(bj.getUTCHours())}:${p(bj.getUTCMinutes())}`;
}

/* ===== 主流程 ===== */
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

    const btn = await page.$("button.checkin-button");
    if (!btn) {
      log("未找到签到按钮");
      await sendTG(
        `⚠️ NodeLoc 未发现签到入口\n账号：${accountStr}\n时间：${timeStr}`
      );
      process.exit(0);
    }

    // === 记录点击前状态（只用于对比，不用于判断）===
    const before = await btn.evaluate(b => ({
      checked: b.classList.contains("checked-in"),
      disabled: b.disabled,
      text:
        (b.getAttribute("title") || "") +
        (b.getAttribute("aria-label") || "")
    }));

    log("执行签到按钮点击（无条件）");

    // 用页面 JS 触发，最接近人工
    await page.evaluate(() => {
      const b = document.querySelector("button.checkin-button");
      if (b) b.click();
    });

    // 等待页面反应
    await page.waitForTimeout(800);

    // === 检查点击后的真实状态 ===
    const after = await page.evaluate(() => {
      const b = document.querySelector("button.checkin-button");
      if (!b) return null;
      const text =
        (b.getAttribute("title") || "") +
        (b.getAttribute("aria-label") || "");
      return {
        checked: b.classList.contains("checked-in"),
        disabled: b.disabled,
        text
      };
    });

    if (!after) {
      throw new Error("签到按钮丢失");
    }

    // === 严格按网站逻辑给结果 ===
    if (
      !before.checked &&
      !before.disabled &&
      !before.text.includes("已签到") &&
      (after.checked || after.disabled || after.text.includes("已签到"))
    ) {
      log("网站返回：签到成功");
      await sendTG(
        `✅ NodeLoc 签到成功\n账号：${accountStr}\n时间：${timeStr}`
      );
      process.exit(0);
    }

    if (
      before.checked ||
      before.disabled ||
      before.text.includes("已签到") ||
      after.text.includes("已签到")
    ) {
      log("网站返回：今日已签到");
      await sendTG(
        `🟢 NodeLoc 今日已签到\n账号：${accountStr}\n时间：${timeStr}`
      );
      process.exit(0);
    }

    log("点击后无有效反馈");
    await sendTG(
      `❌ NodeLoc 签到未触发\n账号：${accountStr}\n时间：${timeStr}`
    );
    process.exit(1);

  } catch (err) {
    console.error("[NodeLoc] 执行异常：", err.message);
    await sendTG(
      `❌ NodeLoc 执行异常\n账号：${LOGIN_EMAIL ? maskEmail(LOGIN_EMAIL) : "（邮箱未配置）"}\n错误：${err.message}`
    );
    process.exit(1);
  } finally {
    log("关闭浏览器，任务结束");
    await browser.close();
  }
})();
