package com.deepnews.domain.user.dto;

import lombok.Getter;
import lombok.Setter;

@Getter
@Setter
public class AuthRequestDto {

    private String loginId;
    private String password;
}
