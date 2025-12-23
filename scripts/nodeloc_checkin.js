/**
 * NodeLoc 账号密码登录 + 签到（Discourse）
 *
 * 依赖：
 *   npm i axios tough-cookie axios-cookiejar-support
 *
 * 环境变量：
 *   NODELOC_USERNAME=你的用户名或邮箱
 *   NODELOC_PASSWORD=你的密码
 *   NODELOC_TIMEZONE=America/Los_Angeles   (可选；默认这个)
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
    console.log("❌ TG 推送失败：", err.message);
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

// ===== 主逻辑 =====
async function main() {
  if (!USERNAME || !PASSWORD) {
    console.log("⚠️ 请设置 NODELOC_USERNAME 和 NODELOC_PASSWORD");
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

  // 随机延迟，避免集中请求
  await sleep(Math.random() * 2000 + 1000);

  try {
    // 1) 获取 CSRF
    const csrf = await fetchCsrf(client);
    if (!csrf) throw new Error("获取 CSRF 失败");

    // 2) 登录（账号密码）
    await login(client, csrf, USERNAME, PASSWORD, TIMEZONE);

    // 3) 获取 nonce（用于签到）
    const nonce = await fetchNonce(client);
    if (!nonce) throw new Error("获取 nonce 失败");

    // 4) 签到
    const result = await checkin(client, csrf, nonce);

    const msg = `✅ NodeLoc 签到结果：\n\`\`\`\n${JSON.stringify(result, null, 2)}\n\`\`\``;
    console.log(msg);
    await sendTG(msg);
  } catch (err) {
    const msg = `❌ NodeLoc 签到失败：${err.message}`;
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
      // "X-CSRF-Token": "undefined", // HAR 里是 undefined，这里不发也行
    },
  });

  // 正常是 { csrf: "..." }
  const csrf = res?.data?.csrf;
  if (!csrf) {
    // 兜底：如果不是 JSON，就从文本里正则提取
    const text = typeof res.data === "string" ? res.data : JSON.stringify(res.data);
    const m = text.match(/"csrf"\s*:\s*"([^"]+)"/);
    return m ? m[1] : null;
  }
  return csrf;
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
    throw new Error(`登录请求失败，HTTP ${res.status}`);
  }

  // 登录失败时，Discourse 往往会返回包含错误信息的内容
  const bodyText = typeof res.data === "string" ? res.data : JSON.stringify(res.data);
  if (bodyText.includes("用户名") && bodyText.includes("密码") && bodyText.includes("不正确")) {
    throw new Error("用户名/邮箱或密码不正确");
  }
  if (bodyText.toLowerCase().includes("second_factor") || bodyText.includes("验证码") || bodyText.includes("二次")) {
    throw new Error("账号触发了二次验证/验证码，脚本不支持绕过（需要你在网页端完成验证后再用 Cookie 方案）");
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

  // 返回一般是 JSON（也可能是文本）
  return res.data;
}

main();
