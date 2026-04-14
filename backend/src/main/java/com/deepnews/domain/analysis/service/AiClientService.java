package com.deepnews.domain.analysis.service;

import org.springframework.http.MediaType;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

import java.util.Map;

@Service
public class AiClientService {

    private final RestClient restClient;

    public AiClientService() {
        this.restClient = RestClient.builder()
                .baseUrl("ai 서버")
                .build();
    }

    public void requestAnalysis(Long newsId) {
        restClient.post()
                .uri("/ai/analyze")
                .contentType(MediaType.APPLICATION_JSON)
                .body(Map.of("news_id", newsId))
                .retrieve()
                .toBodilessEntity();
    }
}
