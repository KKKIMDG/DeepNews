const BACKEND_BASE_URL = "http://127.0.0.1:8000/api/v1/news";
const DEV_AUTH_EMAIL = "test@gmail.com";
const DEV_AUTH_PASSWORD = "1234";

async function safeJson(response) {
  if (!response.ok) {
    throw new Error(`Backend request failed with ${response.status}`);
  }

  return response.json();
}

export async function requestBackendAnalysis(article, token = "") {
  const headers = { "Content-Type": "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;
  const response = await fetch(`${BACKEND_BASE_URL}/analyze`, {
    method: "POST",
    headers,
    body: JSON.stringify(article),
    signal: AbortSignal.timeout(180000)
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(typeof error.detail === "string" ? error.detail : `분석 요청 실패 (${response.status})`);
  }
  return response.json();
}

export async function login(email, password) {
  return authenticateDevAccount(email, password);
}

export async function signup(email, password) {
  return authenticateDevAccount(email, password);
}

function authenticateDevAccount(email, password) {
  if (email !== DEV_AUTH_EMAIL || password !== DEV_AUTH_PASSWORD) {
    throw new Error("테스트 계정은 test@gmail.com / 1234 입니다.");
  }

  return {
    token: "dev-auth-token",
    user: {
      email: DEV_AUTH_EMAIL,
      name: "DeepNews Test User"
    }
  };
}

function normalizeAuthResponse(response) {
  const token = response.token || response.accessToken || response.access_token || "";
  const user = response.user || {
    email: response.email || ""
  };

  if (!token) {
    throw new Error("인증 응답에 로그인 토큰이 없습니다.");
  }

  return {
    token,
    user
  };
}
