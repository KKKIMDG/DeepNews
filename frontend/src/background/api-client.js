const BACKEND_BASE_URL = "http://127.0.0.1:8000/api/v1/news";
const DEV_AUTH_EMAIL = "test@gmail.com";
const DEV_AUTH_PASSWORD = "1234";

async function safeJson(response) {
  if (!response.ok) {
    throw new Error(`Backend request failed with ${response.status}`);
  }

  return response.json();
}

export async function requestBackendAnalysis(url, token = "") {
  try {
    const headers = {
      "Content-Type": "application/json"
    };

    if (token) {
      headers.Authorization = `Bearer ${token}`;
    }

    const response = await fetch(`${BACKEND_BASE_URL}/analyze`, {
      method: "POST",
      headers,
      body: JSON.stringify({
        url
      })
    });

    return await safeJson(response);
  } catch {
    return {
      keywords: [
        {
          term: "뉴스",
          count: 5
        },
        {
          term: "분석",
          count: 4
        },
        {
          term: "이슈",
          count: 3
        }
      ],
      summary:
        "현재 백엔드 분석 API가 연결되지 않아 개발용 분석 결과를 표시하고 있습니다. 실제 API가 연결되면 기사 URL 기반 요약 결과로 대체됩니다.",
      recommendations: [
        {
          title: "개발용 추천 기사 1",
          url
        },
        {
          title: "개발용 추천 기사 2",
          url
        }
      ],
      adLikelihood: {
        label: "개발용 판단 결과",
        score: 0.09
      }
    };
  }
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
