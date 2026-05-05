package com.deepnews.domain.analysis.repository;

import com.deepnews.domain.analysis.entity.NewsAnalysis;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.Optional;

public interface NewsAnalysisRepository extends JpaRepository<NewsAnalysis, Long> {
    Optional<NewsAnalysis> findByNewsId(Long newsId);
}
