/**
 * NodeLoc 账号密码登录 + 签到（Discourse）
 *
 * 依赖：
 *   npm i axios tough-cookie axios-cookiejar-support
 *
 * 环境变量：
 *   NODELOC_USERNAME=你的用户名或邮箱
 *   NODELOC_PASSWORD=你的密码
 *   NODELOC_TIMEZONE=America/Los_Angeles   (可选；默认 America/Los_Angeles)
 *
 * 可选 Telegram 推送：
 *   TG_BOT_TOKEN=xxxxx
 *   TG_USER_ID=123456789
 */

const axios = require("axios");
const { CookieJar } = require("tough-cookie");
const { wrapper } = require("axios-cookiejar-support");

// ===== 配置 =====
const BASE = "https://www.nodeloc.com";
const UA =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36";

const USERNAME = process.env.NODELOC_USERNAME;
const PASSWORD = process.env.NODELOC_PASSWORD;
const TIMEZONE = process.env.NODELOC_TIMEZONE || "America/Los_Angeles";

// ===== TG 推送（可选）=====
async function sendTG(message) {
  const TG_TOKEN = process.env.TG_BOT_TOKEN;
  const TG_USER_ID = process.env.TG_USER_ID;
  if (!TG_TOKEN || !TG_USER_ID) return;

  try {
    await axios.post(`https://api.telegram.org/bot${TG_TOKEN}/sendMessage`, {
      chat_id: TG_USER_ID,
      text: message,
      parse_mode: "Markdown",
    });
    console.log("✅ TG 推送成功");
  } catch (err) {
    console.log("❌ TG 推送失败：", err?.message || err);
  }
}

// ===== 工具：urlencoded =====
function toFormUrlEncoded(obj) {
  return Object.entries(obj)
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v ?? "")}`)
    .join("&");
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

function safeText(data) {
  if (data == null) return "";
  if (typeof data === "string") return data;
  try {
    return JSON.stringify(data);
  } catch {
    return String(data);
  }
}

// ===== 主逻辑 =====
async function main() {
  if (!USERNAME || !PASSWORD) {
    console.log("⚠️ 缺少环境变量：NODELOC_USERNAME / NODELOC_PASSWORD");
    process.exit(1);
  }

  // 让 axios 自动维护 Cookie（登录态）
  const jar = new CookieJar();
  const client = wrapper(
    axios.create({
      jar,
      withCredentials: true,
      timeout: 30000,
      validateStatus: (s) => s >= 200 && s < 500, // 让我们能读到错误响应内容
      headers: {
        "User-Agent": UA,
      },
    })
  );

  // 随机延迟，降低触发风控概率
  await sleep(Math.random() * 1500 + 800);

  try {
    // 1) 获取 CSRF
    const csrf = await fetchCsrf(client);
    if (!csrf) throw new Error("获取 CSRF 失败");

    // 2) 登录（账号密码）
    await login(client, csrf, USERNAME, PASSWORD, TIMEZONE);

    // 3) 获取 nonce（用于签到）
    const nonce = await fetchNonce(client);
    if (!nonce) throw new Error("获取 nonce 失败（可能未登录成功或页面结构变化）");

    // 4) 签到
    const result = await checkin(client, csrf, nonce);

    const msg =
      "✅ NodeLoc 签到结果：\n" +
      "```json\n" +
      JSON.stringify(result, null, 2) +
      "\n```";
    console.log(msg);
    await sendTG(msg);
  } catch (err) {
    const msg = `❌ NodeLoc 签到失败：${err?.message || err}`;
    console.log(msg);
    await sendTG(msg);
    process.exit(1);
  }
}

// ===== 1) GET /session/csrf =====
async function fetchCsrf(client) {
  const res = await client.get(`${BASE}/session/csrf`, {
    headers: {
      Accept: "application/json, text/javascript, */*; q=0.01",
      Referer: `${BASE}/login`,
      "X-Requested-With": "XMLHttpRequest",
      "Discourse-Present": "true",
      // 有些抓包里会看到 "X-CSRF-Token: undefined"，这里不发也能拿到 csrf
    },
  });

  // 正常是 { csrf: "..." }
  const csrf = res?.data?.csrf;
  if (csrf) return csrf;

  // 兜底：如果不是 JSON，就从文本里提取
  const text = safeText(res.data);
  const m = text.match(/"csrf"\s*:\s*"([^"]+)"/);
  return m ? m[1] : null;
}

// ===== 2) POST /session 登录 =====
async function login(client, csrf, username, password, timezone) {
  const data = toFormUrlEncoded({
    login: username,
    password,
    second_factor_method: 1,
    timezone,
  });

  const res = await client.post(`${BASE}/session`, data, {
    headers: {
      Accept: "*/*",
      Referer: `${BASE}/login`,
      Origin: BASE,
      "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
      "X-Requested-With": "XMLHttpRequest",
      "Discourse-Present": "true",
      "X-CSRF-Token": csrf,
    },
  });

  if (res.status !== 200) {
    const body = safeText(res.data);
    throw new Error(`登录请求失败，HTTP ${res.status}，响应：${body.slice(0, 200)}`);
  }

  const body = safeText(res.data);

  // 常见失败提示兜底（不同语言/站点定制可能不一样）
  if (
    body.includes("不正确") ||
    body.toLowerCase().includes("incorrect") ||
    body.toLowerCase().includes("invalid")
  ) {
    throw new Error("登录失败：用户名/邮箱或密码不正确（或站点返回 invalid/incorrect）");
  }

  // 二次验证/验证码：这里不做绕过，只提示
  if (
    body.toLowerCase().includes("second_factor") ||
    body.includes("二次") ||
    body.includes("验证码") ||
    body.toLowerCase().includes("otp") ||
    body.toLowerCase().includes("2fa")
  ) {
    throw new Error("登录触发二次验证/验证码：该脚本不支持绕过（只能人工验证或改用 Cookie 方案）");
  }

  return true;
}

// ===== 3) GET / 抓 nonce="..." =====
async function fetchNonce(client) {
  const res = await client.get(`${BASE}/`, {
    headers: {
      Accept: "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
      Referer: `${BASE}/login`,
    },
  });

  const html = typeof res.data === "string" ? res.data : "";
  const m = html.match(/nonce="([^"]+)"/);
  return m ? m[1] : null;
}

// ===== 4) POST /checkin =====
async function checkin(client, csrf, nonce) {
  const timestamp = Date.now(); // 13位毫秒时间戳
  const data = toFormUrlEncoded({ nonce, timestamp });

  const res = await client.post(`${BASE}/checkin`, data, {
    headers: {
      Accept: "*/*",
      Referer: `${BASE}/`,
      Origin: BASE,
      "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
      "X-Requested-With": "XMLHttpRequest",
      "Discourse-Present": "true",
      "Discourse-Logged-In": "true",
      "X-CSRF-Token": csrf,
      "X-Discourse-Checkin": "true",
      "X-Checkin-Nonce": nonce,
    },
  });

  // 如果返回不是 2xx，也把内容抛出来方便排查
  if (res.status < 200 || res.status >= 300) {
    const body = safeText(res.data);
    throw new Error(`签到请求失败，HTTP ${res.status}，响应：${body.slice(0, 300)}`);
  }

  return res.data;
}

main();
