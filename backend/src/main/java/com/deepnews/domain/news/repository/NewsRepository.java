package com.deepnews.domain.news.repository;

import com.deepnews.domain.news.entity.News;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.Optional;

public interface NewsRepository extends JpaRepository<News, Long> {
    Optional<News> findByUrl(String url);
}
