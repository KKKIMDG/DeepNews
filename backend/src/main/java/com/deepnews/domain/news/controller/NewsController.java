package com.deepnews.domain.news.controller;

import com.deepnews.domain.news.dto.AnalyzeArticleRequestDto;
import com.deepnews.domain.news.dto.AnalyzeArticleResponseDto;
import com.deepnews.domain.news.dto.NewsInteractionRequestDto;
import com.deepnews.domain.news.dto.NewsCrawlRequestDto;
import com.deepnews.domain.news.service.NewsService;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/v1/news")
@RequiredArgsConstructor
public class NewsController {

    private final NewsService newsService;

    @PostMapping("/crawl")
    public ResponseEntity<String> receiveCrawl(@RequestBody NewsCrawlRequestDto dto) {
        Long savedNewsId = newsService.saveCrawledData(dto);

        return ResponseEntity.ok("뉴스 수집 및 분석 요청 완료 (ID: " + savedNewsId + ")");
    }

    @PostMapping("/analyze")
    public ResponseEntity<AnalyzeArticleResponseDto> analyzeArticle(@RequestBody AnalyzeArticleRequestDto dto) {
        return ResponseEntity.ok(newsService.analyzeOrGet(dto));
    }

    @PostMapping("/interactions")
    public ResponseEntity<Void> recordInteraction(@RequestBody NewsInteractionRequestDto dto) {
        newsService.recordInteraction(dto);
        return ResponseEntity.noContent().build();
    }

    @PostMapping("/crawl/bulk")
    public ResponseEntity<Map<String, Object>> receiveBulkCrawl(@RequestBody List<NewsCrawlRequestDto> dtos) {
        int successCount = 0;
        int failCount = 0;
        List<String> failMessages = new ArrayList<>();

        for (NewsCrawlRequestDto dto : dtos) {
            try {
                newsService.saveCrawledData(dto);
                successCount++;
            } catch (Exception e) {
                failCount++;
                failMessages.add(dto.getTitle() + " : " + e.getMessage());
            }
        }

        Map<String, Object> result = new HashMap<>();
        result.put("total", dtos.size());
        result.put("success", successCount);
        result.put("fail", failCount);
        result.put("errors", failMessages);

        return ResponseEntity.ok(result);
    }
}
