package com.deepnews.domain.news.dto;

import lombok.Getter;
import lombok.Setter;

@Getter
@Setter
public class NewsInteractionRequestDto {

    private Long newsId;
    private String url;
    private String clientUserId;
    private String interactionType;
}
