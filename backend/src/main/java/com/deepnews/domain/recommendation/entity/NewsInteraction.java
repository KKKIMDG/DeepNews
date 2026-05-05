package com.deepnews.domain.recommendation.entity;

import com.deepnews.domain.news.entity.News;
import jakarta.persistence.*;
import lombok.AccessLevel;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.jpa.domain.support.AuditingEntityListener;

import java.time.LocalDateTime;

@Entity
@Table(
        name = "news_interaction",
        uniqueConstraints = {
                @UniqueConstraint(
                        name = "unique_client_news_interaction",
                        columnNames = {"client_user_id", "news_id", "interaction_type"}
                )
        }
)
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
@AllArgsConstructor
@Builder
@EntityListeners(AuditingEntityListener.class)
public class NewsInteraction {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "client_user_id", nullable = false, length = 80)
    private String clientUserId;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "news_id", nullable = false)
    private News news;

    @Column(name = "interaction_type", nullable = false, length = 30)
    private String interactionType;

    @Column(nullable = false)
    @Builder.Default
    private Integer weight = 1;

    @CreatedDate
    @Column(updatable = false)
    private LocalDateTime createdAt;

    @LastModifiedDate
    private LocalDateTime updatedAt;

    public void refreshWeight(int weight) {
        this.weight = Math.max(this.weight, weight);
    }
}
