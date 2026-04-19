package com.deepnews.domain.news.service;

import com.deepnews.domain.keyword.entity.ArticleKeyword;
import com.deepnews.domain.keyword.entity.Keyword;
import com.deepnews.domain.keyword.repository.ArticleKeywordRepository;
import com.deepnews.domain.keyword.repository.KeywordRepository;
import com.deepnews.domain.news.dto.ArticleData;
import com.deepnews.domain.news.dto.NewsCrawlRequestDto;
import com.deepnews.domain.news.entity.News;
import com.deepnews.domain.news.repository.NewsRepository;
import jakarta.transaction.Transactional;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;

import java.time.LocalDateTime;

// domain/news/service/NewsService.java
@Service
@RequiredArgsConstructor
@Transactional
public class NewsService {

    private final NewsRepository newsRepository;
    private final KeywordRepository keywordRepository;
    private final ArticleKeywordRepository articleKeywordRepository;

    public Long saveCrawledData(NewsCrawlRequestDto dto) {

        ArticleData articleData = new ArticleData();
        articleData.setSource(dto.getSource());
        articleData.setContent(dto.getContent());
        articleData.setPublishedAt(dto.getPublished_at());
        articleData.setExtraData(dto.getExtraData());

        News news = News.builder()
                .title(dto.getTitle())
                .url(dto.getUrl())
                .articleData(articleData)
                .build();

        News savedNews = newsRepository.save(news);

        if (dto.getToken_counts() != null) {
            dto.getToken_counts().forEach((word, count) -> {
                Keyword keyword = keywordRepository.findByWord(word)
                        .orElseGet(() -> keywordRepository.save(
                                Keyword.builder().word(word).build()
                        ));

                keyword.updateStatistics(count);

                ArticleKeyword mapping = ArticleKeyword.builder()
                        .news(savedNews)
                        .keyword(keyword)
                        .count(count)
                        .build();

                articleKeywordRepository.save(mapping);
            });
        }

        return savedNews.getId();
    }
}
