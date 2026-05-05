const BACKEND_ORIGIN = "http://127.0.0.1:8080";
const BACKEND_BASE_URL = `${BACKEND_ORIGIN}/api/v1/news`;
const AUTH_BASE_URL = `${BACKEND_ORIGIN}/api/v1/auth`;

async function safeJson(response) {
  if (!response.ok) {
    throw new Error(`Backend request failed with ${response.status}`);
  }

  return response.json();
}

export async function requestBackendAnalysis(article, clientUserId) {
  try {
    const response = await fetch(`${BACKEND_BASE_URL}/analyze`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        url: article.url,
        title: article.title,
        content: article.body,
        clientUserId
      })
    });

    return await safeJson(response);
  } catch {
    return {
      article,
      keywords: [],
      summary: "기사 분석 중 문제가 발생했습니다.",
      recommendations: [
        {
          title: "원문 기사",
          url: article.url
        }
      ],
      adLikelihood: {
        label: "검토 필요",
        score: 0.99
      }
    };
  }
}

export async function recordNewsInteraction({ newsId, url, clientUserId, interactionType }) {
  if (!clientUserId || (!newsId && !url)) {
    return;
  }

  await fetch(`${BACKEND_BASE_URL}/interactions`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      newsId,
      url,
      clientUserId,
      interactionType
    })
  });
}

export async function signUp({ loginId, password }) {
  return requestAuth("/signup", { loginId, password });
}

export async function login({ loginId, password }) {
  return requestAuth("/login", { loginId, password });
}

async function requestAuth(path, body) {
  const response = await fetch(`${AUTH_BASE_URL}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify(body)
  });

  if (!response.ok) {
    let message = `Auth request failed with ${response.status}`;
    try {
      const payload = await response.json();
      message = payload.message || message;
    } catch {
      // Use the default message.
    }
    throw new Error(message);
  }

  return response.json();
}
