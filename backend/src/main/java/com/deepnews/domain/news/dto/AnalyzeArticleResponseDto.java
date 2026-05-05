package com.deepnews.domain.news.dto;

import com.deepnews.domain.analysis.entity.NewsAnalysis;
import com.deepnews.domain.news.entity.News;
import lombok.Builder;
import lombok.Getter;

import java.math.BigDecimal;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.stream.Collectors;

@Getter
@Builder
public class AnalyzeArticleResponseDto {

    private Long newsId;
    private boolean cached;
    private ArticlePayload article;
    private List<KeywordPayload> keywords;
    private String summary;
    private List<Map<String, String>> recommendations;
    private AdLikelihood adLikelihood;

    public static AnalyzeArticleResponseDto from(News news, NewsAnalysis analysis, boolean cached) {
        return AnalyzeArticleResponseDto.builder()
                .newsId(news.getId())
                .cached(cached)
                .article(new ArticlePayload(news.getTitle(), news.getUrl()))
                .keywords(extractKeywords(news))
                .summary(analysis.getSummary())
                .recommendations(List.of(
                        Map.of("title", news.getTitle(), "url", news.getUrl())
                ))
                .adLikelihood(new AdLikelihood(
                        labelFor(analysis.getAdProbability()),
                        analysis.getAdProbability().doubleValue()
                ))
                .build();
    }

    @SuppressWarnings("unchecked")
    private static List<KeywordPayload> extractKeywords(News news) {
        Object keywordsValue = news.getArticleData() != null ? news.getArticleData().getExtraData().get("keywords") : null;
        if (keywordsValue instanceof List<?> keywordList) {
            return keywordList.stream()
                    .filter(Map.class::isInstance)
                    .map(Map.class::cast)
                    .map(item -> new KeywordPayload(
                            Objects.toString(item.get("term"), ""),
                            parseCount(item.get("count"))
                    ))
                    .filter(item -> !item.getTerm().isBlank())
                    .sorted(Comparator.comparingInt(KeywordPayload::getCount).reversed())
                    .limit(8)
                    .toList();
        }

        Object tokenCountsValue = news.getArticleData() != null ? news.getArticleData().getExtraData().get("token_counts") : null;
        if (tokenCountsValue instanceof Map<?, ?> tokenCounts) {
            return tokenCounts.entrySet().stream()
                    .map(entry -> new KeywordPayload(
                            Objects.toString(entry.getKey(), ""),
                            parseCount(entry.getValue())
                    ))
                    .filter(item -> !item.getTerm().isBlank())
                    .sorted(Comparator.comparingInt(KeywordPayload::getCount).reversed())
                    .limit(8)
                    .collect(Collectors.toList());
        }

        return List.of();
    }

    private static int parseCount(Object value) {
        if (value instanceof Number number) {
            return number.intValue();
        }
        try {
            return Integer.parseInt(Objects.toString(value, "0"));
        } catch (NumberFormatException exception) {
            return 0;
        }
    }

    private static String labelFor(BigDecimal probability) {
        if (probability == null) {
            return "검토 필요";
        }
        double value = probability.doubleValue();
        if (value >= 0.8) {
            return "광고성 높음";
        }
        if (value >= 0.4) {
            return "검토 필요";
        }
        return "광고성 낮음";
    }

    @Getter
    public static class AdLikelihood {
        private final String label;
        private final double score;

        public AdLikelihood(String label, double score) {
            this.label = label;
            this.score = score;
        }
    }

    @Getter
    public static class ArticlePayload {
        private final String title;
        private final String url;

        public ArticlePayload(String title, String url) {
            this.title = title;
            this.url = url;
        }
    }

    @Getter
    public static class KeywordPayload {
        private final String term;
        private final int count;

        public KeywordPayload(String term, int count) {
            this.term = term;
            this.count = count;
        }
    }
}
