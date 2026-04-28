const STOPWORDS = new Set([
  "그리고",
  "하지만",
  "그러나",
  "또한",
  "입니다",
  "있습니다",
  "있는",
  "하는",
  "위해",
  "대한",
  "에서",
  "으로",
  "까지",
  "이번",
  "관련",
  "기자",
  "뉴스",
  "naver",
  "article"
]);

export function extractKeywords(text, limit = 8) {
  const normalized = (text || "")
    .replace(/<[^>]+>/g, " ")
    .replace(/[^\p{L}\p{N}\s]/gu, " ")
    .toLowerCase();

  const counts = new Map();

  for (const token of normalized.split(/\s+/)) {
    if (token.length < 2 || STOPWORDS.has(token)) {
      continue;
    }

    counts.set(token, (counts.get(token) || 0) + 1);
  }

  return [...counts.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, limit)
    .map(([term, count]) => ({ term, count }));
}

export function buildHighlightPayload(keywords) {
  return keywords.map((keyword) => keyword.term);
}
