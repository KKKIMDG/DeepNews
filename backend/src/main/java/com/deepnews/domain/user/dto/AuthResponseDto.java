package com.deepnews.domain.user.dto;

import lombok.Getter;

@Getter
public class AuthResponseDto {

    private final Long userId;
    private final String loginId;
    private final String clientUserId;

    public AuthResponseDto(Long userId, String loginId) {
        this.userId = userId;
        this.loginId = loginId;
        this.clientUserId = "account:" + userId;
    }
}
