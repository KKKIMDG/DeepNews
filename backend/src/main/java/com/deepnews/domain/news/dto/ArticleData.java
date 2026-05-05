package com.deepnews.domain.news.dto;

import com.fasterxml.jackson.annotation.JsonAnySetter;
import lombok.EqualsAndHashCode;
import lombok.Getter;
import lombok.Setter;

import java.util.HashMap;
import java.util.Map;

@Getter
@Setter
@EqualsAndHashCode
public class ArticleData {

    private String source;
    private String content;
    private String publishedAt;

    private Map<String, Object> extraData = new HashMap<>();


    @JsonAnySetter
    public void setExtraData(String key, Object value) {
        this.extraData.put(key, value);
    }
}
