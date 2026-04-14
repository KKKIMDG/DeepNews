package com.deepnews.domain.news.dto;

import lombok.Getter;
import lombok.NoArgsConstructor;

import java.util.Map;

@Getter
@NoArgsConstructor
public class NewsCrawlRequestDto {
    private String title;
    private String url;
    private String source;
    private String content;
    private String original_content;
    private String published_at;
    private Map<String, Integer> token_counts;
}
