# 카테고리 단어 사전 및 유도어 템플릿 정의
# keyword_formatter.py 로직과 분리하여 독립적으로 관리
#
# ─ 구조 ──────────────────────────────────────────────────────────────────────
# 1. 정적 기본 사전 (CATEGORY_DICT_BASE): 하드코딩 최소 기준값
# 2. THEMES → 카테고리 매핑 (THEMES_CATEGORY_MAP): DB THEMES label 분류 규칙
# 3. build_category_dict(): DB 데이터로 기본 사전을 보강한 최종 dict 생성
# 4. CATEGORY_DICT: 런타임 사용 dict (DB 연결 실패 시 BASE로 폴백)


# ── 1. 정적 기본 사전 ─────────────────────────────────────────────────────────
# DB 연결 실패 또는 초기 개발 시 폴백으로 사용
CATEGORY_DICT_BASE: dict[str, set[str]] = {
    "음식": {
        "파스타", "스테이크", "피자", "커피", "라떼", "케이크", "샐러드",
        "리조또", "브런치", "음식", "메뉴", "디저트", "와인", "맥주",
        "칵테일", "버거", "샌드위치", "수프", "초밥", "라멘", "타코",
        "마카롱", "티라미수", "에스프레소", "아메리카노", "카푸치노",
        "한식", "중식", "일식", "양식", "분식", "채식", "비건"
    },
    "장소": {
        "루프탑", "테라스", "뷰", "창가", "야외", "전망", "위치", "주차",
        "공간", "좌석", "자리", "층", "건물", "골목", "거리", "광장",
    },
    "서비스": {
        "직원", "서비스", "사장님", "응대", "친절", "대기", "예약",
        "웨이터", "안내", "배달", "포장", "주문", "속도", "매너",
    },
    "분위기": {
        "인테리어", "감성", "분위기", "조용", "아늑", "힐링", "인스타",
        "조명", "음악", "소음", "데이트", "혼밥", "단체", "분위기있는",
    },
}

# ── 2. THEMES label → 카테고리 매핑 ──────────────────────────────────────────
# review_analysis 테이블의 THEMES label을 기존 카테고리로 분류
# 매핑 불가 label(만족도, 가격, 목적, 방역 등)은 None → 미분류 처리
THEMES_CATEGORY_MAP: dict[str, str | None] = {
    "맛":      "음식",
    "메뉴":    "음식",
    "음식량":  "음식",
    "위치":    "장소",
    "주차":    "장소",
    "서비스":  "서비스",
    "대기시간": "서비스",
    "예약":    "서비스",
    "배달":    "서비스",
    "분위기":  "분위기",
    "청결도":  "분위기",
    # 매핑 불가 → 미분류
    "만족도":  None,
    "가격":    None,
    "목적":    None,
    "방역":    None,
}

# ── 3. DB 보강 함수 ───────────────────────────────────────────────────────────
def build_category_dict() -> dict[str, set[str]]:
    """
    review_analysis 테이블 데이터로 CATEGORY_DICT_BASE를 보강하여 반환.
    - MENUS label → "음식" 카테고리에 추가
    - THEMES label → THEMES_CATEGORY_MAP 기준으로 해당 카테고리에 추가

    DB 연결 실패 시 CATEGORY_DICT_BASE 그대로 반환 (폴백).
    """
    import copy
    result = copy.deepcopy(CATEGORY_DICT_BASE)

    try:
        from app.db.repository import get_review_analysis_labels
        labels = get_review_analysis_labels()

        # MENUS → 전부 "음식"
        for label in labels.get("MENUS", []):
            result["음식"].add(label)

        # THEMES → 매핑 규칙 적용
        for label in labels.get("THEMES", []):
            category = THEMES_CATEGORY_MAP.get(label)
            if category:
                result[category].add(label)

    except Exception as e:
        print(f"[category_dict] DB 로드 실패, 기본 사전 사용: {e}")

    return result


# ── 4. 카테고리별 유도어 템플릿 ───────────────────────────────────────────────
# purpose:
#   "search"    → 유도어를 결합하여 검색 노출용 키워드 생성
#   "marketing" → 원본 그대로 마케팅 태그로 사용 (유도어 결합 불필요)
INDUCEMENT_TEMPLATE: dict[str, dict] = {
    "음식":   {"purpose": "search",    "inducements": ["맛집", "추천", "가성비", "현지인맛집",
                                                     "웨이팅", "후기좋은", "데이트", "혼밥"]},
    "장소":   {"purpose": "search",    "inducements": ["가볼만한곳", "추천", "핫플", "명소",
                                                     "데이트", "놀거리"]},
    "서비스": {"purpose": "marketing", "inducements": []},
    "분위기": {"purpose": "marketing", "inducements": []},
}

# 카테고리 미분류 키워드에 적용되는 기본값
FALLBACK: dict = {"purpose": "marketing", "inducements": []}

# ── 5. 런타임 dict (모듈 로드 시 한 번만 빌드) ───────────────────────────────
CATEGORY_DICT: dict[str, set[str]] = build_category_dict()
