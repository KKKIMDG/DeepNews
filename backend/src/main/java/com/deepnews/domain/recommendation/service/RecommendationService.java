package com.deepnews.domain.recommendation.service;

import com.deepnews.domain.keyword.repository.ArticleKeywordRepository;
import com.deepnews.domain.news.dto.AnalyzeArticleResponseDto;
import com.deepnews.domain.recommendation.repository.NewsInteractionRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

@Service
@RequiredArgsConstructor
public class RecommendationService {

    private static final int DEFAULT_LIMIT = 5;

    private final NewsInteractionRepository newsInteractionRepository;
    private final ArticleKeywordRepository articleKeywordRepository;

    public List<AnalyzeArticleResponseDto.RecommendationPayload> recommend(
            Long currentNewsId,
            String clientUserId
    ) {
        return recommend(currentNewsId, clientUserId, DEFAULT_LIMIT);
    }

    public List<AnalyzeArticleResponseDto.RecommendationPayload> recommend(
            Long currentNewsId,
            String clientUserId,
            int limit
    ) {
        int normalizedLimit = Math.max(1, limit);
        String normalizedClientUserId = isBlank(clientUserId) ? null : clientUserId.trim();
        Map<Long, AnalyzeArticleResponseDto.RecommendationPayload> recommendations = new LinkedHashMap<>();

        if (normalizedClientUserId != null) {
            addRecommendations(
                    recommendations,
                    newsInteractionRepository.findUserCollaborativeRecommendations(
                            normalizedClientUserId,
                            normalizedLimit
                    ),
                    "Collaborative filtering: similar readers"
            );
        }

        if (recommendations.size() < normalizedLimit && currentNewsId != null) {
            addRecommendations(
                    recommendations,
                    newsInteractionRepository.findCollaborativeRecommendations(
                            currentNewsId,
                            normalizedClientUserId,
                            normalizedLimit * 2
                    ),
                    "Collaborative filtering: readers also viewed"
            );
        }

        if (recommendations.size() < normalizedLimit && currentNewsId != null) {
            addRecommendations(
                    recommendations,
                    articleKeywordRepository.findKeywordSimilarRecommendations(
                            currentNewsId,
                            normalizedClientUserId,
                            normalizedLimit * 2
                    ),
                    "Keyword similarity"
            );
        }

        return recommendations.values().stream()
                .filter(item -> currentNewsId == null || !item.getNewsId().equals(currentNewsId))
                .limit(normalizedLimit)
                .toList();
    }

    private void addRecommendations(
            Map<Long, AnalyzeArticleResponseDto.RecommendationPayload> recommendations,
            List<Object[]> rows,
            String reason
    ) {
        for (Object[] row : rows) {
            Long recommendedNewsId = ((Number) row[0]).longValue();
            if (recommendations.containsKey(recommendedNewsId)) {
                continue;
            }

            double score = row[3] instanceof Number number ? number.doubleValue() : 0.0;
            recommendations.put(recommendedNewsId, new AnalyzeArticleResponseDto.RecommendationPayload(
                    recommendedNewsId,
                    String.valueOf(row[1]),
                    String.valueOf(row[2]),
                    score,
                    reason
            ));
        }
    }

    private boolean isBlank(String value) {
        return value == null || value.isBlank();
    }
}
