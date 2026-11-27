import { API_BASE_STORAGE_KEY, DEFAULT_API_BASE } from "../shared/constants.js";

const DEFAULT_TIMEOUT_MS = 30000;
const ANALYSIS_TIMEOUT_MS = 180000;

export class AuthExpiredError extends Error {}

const AUTH_EXPIRED_MESSAGE = "로그인이 만료되었습니다. 다시 로그인해 주세요.";

async function apiRequest(path, { method = "GET", body, token = "", timeout = DEFAULT_TIMEOUT_MS } = {}) {
  const headers = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (token) headers.Authorization = `Bearer ${token}`;

  const base = (await chrome.storage.local.get(API_BASE_STORAGE_KEY))[API_BASE_STORAGE_KEY] || DEFAULT_API_BASE;
  let response;
  try {
    response = await fetch(`${base}/api/v1${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: AbortSignal.timeout(timeout)
    });
  } catch (error) {
    if (error?.name === "TimeoutError") {
      throw new Error("분석 서버 응답이 너무 늦습니다. 잠시 후 다시 시도해 주세요.");
    }
    throw new Error(`분석 서버(${base})에 연결할 수 없습니다. 패널의 서버 주소와 서버 상태를 확인해 주세요.`);
  }

  if (response.status === 204) {
    return null;
  }

  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    if (response.status === 401 && token) {
      throw new AuthExpiredError(AUTH_EXPIRED_MESSAGE);
    }
    throw new Error(errorMessage(data, response.status));
  }
  return data;
}

function errorMessage(data, status) {
  if (typeof data?.detail === "string" && data.detail) {
    return data.detail;
  }

  const [first] = Array.isArray(data?.detail) ? data.detail : [];
  if (first?.loc?.some((part) => /password/i.test(String(part))) && first.type === "string_too_short") {
    return "비밀번호는 8자 이상이어야 합니다.";
  }
  if (typeof first?.msg === "string") {
    return first.msg.replace(/^Value error, /, "");
  }
  if (status === 429) {
    return "요청이 너무 많습니다. 잠시 후 다시 시도해 주세요.";
  }
  if (status === 503) {
    return "분석 서버가 준비 중이거나 바쁩니다. 잠시 후 다시 시도해 주세요.";
  }
  return `요청 실패 (${status})`;
}

function normalizeAuthResponse(response) {
  const token = response?.token || response?.accessToken || response?.access_token || "";
  const user = response?.user || {
    email: response?.email || ""
  };

  if (!token) {
    throw new Error("인증 응답에 로그인 토큰이 없습니다.");
  }

  return {
    token,
    user
  };
}

export async function requestBackendAnalysis(article, token = "") {
  return apiRequest("/news/analyze", { method: "POST", body: article, token, timeout: ANALYSIS_TIMEOUT_MS });
}

export async function login(email, password) {
  return normalizeAuthResponse(await apiRequest("/auth/login", { method: "POST", body: { email, password } }));
}

export async function signup(email, password, inviteCode = "", { topics = [], keywords = [] } = {}) {
  return normalizeAuthResponse(
    await apiRequest("/auth/signup", { method: "POST", body: { email, password, inviteCode, topics, keywords } })
  );
}

export async function logout(token) {
  return apiRequest("/auth/logout", { method: "POST", token });
}

export async function deleteAccount(token, password) {
  return apiRequest("/auth/me", { method: "DELETE", token, body: { password } });
}

export async function changePassword(token, { currentPassword, newPassword }) {
  return apiRequest("/auth/password", { method: "PUT", token, body: { currentPassword, newPassword } });
}

export async function exportMyData(token) {
  return apiRequest("/me/export", { token });
}

export async function reportNews(token, { newsId, reason = "" }) {
  return apiRequest(`/news/${encodeURIComponent(newsId)}/report`, {
    method: "POST",
    token,
    body: { reason: String(reason).slice(0, 300) }
  });
}

export async function fetchProfile(token) {
  return apiRequest("/me/profile", { token });
}

export async function setKeywordPreference(token, { term, preference }) {
  return apiRequest("/me/keywords", { method: "PUT", body: { term, preference }, token });
}

export async function deleteKeywordPreference(token, { term }) {
  return apiRequest(`/me/keywords?term=${encodeURIComponent(term)}`, { method: "DELETE", token });
}

export async function setTopics(token, { topics = [] }) {
  return apiRequest("/me/topics", { method: "PUT", body: { topics }, token });
}

export async function updateSettings(token, { adFilterThreshold }) {
  return apiRequest("/me/settings", { method: "PUT", body: { adFilterThreshold }, token });
}

export async function fetchHistory(token, { limit = 20, offset = 0 } = {}) {
  return apiRequest(`/me/history?limit=${limit}&offset=${offset}`, { token });
}

export async function deleteHistory(token, { newsId }) {
  return apiRequest(`/me/history/${encodeURIComponent(newsId)}`, { method: "DELETE", token });
}

export async function searchNaverNews(token, { query, display = 5, sort = "sim" }) {
  const params = new URLSearchParams({ query, display: String(display), sort });
  return apiRequest(`/naver/news?${params}`, { token });
}

export async function fetchCollectCandidates(token, { publisher = "", limit = 50, offset = 0 } = {}) {
  const params = new URLSearchParams({ publisher, limit: String(limit), offset: String(offset) });
  return apiRequest(`/collect/candidates?${params}`, { token });
}

export async function fetchArticleRecommendations(token, { newsId, limit = 5 }) {
  return apiRequest(`/me/recommendations?limit=${limit}&newsId=${encodeURIComponent(newsId)}`, { token });
}

export async function fetchRecommendations(token, { limit = 10 } = {}) {
  return apiRequest(`/me/recommendations?limit=${limit}`, { token });
}
