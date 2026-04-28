const BACKEND_BASE_URL = "https://api.example.com";

async function safeJson(response) {
  if (!response.ok) {
    throw new Error(`Backend request failed with ${response.status}`);
  }

  return response.json();
}

export async function requestBackendAnalysis(article, keywords) {
  try {
    const response = await fetch(`${BACKEND_BASE_URL}/analyze`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        article,
        keywords
      })
    });

    return await safeJson(response);
  } catch {
    return {
      summary: `${article.title} 기사의 핵심 키워드는 ${keywords
        .slice(0, 3)
        .map((item) => item.term)
        .join(", ")}입니다.`,
      recommendations: [
        {
          title: "관련 기사 1",
          url: article.url
        },
        {
          title: "관련 기사 2",
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
