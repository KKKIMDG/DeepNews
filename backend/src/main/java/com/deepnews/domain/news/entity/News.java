package com.deepnews.domain.news.entity;

import com.deepnews.domain.analysis.entity.NewsAnalysis;
import com.deepnews.domain.keyword.entity.ArticleKeyword;
import jakarta.persistence.*;
import lombok.*;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.jpa.domain.support.AuditingEntityListener;

import java.time.LocalDateTime;
import java.time.ZonedDateTime;
import java.util.ArrayList;
import java.util.List;

@Entity
@Table(name = "news")
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
@AllArgsConstructor
@Builder
@EntityListeners(AuditingEntityListener.class)
public class News {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String title;

    @Column(nullable = false, unique = true, length = 512)
    private String url;

    @Column(nullable = false, length = 100)
    private String source;

    @Column(nullable = false, columnDefinition = "TEXT")
    private String content;

    @Column(columnDefinition = "TEXT")
    private String originalContent;

    private LocalDateTime publishedAt;

    @CreatedDate
    @Column(updatable = false)
    private LocalDateTime createdAt;

    // 1:1 매핑 (뉴스 분석 결과)
    @OneToOne(mappedBy = "news", cascade = CascadeType.ALL, orphanRemoval = true)
    private NewsAnalysis newsAnalysis;

    // 1:N 매핑
    @OneToMany(mappedBy = "news", cascade = CascadeType.ALL, orphanRemoval = true)
    @Builder.Default
    private List<ArticleKeyword> articleKeywords = new ArrayList<>();
}
