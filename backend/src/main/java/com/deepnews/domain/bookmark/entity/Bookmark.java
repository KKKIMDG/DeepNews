package com.deepnews.domain.bookmark.entity;

import com.deepnews.domain.news.entity.News;
import com.deepnews.domain.user.entity.User;
import jakarta.persistence.*;
import lombok.*;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.jpa.domain.support.AuditingEntityListener;
import java.time.ZonedDateTime;

@Entity
@Table(
        name = "bookmarks",
        uniqueConstraints = {
                @UniqueConstraint(name = "unique_user_news_bookmark", columnNames = {"user_id", "news_id"})
        }
)
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
@AllArgsConstructor
@Builder
@EntityListeners(AuditingEntityListener.class)
public class Bookmark {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "user_id", nullable = false)
    private User user;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "news_id", nullable = false)
    private News news;

    @CreatedDate
    @Column(updatable = false)
    private ZonedDateTime createdAt;
}
