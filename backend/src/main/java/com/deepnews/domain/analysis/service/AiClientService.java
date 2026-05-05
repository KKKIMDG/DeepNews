package com.deepnews.domain.analysis.service;

import com.fasterxml.jackson.annotation.JsonProperty;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

@Service
public class AiClientService {

    private final RestClient restClient;

    public AiClientService(@Value("${ai.service.url:}") String aiServiceUrl) {
        RestClient.Builder builder = RestClient.builder();
        if (aiServiceUrl != null && !aiServiceUrl.isBlank()) {
            builder.baseUrl(aiServiceUrl);
        }
        this.restClient = builder.build();
    }

    public void requestAnalysis(Long newsId) {
        restClient.post()
                .uri("/ai/analyze")
                .contentType(MediaType.APPLICATION_JSON)
                .body(new AnalysisRequestBody("", "", "", newsId))
                .retrieve()
                .toBodilessEntity();
    }

    public AnalysisResult analyzeArticle(String url, String title, String text) {
        try {
            AnalysisResponse response = restClient.post()
                    .uri("/ai/analyze")
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(new AnalysisRequestBody(url, title, text, null))
                    .retrieve()
                    .body(AnalysisResponse.class);

            if (response == null) {
                return placeholder(title, url, text);
            }

            return new AnalysisResult(
                    blankToFallback(response.summary(), text),
                    response.adProbValue(),
                    response.isClickbait() != null ? response.isClickbait() : Boolean.TRUE.equals(response.isAd()),
                    response.namedEntitiesValue()
            );
        } catch (Exception exception) {
            return placeholder(title, url, text);
        }
    }

    public CrawlResult crawlArticle(String url) {
        CrawlResponse response = restClient.post()
                .uri(uriBuilder -> uriBuilder
                        .path("/crawl/article")
                        .queryParam("url", url)
                        .build())
                .retrieve()
                .body(CrawlResponse.class);

        if (response == null) {
            throw new IllegalStateException("Crawl response is empty");
        }

        return new CrawlResult(
                response.title(),
                response.url(),
                response.content(),
                response.publishedAt(),
                response.tokenCounts() != null ? response.tokenCounts() : Map.of(),
                response.keywords() != null ? response.keywords() : List.of()
        );
    }

    private AnalysisResult placeholder(String title, String url, String text) {
        String summary = text == null ? "" : text.substring(0, Math.min(text.length(), 280));
        return new AnalysisResult(
                summary.isBlank() ? title : summary,
                -1.0,
                false,
                List.of()
        );
    }

    private String blankToFallback(String summary, String text) {
        if (summary != null && !summary.isBlank()) {
            return summary;
        }
        if (text == null) {
            return "";
        }
        return text.substring(0, Math.min(text.length(), 280));
    }

    public record AnalysisResult(
            String summary,
            double adProbability,
            boolean isClickbait,
            Object namedEntities
    ) {
    }

    public record AnalysisResponse(
            String summary,
            @JsonProperty("ad_prob") Double adProb,
            @JsonProperty("ad_probability") Double adProbability,
            @JsonProperty("is_ad") Boolean isAd,
            @JsonProperty("is_clickbait") Boolean isClickbait,
            Object entities,
            @JsonProperty("named_entities") Object namedEntities
    ) {
        public double adProbValue() {
            if (adProb != null) {
                return adProb;
            }
            return adProbability == null ? 0.0 : adProbability;
        }

        public Object namedEntitiesValue() {
            if (namedEntities != null) {
                return namedEntities;
            }
            return entities != null ? entities : List.of();
        }
    }

    public record CrawlResult(
            String title,
            String url,
            String content,
            String publishedAt,
            Map<String, Integer> tokenCounts,
            List<String> keywords
    ) {
    }

    public record CrawlResponse(
            String title,
            String url,
            String content,
            @JsonProperty("published_at") String publishedAt,
            @JsonProperty("token_counts") LinkedHashMap<String, Integer> tokenCounts,
            List<String> keywords
    ) {
    }

    public record AnalysisRequestBody(
            String url,
            String title,
            String text,
            Long news_id
    ) {
    }
}
