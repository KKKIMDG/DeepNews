package com.deepnews.domain.news.entity;

import com.deepnews.domain.analysis.entity.NewsAnalysis;
import com.deepnews.domain.keyword.entity.ArticleKeyword;
import com.deepnews.domain.news.dto.ArticleData;
import jakarta.persistence.*;
import lombok.*;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.jpa.domain.support.AuditingEntityListener;

import java.time.LocalDateTime;
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

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(name = "article_data", columnDefinition = "jsonb")
    private ArticleData articleData;

    @CreatedDate
    @Column(updatable = false)
    private LocalDateTime createdAt;

    @OneToOne(mappedBy = "news", cascade = CascadeType.ALL, orphanRemoval = true)
    private NewsAnalysis newsAnalysis;

    @OneToMany(mappedBy = "news", cascade = CascadeType.ALL, orphanRemoval = true)
    @Builder.Default
    private List<ArticleKeyword> articleKeywords = new ArrayList<>();
}