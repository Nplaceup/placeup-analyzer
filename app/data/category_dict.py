# category_dict.py — 하위 호환용 재익스포트 모듈
#
# ─ 변경 이력 ──────────────────────────────────────────────────────────────────
# v1: CATEGORY_DICT_BASE / INDUCEMENT_TEMPLATE / KEYWORD_BLOCKLIST 통합 관리
# v2: 역할 분리 완료
#     - KEYWORD_BLOCKLIST, THEMES_CATEGORY_MAP → blocklist.py
#     - 유도어 목록 (inducements)              → inducement_dict.py
#     - 키워드→카테고리 매핑                   → semantic_dictionary.py
#     - purpose 결정                           → category_mapper.py
#
# ─ 현재 역할 ─────────────────────────────────────────────────────────────────
# 이 파일을 import하는 레거시 코드(scorer, formatter 등)가 남아 있을 경우를
# 위해 유지. 신규 코드는 각 전담 모듈에서 직접 import할 것.
#
# CATEGORY_DICT (런타임 set 조회)는 STAGE 1a 블랙리스트 필터 적용 후
# 더 이상 category 분류에 사용되지 않음.
# category 분류는 semantic_dictionary.py의 get_semantic_tag()가 담당.

# 하위 호환 재익스포트
from app.data.blocklist import KEYWORD_BLOCKLIST, THEMES_CATEGORY_MAP  # noqa: F401

# ── FALLBACK ──────────────────────────────────────────────────────────────────
# keyword_formatter.py v1 레거시 참조용. 신규 코드에서는 사용하지 않음.
FALLBACK: dict = {"purpose": "marketing", "inducements": []}
