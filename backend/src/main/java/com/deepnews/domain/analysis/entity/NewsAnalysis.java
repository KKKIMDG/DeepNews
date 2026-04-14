package com.deepnews.domain.analysis.entity;

import com.deepnews.domain.news.entity.News;
import jakarta.persistence.*;
import lombok.*;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.jpa.domain.support.AuditingEntityListener;
import java.math.BigDecimal;
import java.time.ZonedDateTime;

@Entity
@Table(name = "news_analysis")
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
@AllArgsConstructor
@Builder
@EntityListeners(AuditingEntityListener.class)
public class NewsAnalysis {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @OneToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "news_id", nullable = false, unique = true)
    private News news;

    @Column(nullable = false, columnDefinition = "TEXT")
    private String summary;

    @Column(nullable = false, precision = 5, scale = 2)
    private BigDecimal adProbability;

    @Column(nullable = false)
    @Builder.Default
    private Boolean isClickbait = false;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(columnDefinition = "jsonb")
    private String namedEntities;

    @CreatedDate
    @Column(updatable = false)
    private ZonedDateTime analyzedAt;
}
