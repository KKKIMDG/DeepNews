package com.deepnews.domain.keyword.entity;

import com.deepnews.domain.news.entity.News;
import jakarta.persistence.*;
import lombok.*;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.jpa.domain.support.AuditingEntityListener;
import java.time.ZonedDateTime;

@Entity
@Table(
        name = "article_keyword",
        uniqueConstraints = {
                @UniqueConstraint(name = "unique_news_keyword", columnNames = {"news_id", "keyword_id"})
        }
)
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
@AllArgsConstructor
@Builder
@EntityListeners(AuditingEntityListener.class)
public class ArticleKeyword {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    // 다대일 (N:1) 관계
    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "news_id", nullable = false)
    private News news;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "keyword_id", nullable = false)
    private Keyword keyword;

    @Column(nullable = false)
    @Builder.Default
    private Integer count = 1;

    @CreatedDate
    @Column(updatable = false)
    private ZonedDateTime createdAt;
}
