package com.deepnews.domain.keyword.repository;

import com.deepnews.domain.keyword.entity.ArticleKeyword;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ArticleKeywordRepository extends JpaRepository<ArticleKeyword, Long> {
}
