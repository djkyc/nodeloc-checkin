/**
 * NodeLoc Cookie(优先) 或 账号密码 登录 + 签到（Discourse）
 *
 * 依赖：
 *   npm i axios tough-cookie axios-cookiejar-support
 *
 * 环境变量（二选一即可）：
 *   方式1（推荐）：NODELOC_COOKIE=浏览器 Network 里 Request Headers 的 Cookie: 后面那一整串
 *   方式2：NODELOC_USERNAME=账号/邮箱  NODELOC_PASSWORD=密码
 *
 * 可选：
 *   NODELOC_TIMEZONE=America/Los_Angeles
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
const NODELOC_COOKIE = process.env.NODELOC_COOKIE;

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

// ===== 1) GET /session/csrf =====
async function fetchCsrf(client) {
  const res = await client.get(`${BASE}/session/csrf`, {
    headers: {
      Accept: "application/json, text/javascript, */*; q=0.01",
      Referer: `${BASE}/login`,
      "X-Requested-With": "XMLHttpRequest",
      "Discourse-Present": "true",
    },
  });

  const csrf = res?.data?.csrf;
  if (csrf) return csrf;

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

  if (
    body.includes("不正确") ||
    body.toLowerCase().includes("incorrect") ||
    body.toLowerCase().includes("invalid")
  ) {
    throw new Error("登录失败：用户名/邮箱或密码不正确（或站点返回 invalid/incorrect）");
  }

  // 二次验证/验证码：不处理（提示用户改用 cookie）
  if (
    body.toLowerCase().includes("second_factor") ||
    body.includes("二次") ||
    body.includes("验证码") ||
    body.toLowerCase().includes("otp") ||
    body.toLowerCase().includes("2fa")
  ) {
    throw new Error("登录触发二次验证/验证码：请改用 NODELOC_COOKIE（一次人工登录后长期可用）");
  }

  return true;
}

// ===== 3) GET / 抓 nonce="..." =====
async function fetchNonce(client) {
  const res = await client.get(`${BASE}/`, {
    headers: {
      Accept: "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
      Referer: `${BASE}/`,
    },
  });

  const html = typeof res.data === "string" ? res.data : "";
  const m = html.match(/nonce="([^"]+)"/);
  return m ? m[1] : null;
}

// ===== 4) POST /checkin =====
async function checkin(client, csrf, nonce) {
  const timestamp = Date.now();
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

  if (res.status < 200 || res.status >= 300) {
    const body = safeText(res.data);
    throw new Error(`签到请求失败，HTTP ${res.status}，响应：${body.slice(0, 300)}`);
  }

  return res.data;
}

// ===== 主逻辑 =====
async function main() {
  // 如果没有 cookie，又没有账号密码，就直接报错
  if (!NODELOC_COOKIE && (!USERNAME || !PASSWORD)) {
    console.log("⚠️ 请设置 NODELOC_COOKIE（推荐），或设置 NODELOC_USERNAME / NODELOC_PASSWORD");
    process.exit(1);
  }

  // 让 axios 自动维护 Cookie（登录态）
  const jar = new CookieJar();
  const client = wrapper(
    axios.create({
      jar,
      withCredentials: true,
      timeout: 30000,
      validateStatus: (s) => s >= 200 && s < 500,
      headers: { "User-Agent": UA },
    })
  );

  // 若提供了 NODELOC_COOKIE：写入 cookie jar（跳过账号密码登录）
  if (NODELOC_COOKIE) {
    NODELOC_COOKIE.split(";")
      .map((s) => s.trim())
      .filter(Boolean)
      .forEach((c) => jar.setCookieSync(c, BASE));
  }

  // 随机延迟
  await sleep(Math.random() * 1500 + 800);

  try {
    const csrf = await fetchCsrf(client);
    if (!csrf) throw new Error("获取 CSRF 失败");

    // 没 cookie 才登录
    if (!NODELOC_COOKIE) {
      await login(client, csrf, USERNAME, PASSWORD, TIMEZONE);
    }

    const nonce = await fetchNonce(client);
    if (!nonce) throw new Error("获取 nonce 失败（Cookie 可能失效/未登录/页面结构变化）");

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

main();
