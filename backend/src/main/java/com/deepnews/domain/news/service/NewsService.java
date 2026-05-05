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
import com.deepnews.domain.news.dto.NewsCrawlRequestDto;
import com.deepnews.domain.news.entity.News;
import com.deepnews.domain.news.repository.NewsRepository;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.json.JsonMapper;
import jakarta.transaction.Transactional;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.stream.Collectors;

// domain/news/service/NewsService.java
@Service
@RequiredArgsConstructor
@Transactional
public class NewsService {

    private static final int KEYWORD_LIMIT = 8;

    private final NewsRepository newsRepository;
    private final NewsAnalysisRepository newsAnalysisRepository;
    private final KeywordRepository keywordRepository;
    private final ArticleKeywordRepository articleKeywordRepository;
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
                return AnalyzeArticleResponseDto.from(existingNews.get(), existingAnalysis.get(), true);
            }
        }

        AiClientService.CrawlResult crawlResult = existingNews.isPresent()
                ? rebuildFromExistingNews(existingNews.get())
                        .orElseGet(() -> aiClientService.crawlArticle(requestDto.getUrl()))
                : aiClientService.crawlArticle(requestDto.getUrl());

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

        return AnalyzeArticleResponseDto.from(news, analysis, false);
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

        News savedNews = existingNews.isPresent() ? news : newsRepository.save(news);

        if (syncKeywords && tokenCounts != null && !tokenCounts.isEmpty()) {
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
}
