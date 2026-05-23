from app.services.scoring.seo_scorer import SEOScorer
from app.services.scoring.seo_feedback import SEOFeedback

scorer = SEOScorer()

# ── 케이스 1: 이상적인 매장 (다 좋은 경우) ──────────────────────────
case1 = [
    {"keyword": "강남 카페", "keyword_purpose": "search", "category": "위치", "score": 0.9, "consistency_score": 0.8, "rank_no": 3, "is_opportunity": False, "competition_level": "낮음"},
    {"keyword": "강남 브런치", "keyword_purpose": "search", "category": "메뉴", "score": 0.8, "consistency_score": 0.7, "rank_no": 7, "is_opportunity": False, "competition_level": "낮음"},
    {"keyword": "조용한 카페", "keyword_purpose": "search", "category": "분위기", "score": 0.7, "consistency_score": 0.6, "rank_no": 9, "is_opportunity": True,  "competition_level": "낮음"},
    {"keyword": "노트북 카페", "keyword_purpose": "search", "category": "서비스", "score": 0.6, "consistency_score": 0.5, "rank_no": 2, "is_opportunity": False, "competition_level": "중간"},
    {"keyword": "분위기 좋은", "keyword_purpose": "description", "category": "분위기", "score": 0.5, "consistency_score": 0.4, "rank_no": None, "is_opportunity": True,  "competition_level": "낮음"},
]

# ── 케이스 2: rank_no 전부 None (③번 0점 확인용) ─────────────────────
case2 = [
    {"keyword": "강남 카페", "keyword_purpose": "search", "category": "위치", "score": 0.8, "consistency_score": 0.6, "rank_no": None, "is_opportunity": False, "competition_level": "낮음"},
    {"keyword": "브런치 맛집", "keyword_purpose": "search", "category": "메뉴", "score": 0.7, "consistency_score": 0.5, "rank_no": None, "is_opportunity": False, "competition_level": "중간"},
    {"keyword": "분위기 좋은", "keyword_purpose": "description", "category": "분위기", "score": 0.5, "consistency_score": 0.3, "rank_no": None, "is_opportunity": False, "competition_level": "높음"},
]

# ── 케이스 3: competition_level 전부 "낮음" (④번 만점 확인용) ─────────
case3 = [
    {"keyword": "강남 카페", "keyword_purpose": "search", "category": "위치", 
     "score": 0.5, "consistency_score": 0.4, "rank_no": None, 
     "is_opportunity": False, "competition_level": "중간"},  # "낮음" → "중간"
    {"keyword": "브런치 카페", "keyword_purpose": "description", "category": "메뉴", 
     "score": 0.4, "consistency_score": 0.3, "rank_no": None, 
     "is_opportunity": False, "competition_level": "중간"},  # "낮음" → "중간"
    {"keyword": "조용한 카페", "keyword_purpose": "description", "category": "분위기", 
     "score": 0.3, "consistency_score": 0.2, "rank_no": None, 
     "is_opportunity": False, "competition_level": "중간"},  # "낮음" → "중간"
]

# ── 케이스 4: 빈 리스트 ───────────────────────────────────────────────
case4 = []

# ── 출력 ──────────────────────────────────────────────────────────────
for i, case in enumerate([case1, case2, case3, case4], 1):
    result = scorer.calc_score(case)
    print(f"\n{'='*50}")
    print(f"케이스 {i}")
    print(f"{'='*50}")
    print(f"  총점   : {result['total']}점  {result['grade']}")
    b = result["breakdown"]
    print(f"  ① 키워드 최적화  : {b['keyword_optimization']} / 40")
    print(f"  ② 리뷰 품질      : {b['review_quality']} / 30")
    print(f"  ③ 검색 노출 현황 : {b['search_exposure']} / 20")
    print(f"  ④ 경쟁 포지셔닝  : {b['competition']} / 10")
    
# ── mock 리뷰 데이터 ──────────────────────────────────────────────────
mock_reviews = [
    {"id": 1, "body": "주차가 너무 불편해요. 자리가 없어서 힘들었어요."},
    {"id": 2, "body": "웨이팅이 길었지만 음식이 맛있어서 괜찮았어요."},
    {"id": 3, "body": "가격이 좀 비싸다 싶었는데 분위기는 좋았어요."},
    {"id": 4, "body": "너무 좋아요! 또 올게요."},
    {"id": 5, "body": "주차 공간이 부족해서 불편했어요."},
    {"id": 6, "body": "서비스가 불친절했어요. 실망했습니다."},
    {"id": 7, "body": "분위기 너무 좋고 음식도 맛있어요."},
    {"id": 8, "body": "웨이팅 없이 바로 들어갔어요. 좋았어요."},
    {"id": 9, "body": "가격 대비 양이 적어서 아쉬웠어요."},
    {"id": 10, "body": "친절하고 맛있어요. 강추!"},
]

feedback_gen = SEOFeedback()

print("\n" + "="*50)
print("피드백 테스트 (케이스 1 기준)")
print("="*50)

# 케이스 1 seo_result로 피드백 생성
result1 = scorer.calc_score(case1)
feedback1 = feedback_gen.generate(result1, mock_reviews)

print(f"\n  총평 : {feedback1['summary']}")
print(f"\n  [SEO 기반 피드백]")
for fb in feedback1['seo_feedback']:
    print(f"    · {fb}")
print(f"\n  [리뷰 기반 피드백]")
for fb in feedback1['review_feedback']:
    print(f"    · {fb}")