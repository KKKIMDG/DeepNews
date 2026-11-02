"""Load pure modules by file path so DB/model initialization never runs."""
from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1] / 'backend/domains'


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # dataclasses resolve annotations through sys.modules
    spec.loader.exec_module(module)
    return module


ranking = load('personalization_ranking', 'personalization/ranking.py')
security = load('auth_security', 'auth/security.py')
NOW = datetime(2026, 10, 30, tzinfo=timezone.utc)


def candidate(news_id, keywords, days_old=3, ad=None):
    # Titles without bigrams keep title de-duplication out of unrelated tests.
    return ranking.Candidate(news_id, f'#{news_id}', f'https://news.example/{news_id}',
                             NOW - timedelta(days=days_old), ad, keywords)


def rank(candidates, current=None, profile=None, include=(), exclude=(), threshold=0.8, limit=5):
    return ranking.rank_candidates(candidates, {}, current, profile or {}, set(include), set(exclude),
                                   threshold, NOW, limit)


class RankingTests(unittest.TestCase):
    def test_related_article_beats_unrelated(self):
        result = rank([candidate(1, {'반도체': 3, '수출': 2}), candidate(2, {'야구': 4})],
                      current={'반도체': 5, '수출': 1})
        self.assertEqual([r.candidate.news_id for r in result], [1])
        self.assertIn("'반도체' 키워드 공통", result[0].reasons)

    def test_profile_breaks_tie_between_equally_related_articles(self):
        candidates = [candidate(1, {'AI': 2, '반도체': 2}), candidate(2, {'AI': 2, '야구': 2})]
        profile = {'야구': 1.0}
        result = rank(candidates, current={'AI': 3}, profile=profile)
        self.assertEqual(result[0].candidate.news_id, 2)
        self.assertIn("관심사 '야구'", result[0].reasons)

    def test_excluded_keyword_and_ad_threshold_filter(self):
        result = rank([candidate(1, {'AI': 2, '코인': 1}), candidate(2, {'AI': 2}, ad=0.95),
                       candidate(3, {'AI': 1}, ad=0.3)], current={'AI': 2}, exclude={'코인'})
        self.assertEqual([r.candidate.news_id for r in result], [3])

    def test_threshold_one_disables_ad_filter(self):
        result = rank([candidate(1, {'AI': 2}, ad=0.99)], current={'AI': 1}, threshold=1.0)
        self.assertEqual(len(result), 1)

    def test_include_keyword_bonus_and_reason(self):
        # build_profile always pins manual interests into the profile, as the service does.
        result = rank([candidate(1, {'AI': 1}), candidate(2, {'AI': 1, '로봇': 1})],
                      current={'AI': 1}, profile={'로봇': 1.0}, include={'로봇'})
        self.assertEqual(result[0].candidate.news_id, 2)
        self.assertEqual(result[0].reasons[0], "관심 키워드 '로봇'")

    def test_near_duplicates_are_collapsed(self):
        same = {'AI': 3, '반도체': 2, '수출': 1}
        result = rank([candidate(1, same), candidate(2, dict(same)), candidate(3, {'AI': 1, '정책': 3})],
                      current={'AI': 2})
        self.assertEqual(len(result), 2)

    def test_same_story_from_other_outlets_is_collapsed_by_title(self):
        titles = ["[단독] 'AI 안경' 쓰고 국가자격증 시험 본 20대 수험생 송치",
                  'AI 스마트안경 쓰고 국가자격증 시험 본 20대 송치',
                  '전세계 웹사이트에 해킹 비상…AI가 치명적 보안결함 발견(종합)']
        keywords = [{'안경': 2, '시험': 2}, {'스마트': 1, '수험생': 2}, {'해킹': 3, '보안': 2}]
        candidates = [ranking.Candidate(i, t, f'https://news.example/{i}', NOW, None, k)
                      for i, (t, k) in enumerate(zip(titles, keywords), start=1)]
        result = rank(candidates)  # cold start keeps every candidate eligible
        self.assertEqual(sorted(r.candidate.news_id for r in result), [2, 3])  # 1 is a rewrite of 2

    def test_other_outlets_take_on_a_seen_story_is_skipped(self):
        seen = ['AI 안경 쓰고 국가자격시험 본 20대…업무방해 등 혐의 송치']
        candidates = [ranking.Candidate(1, 'AI 안경에 "문제 풀어달라" 입력…자격증 시험 본 20대 송치',
                                        'https://news.example/1', NOW, None, {'안경': 2}),
                      ranking.Candidate(2, '안경 렌즈 시장 성장세', 'https://news.example/2', NOW, None, {'안경': 2})]
        result = ranking.rank_candidates(candidates, {}, {'안경': 1}, {}, set(), set(), 0.8, NOW, 5,
                                         seen_titles=seen)
        self.assertEqual([r.candidate.news_id for r in result], [2])

    def test_cold_start_returns_freshest(self):
        result = rank([candidate(1, {'AI': 1}, days_old=10), candidate(2, {}, days_old=0.2)])
        self.assertEqual([r.candidate.news_id for r in result], [2, 1])
        self.assertIn('최신 기사', result[0].reasons)

    def test_profile_decays_and_pins_manual_interests(self):
        history = [ranking.HistoryEntry({'오래된': 5}, 1, NOW - timedelta(days=60)),
                   ranking.HistoryEntry({'최근': 5}, 1, NOW)]
        profile = ranking.build_profile(history, {}, {'수동'}, {'최근'}, NOW)
        self.assertNotIn('최근', profile)
        self.assertEqual(profile['수동'], 1.0)
        self.assertLess(profile['오래된'], 1.0)

    def test_repeated_reads_weigh_more(self):
        history = [ranking.HistoryEntry({'A': 1}, 5, NOW), ranking.HistoryEntry({'B': 1}, 1, NOW)]
        profile = ranking.build_profile(history, {}, set(), set(), NOW)
        self.assertGreater(profile['A'], profile['B'])



class InterestTopicTests(unittest.TestCase):
    def test_topic_strength_fades_to_floor(self):
        self.assertEqual(ranking.topic_strength(0), 1.0)
        self.assertAlmostEqual(ranking.topic_strength(10), 0.5)
        self.assertEqual(ranking.topic_strength(500), ranking.TOPIC_STRENGTH_FLOOR)

    def test_topic_terms_prefer_distinctive_words(self):
        rows = [('스포츠', '감독', 40, 45), ('스포츠', '대통령', 40, 900), ('스포츠', '000원', 40, 41),
                ('스포츠', '홈런', 2, 2), ('스포츠', '감독을', 5, 5), ('미분류', '기타', 9, 9)]
        terms = ranking.topic_terms(rows, {'스포츠': 100, '미분류': 9}, 1000)
        self.assertEqual(set(terms), {'스포츠'})
        self.assertEqual(terms['스포츠']['감독'], 1.0)          # '감독을' pooled into it
        self.assertLess(terms['스포츠'].get('대통령', 0), 0.5)  # common everywhere
        self.assertNotIn('000원', terms['스포츠'])              # figures are boilerplate
        self.assertNotIn('홈런', terms['스포츠'])               # below TOPIC_MIN_ARTICLES

    def test_topics_blend_below_manual_interests(self):
        profile = ranking.build_profile([], {}, {'수동'}, {'제외'}, NOW,
                                        topic_profile={'감독': 1.0, '제외': 1.0, '수동': 0.5}, strength=1.0)
        self.assertEqual(profile['수동'], 1.0)
        self.assertAlmostEqual(profile['감독'], ranking.TOPIC_PROFILE_SCALE)
        self.assertNotIn('제외', profile)

    def test_topic_match_reaches_unrelated_article_with_reason(self):
        sports = ranking.Candidate(1, '#1', 'https://news.example/1', NOW, None, {'야구': 1}, '스포츠')
        other = ranking.Candidate(2, '#2', 'https://news.example/2', NOW, None, {'주가': 1}, '경제')
        result = ranking.rank_candidates([sports, other], {}, None, {'반도체': 1.0}, set(), set(), 0.8, NOW, 5,
                                         topics={'스포츠'}, strength=1.0)
        self.assertEqual([r.candidate.news_id for r in result], [1])
        self.assertIn("관심 분야 '스포츠'", result[0].reasons)

    def test_topic_bonus_shrinks_with_strength(self):
        sports = ranking.Candidate(1, '#1', 'https://news.example/1', NOW, None, {'야구': 1}, '스포츠')
        scores = [ranking.rank_candidates([sports], {}, None, {'야구': 1.0}, set(), set(), 0.8, NOW, 5,
                                          topics={'스포츠'}, strength=strength)[0].score
                  for strength in (1.0, 0.3)]
        self.assertAlmostEqual(scores[0] - scores[1], ranking.TOPIC_BONUS * 0.7, places=3)

    def test_feed_mixes_categories_but_related_list_keeps_relevance(self):
        def make(news_id, category, weight):
            return ranking.Candidate(news_id, f'#{news_id}', f'https://news.example/{news_id}', NOW, None,
                                     {f'a{news_id}': 5, f'b{news_id}': 5, '공통': weight}, category)
        candidates = [make(1, '경제', 4), make(2, '경제', 4), make(3, '경제', 4), make(4, '스포츠', 3)]
        feed = ranking.rank_candidates(candidates, {}, None, {'공통': 1.0}, set(), set(), 0.8, NOW, 3,
                                       topics={'경제', '스포츠'}, strength=1.0)
        self.assertIn(4, [r.candidate.news_id for r in feed])
        related = ranking.rank_candidates(candidates, {}, {'공통': 1}, {}, set(), set(), 0.8, NOW, 3)
        self.assertEqual([r.candidate.news_id for r in related], [3, 2, 1])

class KeywordNormalizationTests(unittest.TestCase):
    def test_strips_safe_particles_only(self):
        for raw, expected in [('안경을', '안경'), ('부정행위를', '부정행위'), ('취약점을', '취약점'),
                              ('서울에서', '서울'), ('마을', '마을'), ('평가', '평가'), ('회의', '회의'),
                              ('AI', 'AI'), ('앞바다', '앞바다'), ('캐나다', '캐나다'), ('플로리다', '플로리다'),
                              ('최다', '최다'), ('한옥마을', '한옥마을'), ('늦가을', '늦가을')]:
            self.assertEqual(ranking.normalize_term(raw), expected, raw)

    def test_drops_predicates_and_generic_terms(self):
        for raw in ['있다', '했습니다', '말했다', '꼽는다', '넘겨졌습니다', '없다', '한다', '것으로', '우리', '를', '가']:
            self.assertIsNone(ranking.normalize_term(raw), raw)

    def test_variants_merge_counts(self):
        self.assertEqual(ranking.normalize_keywords({'안경': 2, '안경을': 1, '있다': 5}), {'안경': 3})


class SecurityTests(unittest.TestCase):
    def test_password_round_trip(self):
        stored = security.hash_password('correct horse')
        self.assertTrue(security.verify_password('correct horse', stored))
        self.assertFalse(security.verify_password('wrong', stored))
        self.assertNotEqual(stored, security.hash_password('correct horse'))  # salted

    def test_malformed_hash_is_rejected(self):
        self.assertFalse(security.verify_password('x', 'not-a-hash'))
        self.assertFalse(security.verify_password('x', 'bcrypt$1$2$3$AA==$AA=='))

    def test_session_token_is_stored_as_digest(self):
        token = security.new_session_token()
        self.assertEqual(len(security.hash_session_token(token)), 64)
        self.assertNotEqual(security.hash_session_token(token), token)


if __name__ == '__main__':
    unittest.main()
