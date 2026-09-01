"""
용량 제한값 한곳에 모아둠. 나중에 정책 바뀌면 여기만 고치면 됨.
"""
MAX_WORD_LISTS_PER_TEACHER = 100   # 단어장(폴더) 개수
MAX_WORDS_PER_TEACHER = 5000       # 선생님 계정 전체 단어 개수 합
MAX_STUDENTS_PER_TEACHER = 100     # 학생 등록 인원
MAX_LOGO_DATA_URL_LENGTH = 700_000  # 학원 로고(base64 data URL) 최대 길이, 대략 원본 이미지 500KB 정도
