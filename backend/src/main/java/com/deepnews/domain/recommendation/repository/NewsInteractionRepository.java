package com.deepnews.domain.recommendation.repository;

import com.deepnews.domain.recommendation.entity.NewsInteraction;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.List;
import java.util.Optional;

public interface NewsInteractionRepository extends JpaRepository<NewsInteraction, Long> {

    @Query("""
            select ni
            from NewsInteraction ni
            where ni.clientUserId = :clientUserId
                and ni.news.id = :newsId
                and ni.interactionType = :interactionType
            """)
    Optional<NewsInteraction> findExistingInteraction(
            @Param("clientUserId") String clientUserId,
            @Param("newsId") Long newsId,
            @Param("interactionType") String interactionType
    );

    @Query(value = """
            select
                n.id,
                n.title,
                n.url,
                (
                    coalesce(sum(i2.weight), 0)
                    + case when n.created_at >= now() - interval '2 days' then 1.5 else 0 end
                    + case when na.ad_probability >= 0 and na.ad_probability < 0.4 then 1 else 0 end
                ) as score
            from news_interaction i1
            join news_interaction i2
                on i2.client_user_id = i1.client_user_id
                and i2.news_id <> :newsId
            join news n on n.id = i2.news_id
            left join news_analysis na on na.news_id = n.id
            where i1.news_id = :newsId
                and (:clientUserId is null or i2.client_user_id <> :clientUserId)
                and (
                    :clientUserId is null
                    or not exists (
                        select 1
                        from news_interaction seen
                        where seen.client_user_id = :clientUserId
                            and seen.news_id = n.id
                    )
                )
            group by n.id, n.title, n.url, n.created_at, na.ad_probability
            order by score desc, max(i2.updated_at) desc nulls last, n.id desc
            limit :limit
            """, nativeQuery = true)
    List<Object[]> findCollaborativeRecommendations(
            @Param("newsId") Long newsId,
            @Param("clientUserId") String clientUserId,
            @Param("limit") int limit
    );
}
