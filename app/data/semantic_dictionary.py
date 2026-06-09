# Layer 3/4용: 키워드 → 의미태그 → 마케팅 분류
from dataclasses import dataclass

@dataclass
class SemanticTag:
    category: str   # 마케팅 대분류 (음식/맛/장소/서비스/분위기/미분류)
    property: str   # 의미 태그 (세부 속성)

SEMANTIC_DICTIONARY: dict[str, SemanticTag] = {

    # ── 맛: 일반맛 ───────────────────────────────────
    "맛있다":   SemanticTag("맛", "일반맛"),
    "맛":       SemanticTag("맛", "일반맛"),

    # ── 맛: 식감/풍미 ────────────────────────────────
    "육즙":     SemanticTag("맛", "식감/풍미"),
    "바삭":     SemanticTag("맛", "식감/풍미"),
    "촉촉":     SemanticTag("맛", "식감/풍미"),
    "쫄깃":     SemanticTag("맛", "식감/풍미"),
    "담백":     SemanticTag("맛", "식감/풍미"),
    "고소":     SemanticTag("맛", "식감/풍미"),
    "진하다":   SemanticTag("맛", "식감/풍미"),
    "꾸덕":     SemanticTag("맛", "식감/풍미"),
    "산미":     SemanticTag("맛", "식감/풍미"),
    "달달":     SemanticTag("맛", "식감/풍미"),
    "짭조름":   SemanticTag("맛", "식감/풍미"),
    "매콤":     SemanticTag("맛", "식감/풍미"),
    "부드럽다": SemanticTag("맛", "식감/풍미"),
    "쫀득":     SemanticTag("맛", "식감/풍미"),

    # ── 맛: 온도 ─────────────────────────────────────
    "뜨겁다":   SemanticTag("맛", "온도"),
    "따뜻하다": SemanticTag("맛", "온도"),
    "차갑다":   SemanticTag("맛", "온도"),
    "시원하다": SemanticTag("맛", "온도"),

    # ── 맛: 양 ───────────────────────────────────────
    "양많음":   SemanticTag("맛", "양"),
    "양":       SemanticTag("맛", "양"),

    # ── 음식: 메뉴명/육류 ────────────────────────────
    "삼겹살":   SemanticTag("음식", "메뉴명/육류"),
    "목살":     SemanticTag("음식", "메뉴명/육류"),
    "갈비":     SemanticTag("음식", "메뉴명/육류"),
    "갈비살":   SemanticTag("음식", "메뉴명/육류"),
    "스테이크": SemanticTag("음식", "메뉴명/육류"),
    "소고기":   SemanticTag("음식", "메뉴명/육류"),
    "돼지고기": SemanticTag("음식", "메뉴명/육류"),
    "닭갈비":   SemanticTag("음식", "메뉴명/육류"),
    "치킨":     SemanticTag("음식", "메뉴명/육류"),
    "족발":     SemanticTag("음식", "메뉴명/육류"),
    "보쌈":     SemanticTag("음식", "메뉴명/육류"),
    "차돌":     SemanticTag("음식", "메뉴명/육류"),
    "한우":     SemanticTag("음식", "메뉴명/육류"),
    "등심":     SemanticTag("음식", "메뉴명/육류"),
    "항정살":   SemanticTag("음식", "메뉴명/육류"),
    "부채살":   SemanticTag("음식", "메뉴명/육류"),
    "꽃살":     SemanticTag("음식", "메뉴명/육류"),
    "수육":     SemanticTag("음식", "메뉴명/육류"),
    "갈비찜":   SemanticTag("음식", "메뉴명/육류"),

    # ── 음식: 메뉴명/해산물 ──────────────────────────
    "회":       SemanticTag("음식", "메뉴명/해산물"),
    "초밥":     SemanticTag("음식", "메뉴명/해산물"),
    "연어":     SemanticTag("음식", "메뉴명/해산물"),
    "새우":     SemanticTag("음식", "메뉴명/해산물"),
    "랍스터":   SemanticTag("음식", "메뉴명/해산물"),
    "굴":       SemanticTag("음식", "메뉴명/해산물"),
    "꽃게":     SemanticTag("음식", "메뉴명/해산물"),
    "해물":     SemanticTag("음식", "메뉴명/해산물"),
    "해산물":   SemanticTag("음식", "메뉴명/해산물"),
    "생선":     SemanticTag("음식", "메뉴명/해산물"),
    "명란":     SemanticTag("음식", "메뉴명/해산물"),
    "전복":     SemanticTag("음식", "메뉴명/해산물"),
    "문어":     SemanticTag("음식", "메뉴명/해산물"),
    "오징어":   SemanticTag("음식", "메뉴명/해산물"),
    "낙지":     SemanticTag("음식", "메뉴명/해산물"),
    "조개":     SemanticTag("음식", "메뉴명/해산물"),
    "광어":     SemanticTag("음식", "메뉴명/해산물"),
    "우럭":     SemanticTag("음식", "메뉴명/해산물"),

    # ── 음식: 메뉴명/한식 ────────────────────────────
    "구이":     SemanticTag("음식", "메뉴명/한식"),
    "화덕":     SemanticTag("음식", "메뉴명/한식"),
    "반찬":     SemanticTag("음식", "메뉴명/한식"),
    "묵은지":   SemanticTag("음식", "메뉴명/한식"),
    "깍두기":   SemanticTag("음식", "메뉴명/한식"),
    "김치":     SemanticTag("음식", "메뉴명/한식"),
    "감자전":   SemanticTag("음식", "메뉴명/한식"),
    "파전":     SemanticTag("음식", "메뉴명/한식"),
    "잡채":     SemanticTag("음식", "메뉴명/한식"),
    "불고기":   SemanticTag("음식", "메뉴명/한식"),
    "제육볶음": SemanticTag("음식", "메뉴명/한식"),
    "닭볶음탕": SemanticTag("음식", "메뉴명/한식"),
    "찜닭":     SemanticTag("음식", "메뉴명/한식"),
    "두루치기": SemanticTag("음식", "메뉴명/한식"),
    "장어":     SemanticTag("음식", "메뉴명/한식"),
    "순대":     SemanticTag("음식", "메뉴명/한식"),
    "떡볶이":   SemanticTag("음식", "메뉴명/한식"),
    "꼬치":     SemanticTag("음식", "메뉴명/한식"),

    # ── 음식: 이용방식 ────────────────────────────────
    "혼밥":     SemanticTag("음식", "이용방식"),
    "혼술":     SemanticTag("음식", "이용방식"),

    # ── 음식: 메뉴명/면류 ────────────────────────────
    "파스타":       SemanticTag("음식", "메뉴명/면류"),
    "알리오올리오": SemanticTag("음식", "메뉴명/면류"),
    "까르보나라":   SemanticTag("음식", "메뉴명/면류"),
    "라멘":         SemanticTag("음식", "메뉴명/면류"),
    "라면":         SemanticTag("음식", "메뉴명/면류"),
    "우동":         SemanticTag("음식", "메뉴명/면류"),
    "냉면":         SemanticTag("음식", "메뉴명/면류"),
    "국수":         SemanticTag("음식", "메뉴명/면류"),
    "쌀국수":       SemanticTag("음식", "메뉴명/면류"),
    "짜장면":       SemanticTag("음식", "메뉴명/면류"),
    "짬뽕":         SemanticTag("음식", "메뉴명/면류"),
    "소바":         SemanticTag("음식", "메뉴명/면류"),

    # ── 음식: 메뉴명/밥류 ────────────────────────────
    "비빔밥":     SemanticTag("음식", "메뉴명/밥류"),
    "볶음밥":     SemanticTag("음식", "메뉴명/밥류"),
    "덮밥":       SemanticTag("음식", "메뉴명/밥류"),
    "솥밥":       SemanticTag("음식", "메뉴명/밥류"),
    "돌솥밥":     SemanticTag("음식", "메뉴명/밥류"),
    "오므라이스": SemanticTag("음식", "메뉴명/밥류"),
    "카레":       SemanticTag("음식", "메뉴명/밥류"),
    "리조또":     SemanticTag("음식", "메뉴명/밥류"),

    # ── 음식: 메뉴명/국찌개 ──────────────────────────
    "된장찌개":   SemanticTag("음식", "메뉴명/국찌개"),
    "김치찌개":   SemanticTag("음식", "메뉴명/국찌개"),
    "순두부찌개": SemanticTag("음식", "메뉴명/국찌개"),
    "부대찌개":   SemanticTag("음식", "메뉴명/국찌개"),
    "설렁탕":     SemanticTag("음식", "메뉴명/국찌개"),
    "곰탕":       SemanticTag("음식", "메뉴명/국찌개"),
    "삼계탕":     SemanticTag("음식", "메뉴명/국찌개"),
    "순대국":     SemanticTag("음식", "메뉴명/국찌개"),
    "해장국":     SemanticTag("음식", "메뉴명/국찌개"),
    "갈비탕":     SemanticTag("음식", "메뉴명/국찌개"),

    # ── 음식: 메뉴명/음료 ────────────────────────────
    "아메리카노": SemanticTag("음식", "메뉴명/음료"),
    "라떼":       SemanticTag("음식", "메뉴명/음료"),
    "카페라떼":   SemanticTag("음식", "메뉴명/음료"),
    "에스프레소": SemanticTag("음식", "메뉴명/음료"),
    "카푸치노":   SemanticTag("음식", "메뉴명/음료"),
    "플랫화이트": SemanticTag("음식", "메뉴명/음료"),
    "콜드브루":   SemanticTag("음식", "메뉴명/음료"),
    "아이스티":   SemanticTag("음식", "메뉴명/음료"),
    "스무디":     SemanticTag("음식", "메뉴명/음료"),
    "에이드":     SemanticTag("음식", "메뉴명/음료"),
    "주스":       SemanticTag("음식", "메뉴명/음료"),
    "맥주":       SemanticTag("음식", "메뉴명/음료"),
    "와인":       SemanticTag("음식", "메뉴명/음료"),
    "막걸리":     SemanticTag("음식", "메뉴명/음료"),
    "소주":       SemanticTag("음식", "메뉴명/음료"),

    # ── 음식: 메뉴명/디저트 ──────────────────────────
    "케이크":     SemanticTag("음식", "메뉴명/디저트"),
    "마카롱":     SemanticTag("음식", "메뉴명/디저트"),
    "크로플":     SemanticTag("음식", "메뉴명/디저트"),
    "크루아상":   SemanticTag("음식", "메뉴명/디저트"),
    "티라미수":   SemanticTag("음식", "메뉴명/디저트"),
    "아이스크림": SemanticTag("음식", "메뉴명/디저트"),
    "빙수":       SemanticTag("음식", "메뉴명/디저트"),
    "와플":       SemanticTag("음식", "메뉴명/디저트"),
    "팬케이크":   SemanticTag("음식", "메뉴명/디저트"),
    "타르트":     SemanticTag("음식", "메뉴명/디저트"),
    "브라우니":   SemanticTag("음식", "메뉴명/디저트"),
    "쿠키":       SemanticTag("음식", "메뉴명/디저트"),
    "스콘":       SemanticTag("음식", "메뉴명/디저트"),

    # ── 서비스: 친절도 ───────────────────────────────
    "친절":     SemanticTag("서비스", "친절도"),
    "응대":     SemanticTag("서비스", "친절도"),
    "서비스":   SemanticTag("서비스", "친절도"),

    # ── 서비스: 속도 ─────────────────────────────────
    "빠름":     SemanticTag("서비스", "속도"),

    # ── 서비스: 전문성 ───────────────────────────────
    "설명잘함": SemanticTag("서비스", "전문성"),
    "전문적":   SemanticTag("서비스", "전문성"),
    "바리스타": SemanticTag("서비스", "전문성"),
    "소믈리에": SemanticTag("서비스", "전문성"),

    # ── 서비스: 편의 ─────────────────────────────────
    "리필가능": SemanticTag("서비스", "편의"),
    "포장가능": SemanticTag("서비스", "편의"),
    "배달가능": SemanticTag("서비스", "편의"),
    "예약가능": SemanticTag("서비스", "편의"),
    "단체가능": SemanticTag("서비스", "편의"),

    # ── 서비스: 혼잡도 ───────────────────────────────
    "웨이팅":   SemanticTag("서비스", "혼잡도"),
    "대기":     SemanticTag("서비스", "혼잡도"),
    "혼잡":     SemanticTag("서비스", "혼잡도"),

    # ── 서비스: 가성비 ───────────────────────────────
    "가성비":   SemanticTag("서비스", "가성비"),
    "저렴":     SemanticTag("서비스", "가성비"),
    "합리적":   SemanticTag("서비스", "가성비"),
    "혜자":     SemanticTag("서비스", "가성비"),

    # ── 분위기: 감성 ─────────────────────────────────
    "분위기":   SemanticTag("분위기", "감성"),
    "인테리어": SemanticTag("분위기", "감성"),
    "감성":     SemanticTag("분위기", "감성"),
    "아늑":     SemanticTag("분위기", "감성"),
    "힐링":     SemanticTag("분위기", "감성"),
    "포근":     SemanticTag("분위기", "감성"),
    "아기자기": SemanticTag("분위기", "감성"),

    # ── 분위기: 뷰 ───────────────────────────────────
    "뷰":       SemanticTag("분위기", "뷰"),
    "경치":     SemanticTag("분위기", "뷰"),
    "전망":     SemanticTag("분위기", "뷰"),
    "야경":     SemanticTag("분위기", "뷰"),

    # ── 분위기: 소음 ─────────────────────────────────
    "조용":     SemanticTag("분위기", "소음"),
    "한적":     SemanticTag("분위기", "소음"),

    # ── 장소: 청결 ───────────────────────────────────
    "청결":     SemanticTag("장소", "청결"),
    "위생":     SemanticTag("장소", "청결"),

    # ── 장소: 주차 ───────────────────────────────────
    "주차":     SemanticTag("장소", "편의/주차"),

    # ── 장소: 편의시설 ───────────────────────────────
    "화장실":   SemanticTag("장소", "편의/시설"),
    "와이파이": SemanticTag("장소", "편의/시설"),
    "콘센트":   SemanticTag("장소", "편의/시설"),
    "루프탑":   SemanticTag("장소", "편의/시설"),
    "테라스":   SemanticTag("장소", "편의/시설"),
    "좌석":     SemanticTag("장소", "편의/시설"),
    "단독룸":   SemanticTag("장소", "편의/시설"),
    "룸":       SemanticTag("장소", "편의/시설"),
    "노키즈":   SemanticTag("장소", "편의/시설"),
    "애견동반": SemanticTag("장소", "편의/시설"),

    # ── 장소: 공간 ───────────────────────────────────
    "넓다":     SemanticTag("장소", "공간"),
    "협소":     SemanticTag("장소", "공간"),

    # ── 장소: 위치 ───────────────────────────────────
    "접근성":   SemanticTag("장소", "위치"),
    "역근처":   SemanticTag("장소", "위치"),
    "대중교통": SemanticTag("장소", "위치"),

    # ── 미분류 ───────────────────────────────────────
    "재방문":   SemanticTag("미분류", "충성도"),
    "단골":     SemanticTag("미분류", "충성도"),
    "특별한날": SemanticTag("미분류", "특별한날"),
    "데이트":   SemanticTag("미분류", "특별한날"),
    "기념일":   SemanticTag("미분류", "특별한날"),
    "생일":     SemanticTag("미분류", "특별한날"),
    "접대":     SemanticTag("미분류", "특별한날"),
    "모임":     SemanticTag("미분류", "특별한날"),
}

def get_semantic_tag(keyword: str) -> SemanticTag | None:
    return SEMANTIC_DICTIONARY.get(keyword, None)