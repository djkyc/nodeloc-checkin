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

const BASE = "https://www.nodeloc.com";
const UA =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36";

const USERNAME = process.env.NODELOC_USERNAME;
const PASSWORD = process.env.NODELOC_PASSWORD;
const TIMEZONE = process.env.NODELOC_TIMEZONE || "America/Los_Angeles";
const NODELOC_COOKIE = process.env.NODELOC_COOKIE;

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

function toFormUrlEncoded(obj) {
  return Object.entries(obj)
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v ?? "")}`)
    .join("&");
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function safeText(data) {
  if (data == null) return "";
  if (typeof data === "string") return data;
  try {
    return JSON.stringify(data);
  } catch {
    return String(data);
  }
}

// GET /session/csrf
async function fetchCsrf(client, referer = `${BASE}/login`) {
  const res = await client.get(`${BASE}/session/csrf`, {
    headers: {
      Accept: "application/json, text/javascript, */*; q=0.01",
      Referer: referer,
      "X-Requested-With": "XMLHttpRequest",
      "Discourse-Present": "true",
    },
  });

  if (res?.data?.csrf) return res.data.csrf;

  const text = safeText(res.data);
  const m = text.match(/"csrf"\s*:\s*"([^"]+)"/);
  return m ? m[1] : null;
}

// POST /session 登录
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
    throw new Error(`登录请求失败，HTTP ${res.status}，响应：${safeText(res.data).slice(0, 200)}`);
  }

  const body = safeText(res.data);
  if (
    body.includes("不正确") ||
    body.toLowerCase().includes("incorrect") ||
    body.toLowerCase().includes("invalid")
  ) {
    throw new Error("登录失败：用户名/邮箱或密码不正确");
  }

  if (
    body.toLowerCase().includes("second_factor") ||
    body.includes("二次") ||
    body.includes("验证码") ||
    body.toLowerCase().includes("otp") ||
    body.toLowerCase().includes("2fa")
  ) {
    throw new Error("登录触发二次验证/验证码：建议用 NODELOC_COOKIE");
  }
}

// GET / 抓 nonce
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

// 从服务器响应头 Date 取时间戳（更贴近服务端，避免时差）
async function getServerTimestampMs(client) {
  const res = await client.get(`${BASE}/`, {
    headers: {
      Accept: "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
      Referer: `${BASE}/`,
    },
  });
  const dateHeader = res?.headers?.date;
  const ms = dateHeader ? new Date(dateHeader).getTime() : NaN;
  return Number.isFinite(ms) ? ms : Date.now();
}

// POST /checkin
async function checkin(client, csrf, nonce, timestampMs) {
  const data = toFormUrlEncoded({ nonce, timestamp: String(timestampMs) });

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
    throw new Error(`签到请求失败，HTTP ${res.status}，响应：${safeText(res.data).slice(0, 300)}`);
  }

  // 有时会 200 但 success:false（无效请求/已签到/IP限制等），也当作失败抛出方便看日志
  if (res?.data && typeof res.data === "object" && res.data.success === false) {
    throw new Error(`签到返回失败：${safeText(res.data)}`);
  }

  return res.data;
}

async function main() {
  if (!NODELOC_COOKIE && (!USERNAME || !PASSWORD)) {
    console.log("⚠️ 请设置 NODELOC_COOKIE（推荐），或设置 NODELOC_USERNAME / NODELOC_PASSWORD");
    process.exit(1);
  }

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

  // 写入 Cookie（优先）
  if (NODELOC_COOKIE) {
    NODELOC_COOKIE.split(";")
      .map((s) => s.trim())
      .filter(Boolean)
      .forEach((c) => jar.setCookieSync(c, BASE));
  }

  await sleep(Math.random() * 1200 + 600);

  try {
    // 1) CSRF（初始）
    const csrf1 = await fetchCsrf(client, `${BASE}/login`);
    if (!csrf1) throw new Error("获取 CSRF 失败");

    // 2) 登录（仅当没 cookie）
    if (!NODELOC_COOKIE) {
      await login(client, csrf1, USERNAME, PASSWORD, TIMEZONE);
    }

    // 3) nonce
    const nonce = await fetchNonce(client);
    if (!nonce) throw new Error("获取 nonce 失败（Cookie 可能失效/未登录/页面变化）");

    // 4) timestamp（用服务器时间更稳）
    const ts = await getServerTimestampMs(client);

    // 5) 关键：签到前再取一次 CSRF（对齐 HAR 流程）
    const csrf2 = await fetchCsrf(client, `${BASE}/`);
    if (!csrf2) throw new Error("获取签到用 CSRF 失败");

    // 6) checkin
    const result = await checkin(client, csrf2, nonce, ts);

    const msg = "✅ NodeLoc 签到结果：\n```json\n" + JSON.stringify(result, null, 2) + "\n```";
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
