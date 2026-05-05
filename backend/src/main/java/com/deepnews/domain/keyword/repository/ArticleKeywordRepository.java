package com.deepnews.domain.keyword.repository;

import com.deepnews.domain.keyword.entity.ArticleKeyword;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface ArticleKeywordRepository extends JpaRepository<ArticleKeyword, Long> {
    @Modifying
    @Query("delete from ArticleKeyword ak where ak.news.id = :newsId")
    void deleteByNewsId(@Param("newsId") Long newsId);
}
