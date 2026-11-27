export function buildHighlightPayload(keywords) {
  return keywords
    .map((keyword) => (typeof keyword === "string" ? keyword : keyword.term))
    .filter(Boolean);
}
