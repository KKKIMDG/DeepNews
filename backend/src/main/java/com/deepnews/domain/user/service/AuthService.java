package com.deepnews.domain.user.service;

import com.deepnews.domain.user.dto.AuthRequestDto;
import com.deepnews.domain.user.dto.AuthResponseDto;
import com.deepnews.domain.user.entity.User;
import com.deepnews.domain.user.repository.UserRepository;
import jakarta.transaction.Transactional;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;

import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;
import java.security.SecureRandom;
import java.util.Base64;

@Service
@RequiredArgsConstructor
@Transactional
public class AuthService {

    private static final SecureRandom SECURE_RANDOM = new SecureRandom();
    private static final int SALT_BYTES = 16;
    private static final int ITERATIONS = 120_000;
    private static final int KEY_BITS = 256;

    private final UserRepository userRepository;

    public AuthResponseDto signUp(AuthRequestDto requestDto) {
        validate(requestDto);
        String loginId = normalizeLoginId(requestDto.getLoginId());
        if (userRepository.existsByLoginId(loginId)) {
            throw new IllegalArgumentException("이미 사용 중인 아이디입니다.");
        }

        User user = userRepository.save(User.builder()
                .loginId(loginId)
                .email(loginId + "@deepnews.local")
                .password(hashPassword(requestDto.getPassword()))
                .nickname(loginId)
                .provider("local")
                .build());

        return new AuthResponseDto(user.getId(), user.getLoginId());
    }

    public AuthResponseDto login(AuthRequestDto requestDto) {
        validate(requestDto);
        String loginId = normalizeLoginId(requestDto.getLoginId());
        User user = userRepository.findByLoginId(loginId)
                .orElseThrow(() -> new IllegalArgumentException("아이디 또는 비밀번호가 올바르지 않습니다."));

        if (!verifyPassword(requestDto.getPassword(), user.getPassword())) {
            throw new IllegalArgumentException("아이디 또는 비밀번호가 올바르지 않습니다.");
        }

        return new AuthResponseDto(user.getId(), user.getLoginId());
    }

    private void validate(AuthRequestDto requestDto) {
        if (requestDto == null || isBlank(requestDto.getLoginId()) || isBlank(requestDto.getPassword())) {
            throw new IllegalArgumentException("아이디와 비밀번호를 입력해 주세요.");
        }
        String loginId = normalizeLoginId(requestDto.getLoginId());
        if (!loginId.matches("[a-zA-Z0-9_]{4,30}")) {
            throw new IllegalArgumentException("아이디는 영문, 숫자, 밑줄 4~30자로 입력해 주세요.");
        }
        if (requestDto.getPassword().length() < 6) {
            throw new IllegalArgumentException("비밀번호는 6자 이상 입력해 주세요.");
        }
    }

    private String normalizeLoginId(String loginId) {
        return loginId == null ? "" : loginId.trim().toLowerCase();
    }

    private String hashPassword(String password) {
        byte[] salt = new byte[SALT_BYTES];
        SECURE_RANDOM.nextBytes(salt);
        byte[] hash = pbkdf2(password.toCharArray(), salt);
        return "pbkdf2$" + ITERATIONS + "$"
                + Base64.getEncoder().encodeToString(salt) + "$"
                + Base64.getEncoder().encodeToString(hash);
    }

    private boolean verifyPassword(String password, String encoded) {
        if (encoded == null || !encoded.startsWith("pbkdf2$")) {
            return false;
        }
        String[] parts = encoded.split("\\$");
        if (parts.length != 4) {
            return false;
        }
        byte[] salt = Base64.getDecoder().decode(parts[2]);
        byte[] expected = Base64.getDecoder().decode(parts[3]);
        byte[] actual = pbkdf2(password.toCharArray(), salt);
        return java.security.MessageDigest.isEqual(expected, actual);
    }

    private byte[] pbkdf2(char[] password, byte[] salt) {
        try {
            PBEKeySpec spec = new PBEKeySpec(password, salt, ITERATIONS, KEY_BITS);
            return SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256").generateSecret(spec).getEncoded();
        } catch (Exception exception) {
            throw new IllegalStateException("비밀번호 처리 중 오류가 발생했습니다.", exception);
        }
    }

    private boolean isBlank(String value) {
        return value == null || value.isBlank();
    }
}
