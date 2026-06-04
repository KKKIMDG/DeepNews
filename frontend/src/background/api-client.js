const RECOMMENDATION_BASE_URL = "http://127.0.0.1:8011/api/v1/recommendations";

async function safeJson(response) {
  if (!response.ok) {
    throw new Error(`Backend request failed with ${response.status}`);
  }

  return response.json();
}

export async function requestBackendAnalysis(article) {
  try {
    const response = await fetch(`${RECOMMENDATION_BASE_URL}/mind-svd?limit=10`);
    const recommendationResult = await safeJson(response);

    return {
      article,
      keywords: [
        { term: "MIND", count: 3 },
        { term: "SVD", count: 2 },
        { term: "추천", count: 2 },
        { term: "네이버", count: 1 }
      ],
      summary:
        "MIND 데이터셋 기반 SVD 협업 필터링 결과를 네이버 뉴스 메타데이터로 매핑해 추천합니다.",
      recommendations: recommendationResult.items || [],
      adLikelihood: {
        label: "추천 데모",
        score: 0
      }
    };
  } catch {
    return {
      article,
      keywords: [],
      summary: "추천 API 연결 중 문제가 발생했습니다. 서버가 켜져 있는지 확인해 주세요.",
      recommendations: [
        {
          title: "현재 기사",
          url: article.url
        }
      ],
      adLikelihood: {
        label: "연결 필요",
        score: 0
      }
    };
  }
}
