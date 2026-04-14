package com.deepnews.domain.keyword.entity;

import jakarta.persistence.*;
import lombok.*;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.jpa.domain.support.AuditingEntityListener;
import java.time.ZonedDateTime;

@Entity
@Table(name = "keyword")
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
@AllArgsConstructor
@Builder
@EntityListeners(AuditingEntityListener.class)
public class Keyword {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true, length = 50)
    private String word;

    @Column(nullable = false)
    @Builder.Default
    private Integer totalCount = 0;

    @Column(nullable = false)
    @Builder.Default
    private Integer articleCount = 0;

    @CreatedDate
    @Column(updatable = false)
    private ZonedDateTime createdAt;

    @LastModifiedDate
    private ZonedDateTime updatedAt;

    public void updateStatistics(int newCount) {
        this.totalCount += newCount;
        this.articleCount += 1;
    }
}
