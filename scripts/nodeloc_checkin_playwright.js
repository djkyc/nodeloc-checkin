const { chromium } = require("playwright");
const axios = require("axios");

const BASE = "https://www.nodeloc.com";

/* ========== 环境变量 ========== */
const NODELOC_COOKIE = (process.env.NODELOC_COOKIE || "").trim();
const LOGIN_EMAIL = (process.env.NODELOC_LOGIN_EMAIL || "").trim();
const LOGIN_PASSWORD = (process.env.NODELOC_LOGIN_PASSWORD || "").trim();
const COOKIE_TG_MODE = (process.env.NODELOC_COOKIE_TG_MODE || "safe").toLowerCase();

/* ========== 日志工具 ========== */
function log(msg) {
  console.log(`[NodeLoc] ${msg}`);
}

/* ========== TG 推送 ========== */
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

/* ========== 工具函数 ========== */
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

/* ========== 自动登录刷新 Cookie ========== */
async function reloginAndRefresh(page) {
  if (!LOGIN_EMAIL || !LOGIN_PASSWORD) {
    log("未配置自动登录账号密码，无法刷新 Cookie");
    return null;
  }

  log("跳转到登录页进行自动登录");
  await page.goto(`${BASE}/login`, { waitUntil: "domcontentloaded", timeout: 60000 });

  await page.fill('input[name="login"]', LOGIN_EMAIL);
  await page.fill('input[name="password"]', LOGIN_PASSWORD);
  await page.click('button[type="submit"]');

  log("已提交登录表单，等待登录完成");
  await page.waitForSelector("img.avatar", { timeout: 30000 });

  const cookies = await page.context().cookies(BASE);
  log("自动登录成功，已获取新 Cookie");

  return cookies.map(c => `${c.name}=${c.value}`).join("; ");
}

/* ========== 主流程 ========== */
(async () => {
  log("启动 NodeLoc 签到任务");

  if (!NODELOC_COOKIE) {
    log("未设置 NODELOC_COOKIE，直接退出");
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
    log("打开 NodeLoc 首页");
    await page.goto(BASE, { waitUntil: "domcontentloaded", timeout: 60000 });
    await page.waitForTimeout(3000);

    let checkinIcon = await page.$("li.header-dropdown-toggle.checkin-icon");
    let cookieUsed = NODELOC_COOKIE;

    /* ===== Cookie 失效处理 ===== */
    if (!checkinIcon) {
      log("未检测到签到入口，判定 Cookie 已失效");

      const newCookie = await reloginAndRefresh(page);
      if (!newCookie) {
        log("Cookie 刷新失败，任务终止");
        await sendTG("❌ NodeLoc Cookie 已失效，且未配置自动登录");
        process.exit(1);
      }

      await context.clearCookies();
      await context.addCookies(parseCookies(newCookie));
      cookieUsed = newCookie;

      log("已注入新 Cookie，重新加载首页");
      await page.goto(BASE, { waitUntil: "domcontentloaded" });
      await page.waitForTimeout(3000);

      checkinIcon = await page.$("li.header-dropdown-toggle.checkin-icon");
      if (!checkinIcon) {
        log("自动登录后仍未检测到签到入口，可能触发验证码/2FA");
        await sendTG("❌ NodeLoc 自动登录失败（可能需要验证码/2FA）");
        process.exit(1);
      }

      const timeStr = formatBeijingTime();
      const accountStr = LOGIN_EMAIL ? maskEmail(LOGIN_EMAIL) : "（邮箱未配置）";

      let msg =
        "♻️ NodeLoc Cookie 已自动刷新\n" +
        `账号：${accountStr}\n` +
        `时间：${timeStr}\n\n`;

      if (COOKIE_TG_MODE === "full") {
        msg += "NEW NODELOC_COOKIE：\n" + cookieUsed;
        log("TG 已配置 full 模式，发送完整 Cookie");
      } else {
        msg +=
          "Cookie 摘要：\n" +
          cookieSummary(cookieUsed) +
          "\n\n请到 Actions 日志复制完整 Cookie 更新 Secrets";
        log("TG 使用 safe 模式，仅发送 Cookie 摘要");
      }

      await sendTG(msg);
      console.log("\n[NodeLoc] NEW NODELOC_COOKIE:\n" + cookieUsed + "\n");
    } else {
      log("Cookie 有效，检测到签到入口");
    }

    const timeStr = formatBeijingTime();
    const displayAccount = LOGIN_EMAIL ? maskEmail(LOGIN_EMAIL) : "（邮箱未配置）";

    /* ===== 已签到判断 ===== */
    const alreadySigned = await page.$(".d-icon-calendar-check");
    if (alreadySigned) {
      log("检测到今日已签到");
      await sendTG(
        `🟢 NodeLoc 今日已签到\n账号：${displayAccount}\n时间：${timeStr}`
      );
      process.exit(0);
    }

    /* ===== 执行签到 ===== */
    const checkinBtn = await page.$("button.checkin-button");
    if (!checkinBtn) {
      log("未找到签到按钮，可能页面结构变更");
      await sendTG(
        `⚠️ NodeLoc 未发现签到入口\n账号：${displayAccount}\n时间：${timeStr}`
      );
      process.exit(0);
    }

    log("检测到未签到状态，执行签到点击");
    await checkinBtn.click();

    // 🔴 关键修复：等待真实状态变化
    log("等待签到状态更新确认");
    try {
      await page.waitForSelector(".d-icon-calendar-check", { timeout: 10000 });
    } catch {
      log("点击后未检测到已签到状态，判定签到失败");
      await sendTG(
        `❌ NodeLoc 签到失败（页面状态未变化）\n账号：${displayAccount}\n时间：${timeStr}`
      );
      process.exit(1);
    }

    log("检测到签到状态已更新，签到成功");
    await sendTG(
      `✅ NodeLoc 签到成功\n账号：${displayAccount}\n时间：${timeStr}`
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
