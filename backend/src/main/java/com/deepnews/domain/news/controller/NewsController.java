package com.deepnews.domain.news.controller;

import com.deepnews.domain.analysis.service.AiClientService;
import com.deepnews.domain.news.dto.NewsCrawlRequestDto;
import com.deepnews.domain.news.service.NewsService;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/news")
@RequiredArgsConstructor
public class NewsController {

    private final NewsService newsService;
    private final AiClientService aiClientService;

    @PostMapping("/crawl")
    public ResponseEntity<String> receiveCrawl(@RequestBody NewsCrawlRequestDto dto) {
        Long savedNewsId = newsService.saveCrawledData(dto);

        aiClientService.requestAnalysis(savedNewsId);

        return ResponseEntity.ok("뉴스 수집 및 분석 요청 완료 (ID: " + savedNewsId + ")");
    }
}
