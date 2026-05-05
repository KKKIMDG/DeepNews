const BACKEND_BASE_URL = "http://127.0.0.1:8080/api/v1/news";

async function safeJson(response) {
  if (!response.ok) {
    throw new Error(`Backend request failed with ${response.status}`);
  }

  return response.json();
}

export async function requestBackendAnalysis(article) {
  try {
    const response = await fetch(`${BACKEND_BASE_URL}/analyze`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        url: article.url
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
