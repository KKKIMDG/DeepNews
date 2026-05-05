package com.deepnews.domain.news.service;

import com.deepnews.domain.analysis.entity.NewsAnalysis;
import com.deepnews.domain.analysis.repository.NewsAnalysisRepository;
import com.deepnews.domain.analysis.service.AiClientService;
import com.deepnews.domain.keyword.entity.ArticleKeyword;
import com.deepnews.domain.keyword.entity.Keyword;
import com.deepnews.domain.keyword.repository.ArticleKeywordRepository;
import com.deepnews.domain.keyword.repository.KeywordRepository;
import com.deepnews.domain.news.dto.AnalyzeArticleRequestDto;
import com.deepnews.domain.news.dto.AnalyzeArticleResponseDto;
import com.deepnews.domain.news.dto.ArticleData;
import com.deepnews.domain.news.dto.NewsInteractionRequestDto;
import com.deepnews.domain.news.dto.NewsCrawlRequestDto;
import com.deepnews.domain.news.entity.News;
import com.deepnews.domain.news.repository.NewsRepository;
import com.deepnews.domain.recommendation.entity.NewsInteraction;
import com.deepnews.domain.recommendation.repository.NewsInteractionRepository;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.json.JsonMapper;
import jakarta.transaction.Transactional;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.TimeUnit;
import java.util.stream.Collectors;

// domain/news/service/NewsService.java
@Service
@RequiredArgsConstructor
@Transactional
public class NewsService {

    private static final int KEYWORD_LIMIT = 8;
    private static final int RECOMMENDATION_LIMIT = 5;
    private static final Duration KEYWORD_EXTRACTOR_TIMEOUT = Duration.ofSeconds(20);
    private static final String VIEW_INTERACTION = "VIEW";
    private static final List<String> KOREAN_PARTICLE_SUFFIXES = List.of(
            "으로부터", "에게서", "에서는", "으로써", "로부터", "이라는", "라는", "에서", "에게", "까지", "부터",
            "으로", "라고", "하고", "보다", "처럼", "마다", "이며", "이며", "이고", "하고", "은", "는", "이", "가",
            "을", "를", "의", "에", "와", "과", "도", "로", "만"
    );
    private static final List<String> KEYWORD_STOPWORDS = List.of(
            "기자", "뉴스", "기사", "사진", "영상", "제공", "관련", "이번", "지난", "오늘", "내일", "오전", "오후",
            "무단", "전재", "재배포", "금지", "네이버", "본문", "내용", "결과", "통해", "대해", "위해", "대한",
            "있다", "했다", "한다", "되는", "한다", "됐다", "기반", "사용", "서비스", "것으로", "것은", "것이"
    );
    private static final Map<String, Integer> INTERACTION_WEIGHTS = Map.of(
            VIEW_INTERACTION, 1,
            "CLICK", 3,
            "BOOKMARK", 5,
            "DISMISS", 0
    );

    private final NewsRepository newsRepository;
    private final NewsAnalysisRepository newsAnalysisRepository;
    private final KeywordRepository keywordRepository;
    private final ArticleKeywordRepository articleKeywordRepository;
    private final NewsInteractionRepository newsInteractionRepository;
    private final AiClientService aiClientService;
    private static final ObjectMapper OBJECT_MAPPER = JsonMapper.builder().build();

    public Long saveCrawledData(NewsCrawlRequestDto dto) {
        Optional<News> existingNews = newsRepository.findByUrl(dto.getUrl());
        boolean isNew = existingNews.isEmpty();
        News savedNews = upsertNews(existingNews, dto.getTitle(), dto.getUrl(), buildArticleData(dto), dto.getToken_counts(), isNew);
        return savedNews.getId();
    }

    public AnalyzeArticleResponseDto analyzeOrGet(AnalyzeArticleRequestDto requestDto) {
        validateRequest(requestDto);

        Optional<News> existingNews = newsRepository.findByUrl(requestDto.getUrl());
        Optional<NewsAnalysis> existingAnalysis = Optional.empty();
        if (existingNews.isPresent()) {
            existingAnalysis = newsAnalysisRepository.findByNewsId(existingNews.get().getId());
            if (existingAnalysis.isPresent()) {
                recordInteraction(existingNews.get(), requestDto.getClientUserId(), VIEW_INTERACTION);
                return buildAnalyzeResponse(existingNews.get(), existingAnalysis.get(), true, requestDto.getClientUserId());
            }
        }

        AiClientService.CrawlResult crawlResult = resolveCrawlResult(existingNews, requestDto);

        News news = upsertNews(
                existingNews,
                crawlResult.title(),
                crawlResult.url(),
                buildArticleData(crawlResult),
                crawlResult.tokenCounts(),
                existingNews.isEmpty()
        );

        AiClientService.AnalysisResult analysisResult = aiClientService.analyzeArticle(
                crawlResult.url(),
                crawlResult.title(),
                crawlResult.content()
        );

        NewsAnalysis analysis = existingAnalysis
                .map(existing -> existing.updateFrom(
                        analysisResult.summary(),
                        scaledProbability(analysisResult.adProbability()),
                        analysisResult.isClickbait(),
                        serializeNamedEntities(analysisResult.namedEntities())
                ))
                .orElseGet(() -> newsAnalysisRepository.save(
                        NewsAnalysis.builder()
                                .news(news)
                                .summary(analysisResult.summary())
                                .adProbability(scaledProbability(analysisResult.adProbability()))
                                .isClickbait(analysisResult.isClickbait())
                                .namedEntities(serializeNamedEntities(analysisResult.namedEntities()))
                                .build()
                ));

        recordInteraction(news, requestDto.getClientUserId(), VIEW_INTERACTION);
        return buildAnalyzeResponse(news, analysis, false, requestDto.getClientUserId());
    }

    public void recordInteraction(NewsInteractionRequestDto requestDto) {
        if (requestDto == null || isBlank(requestDto.getClientUserId())) {
            return;
        }

        Optional<News> news = Optional.empty();
        if (requestDto.getNewsId() != null) {
            news = newsRepository.findById(requestDto.getNewsId());
        }
        if (news.isEmpty() && !isBlank(requestDto.getUrl())) {
            news = newsRepository.findByUrl(requestDto.getUrl());
        }

        news.ifPresent(value -> recordInteraction(
                value,
                requestDto.getClientUserId(),
                normalizeInteractionType(requestDto.getInteractionType())
        ));
    }

    private News upsertNews(
            Optional<News> existingNews,
            String title,
            String url,
            ArticleData articleData,
            Map<String, Integer> tokenCounts,
            boolean syncKeywords
    ) {
        News news = existingNews
                .orElseGet(() -> News.builder()
                        .title(title)
                        .url(url)
                        .articleData(articleData)
                        .build());

        if (existingNews.isPresent()) {
            news.updateArticle(title, articleData);
        }

        News savedNews = existingNews.isPresent() ? news : newsRepository.save(news);

        if (syncKeywords && tokenCounts != null && !tokenCounts.isEmpty()) {
            articleKeywordRepository.deleteByNewsId(savedNews.getId());
            saveKeywordMappings(savedNews, tokenCounts);
        }

        return savedNews;
    }

    private void saveKeywordMappings(News news, Map<String, Integer> tokenCounts) {
        Map<String, Integer> limitedTokenCounts = limitTokenCounts(tokenCounts);

        Map<String, Keyword> keywordsByWord = keywordRepository.findAllByWordIn(limitedTokenCounts.keySet()).stream()
                .collect(Collectors.toMap(Keyword::getWord, keyword -> keyword, (left, right) -> left, LinkedHashMap::new));

        List<Keyword> newKeywords = limitedTokenCounts.keySet().stream()
                .filter(word -> !keywordsByWord.containsKey(word))
                .map(word -> Keyword.builder()
                        .word(word)
                        .totalCount(limitedTokenCounts.get(word))
                        .articleCount(1)
                        .build())
                .toList();

        if (!newKeywords.isEmpty()) {
            keywordRepository.saveAll(newKeywords);
            newKeywords.forEach(keyword -> keywordsByWord.put(keyword.getWord(), keyword));
        }

        List<ArticleKeyword> mappings = new ArrayList<>(limitedTokenCounts.size());
        limitedTokenCounts.forEach((word, count) -> {
            Keyword keyword = keywordsByWord.get(word);
            if (!isNewKeyword(keyword, newKeywords)) {
                keyword.updateStatistics(count);
            }
            mappings.add(ArticleKeyword.builder()
                    .news(news)
                    .keyword(keyword)
                    .count(count)
                    .build());
        });

        articleKeywordRepository.saveAll(mappings);
    }

    private boolean isNewKeyword(Keyword keyword, List<Keyword> newKeywords) {
        return newKeywords.contains(keyword);
    }

    private Map<String, Integer> limitTokenCounts(Map<String, Integer> tokenCounts) {
        return tokenCounts.entrySet().stream()
                .sorted(Map.Entry.<String, Integer>comparingByValue(Comparator.reverseOrder()))
                .limit(KEYWORD_LIMIT)
                .collect(Collectors.toMap(
                        Map.Entry::getKey,
                        Map.Entry::getValue,
                        (left, right) -> left,
                        LinkedHashMap::new
                ));
    }

    private ArticleData buildArticleData(NewsCrawlRequestDto dto) {
        ArticleData articleData = new ArticleData();
        articleData.setSource(dto.getSource());
        articleData.setContent(dto.getContent());
        articleData.setPublishedAt(dto.getPublished_at());
        articleData.setExtraData(dto.getExtraData());
        return articleData;
    }

    private ArticleData buildArticleData(AiClientService.CrawlResult crawlResult) {
        ArticleData articleData = new ArticleData();
        articleData.setSource("naver_news");
        articleData.setContent(crawlResult.content());
        articleData.setPublishedAt(crawlResult.publishedAt());
        articleData.setExtraData(Map.of(
                "keywords", crawlResult.keywords().stream()
                        .map(keyword -> Map.of(
                                "term", keyword,
                                "count", crawlResult.tokenCounts().getOrDefault(keyword, 0)
                        ))
                        .toList(),
                "token_counts", crawlResult.tokenCounts()
        ));
        return articleData;
    }

    private AiClientService.CrawlResult resolveCrawlResult(
            Optional<News> existingNews,
            AnalyzeArticleRequestDto requestDto
    ) {
        Optional<AiClientService.CrawlResult> requestArticle = buildCrawlResultFromRequest(requestDto);
        if (existingNews.isPresent()) {
            return rebuildFromExistingNews(existingNews.get())
                    .or(() -> requestArticle)
                    .orElseGet(() -> aiClientService.crawlArticle(requestDto.getUrl()));
        }

        return requestArticle.orElseGet(() -> aiClientService.crawlArticle(requestDto.getUrl()));
    }

    private Optional<AiClientService.CrawlResult> buildCrawlResultFromRequest(AnalyzeArticleRequestDto requestDto) {
        if (requestDto == null || isBlank(requestDto.getContent())) {
            return Optional.empty();
        }

        String title = isBlank(requestDto.getTitle()) ? requestDto.getUrl() : requestDto.getTitle().trim();
        String content = requestDto.getContent().trim();
        Map<String, Integer> tokenCounts = extractTokenCountsWithPython(title, content)
                .orElseGet(() -> extractSimpleTokenCounts(title, content));
        List<String> keywords = tokenCounts.keySet().stream().limit(KEYWORD_LIMIT).toList();

        return Optional.of(new AiClientService.CrawlResult(
                title,
                requestDto.getUrl(),
                content,
                "",
                tokenCounts,
                keywords
        ));
    }

    private Optional<Map<String, Integer>> extractTokenCountsWithPython(String title, String content) {
        Path scriptPath = Path.of("batch", "deepnews_batch", "keyword_extractor.py");
        if (!Files.exists(scriptPath)) {
            return Optional.empty();
        }

        String pythonCommand = Optional.ofNullable(System.getenv("DEEPNEWS_PYTHON"))
                .filter(value -> !value.isBlank())
                .orElse("python");

        try {
            Process process = new ProcessBuilder(pythonCommand, scriptPath.toString())
                    .directory(Path.of(".").toFile())
                    .redirectErrorStream(true)
                    .start();

            Map<String, String> payload = Map.of(
                    "title", title == null ? "" : title,
                    "content", content == null ? "" : content
            );
            process.getOutputStream().write(OBJECT_MAPPER.writeValueAsBytes(payload));
            process.getOutputStream().close();

            boolean finished = process.waitFor(KEYWORD_EXTRACTOR_TIMEOUT.toMillis(), TimeUnit.MILLISECONDS);
            String output = new String(process.getInputStream().readAllBytes(), StandardCharsets.UTF_8);
            if (!finished) {
                process.destroyForcibly();
                return Optional.empty();
            }
            if (process.exitValue() != 0 || output.isBlank()) {
                return Optional.empty();
            }

            Map<String, Object> result = OBJECT_MAPPER.readValue(output, new TypeReference<>() {
            });
            Object tokenCountsValue = result.get("token_counts");
            if (!(tokenCountsValue instanceof Map<?, ?> tokenCounts)) {
                return Optional.empty();
            }

            Map<String, Integer> parsed = tokenCounts.entrySet().stream()
                    .filter(entry -> entry.getKey() != null && entry.getValue() instanceof Number)
                    .collect(Collectors.toMap(
                            entry -> entry.getKey().toString(),
                            entry -> ((Number) entry.getValue()).intValue(),
                            (left, right) -> left,
                            LinkedHashMap::new
                    ));
            return parsed.isEmpty() ? Optional.empty() : Optional.of(limitTokenCounts(parsed));
        } catch (Exception exception) {
            return Optional.empty();
        }
    }

    private Map<String, Integer> extractSimpleTokenCounts(String title, String content) {
        Map<String, Integer> scores = new LinkedHashMap<>();
        addKeywordScores(scores, title, 3);
        addKeywordScores(scores, content, 1);
        return limitTokenCounts(scores);
    }

    private void addKeywordScores(Map<String, Integer> scores, String text, int weight) {
        String normalized = (text == null ? "" : text)
                .replaceAll("<[^>]+>", " ")
                .replaceAll("[^\\p{L}\\p{N}\\s]", " ")
                .toLowerCase();

        for (String rawToken : normalized.split("\\s+")) {
            String token = normalizeKeywordToken(rawToken);
            if (!isUsefulKeyword(token)) {
                continue;
            }
            scores.merge(token, weight, Integer::sum);
        }
    }

    private String normalizeKeywordToken(String rawToken) {
        String token = rawToken == null ? "" : rawToken.trim();
        boolean changed = true;
        while (changed) {
            changed = false;
            for (String suffix : KOREAN_PARTICLE_SUFFIXES) {
                if (token.length() > suffix.length() + 1 && token.endsWith(suffix)) {
                    token = token.substring(0, token.length() - suffix.length());
                    changed = true;
                    break;
                }
            }
        }
        return token;
    }

    private boolean isUsefulKeyword(String token) {
        if (token.length() < 2 || token.length() > 24) {
            return false;
        }
        if (token.matches("\\d+")) {
            return false;
        }
        return !KEYWORD_STOPWORDS.contains(token);
    }

    private Optional<AiClientService.CrawlResult> rebuildFromExistingNews(News news) {
        ArticleData articleData = news.getArticleData();
        if (articleData == null || isBlank(articleData.getContent())) {
            return Optional.empty();
        }

        Map<String, Integer> tokenCounts = extractTokenCounts(articleData);
        List<String> keywords = tokenCounts.entrySet().stream()
                .sorted(Map.Entry.<String, Integer>comparingByValue().reversed())
                .map(Map.Entry::getKey)
                .toList();

        return Optional.of(new AiClientService.CrawlResult(
                news.getTitle(),
                news.getUrl(),
                articleData.getContent(),
                articleData.getPublishedAt(),
                tokenCounts,
                keywords
        ));
    }

    @SuppressWarnings("unchecked")
    private Map<String, Integer> extractTokenCounts(ArticleData articleData) {
        if (articleData == null || articleData.getExtraData() == null) {
            return Map.of();
        }

        Object tokenCounts = articleData.getExtraData().get("token_counts");
        if (!(tokenCounts instanceof Map<?, ?> tokenCountMap)) {
            return Map.of();
        }

        return tokenCountMap.entrySet().stream()
                .filter(entry -> entry.getKey() != null && entry.getValue() != null)
                .collect(Collectors.toMap(
                        entry -> entry.getKey().toString(),
                        entry -> ((Number) entry.getValue()).intValue()
                ));
    }

    private BigDecimal scaledProbability(double value) {
        return BigDecimal.valueOf(value).setScale(2, RoundingMode.HALF_UP);
    }

    private String serializeNamedEntities(Object namedEntities) {
        try {
            return OBJECT_MAPPER.writeValueAsString(namedEntities == null ? List.of() : namedEntities);
        } catch (JsonProcessingException exception) {
            throw new IllegalStateException("Failed to serialize named entities", exception);
        }
    }

    private void validateRequest(AnalyzeArticleRequestDto requestDto) {
        if (requestDto == null) {
            throw new IllegalArgumentException("request payload is required");
        }
        if (isBlank(requestDto.getUrl())) {
            throw new IllegalArgumentException("article url is required");
        }
    }

    private boolean isBlank(String value) {
        return value == null || value.isBlank();
    }

    private AnalyzeArticleResponseDto buildAnalyzeResponse(
            News news,
            NewsAnalysis analysis,
            boolean cached,
            String clientUserId
    ) {
        return AnalyzeArticleResponseDto.from(
                news,
                analysis,
                cached,
                buildRecommendations(news.getId(), clientUserId)
        );
    }

    private List<AnalyzeArticleResponseDto.RecommendationPayload> buildRecommendations(
            Long newsId,
            String clientUserId
    ) {
        Map<Long, AnalyzeArticleResponseDto.RecommendationPayload> recommendations = new LinkedHashMap<>();

        addRecommendations(
                recommendations,
                newsInteractionRepository.findCollaborativeRecommendations(
                        newsId,
                        isBlank(clientUserId) ? null : clientUserId,
                        RECOMMENDATION_LIMIT
                ),
                "Collaborative filtering"
        );

        if (recommendations.size() < RECOMMENDATION_LIMIT) {
            addRecommendations(
                    recommendations,
                    articleKeywordRepository.findKeywordSimilarRecommendations(
                            newsId,
                            isBlank(clientUserId) ? null : clientUserId,
                            RECOMMENDATION_LIMIT * 2
                    ),
                    "Keyword similarity"
            );
        }

        return recommendations.values().stream()
                .filter(item -> !item.getNewsId().equals(newsId))
                .limit(RECOMMENDATION_LIMIT)
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

    private void recordInteraction(News news, String clientUserId, String interactionType) {
        if (news == null || isBlank(clientUserId)) {
            return;
        }

        String normalizedInteractionType = normalizeInteractionType(interactionType);
        int weight = INTERACTION_WEIGHTS.getOrDefault(normalizedInteractionType, 1);
        NewsInteraction interaction = newsInteractionRepository
                .findExistingInteraction(clientUserId, news.getId(), normalizedInteractionType)
                .orElseGet(() -> NewsInteraction.builder()
                        .clientUserId(clientUserId)
                        .news(news)
                        .interactionType(normalizedInteractionType)
                        .weight(weight)
                        .build());
        interaction.refreshWeight(weight);
        newsInteractionRepository.save(interaction);
    }

    private String normalizeInteractionType(String interactionType) {
        if (isBlank(interactionType)) {
            return VIEW_INTERACTION;
        }
        String normalized = interactionType.trim().toUpperCase();
        return INTERACTION_WEIGHTS.containsKey(normalized) ? normalized : VIEW_INTERACTION;
    }
}
