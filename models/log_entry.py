# ============================================================
# log_entry.py - 로그 한 줄을 담는 데이터 그릇(모델) 정의
# ============================================================
# dataclass를 사용하면 클래스를 더 간단하게 만들 수 있습니다.
# 마치 엑셀 행 하나처럼 각 로그 줄의 정보를 필드로 저장합니다.
# ============================================================

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


# ----- 로그 종류를 구분하는 열거형 -----
class LogFormat(Enum):
    """
    로그 파일에 섞여 있는 두 가지 형식을 구분하는 값입니다.
    JEUS_SYSTEM  : JEUS 미들웨어 자체가 남기는 시스템 로그
    APP_EGOV     : 전자정부 프레임워크 애플리케이션이 남기는 로그
    UNKNOWN      : 위 두 형식 모두 해당하지 않는 줄
    """
    JEUS_SYSTEM = "JEUS_SYSTEM"
    APP_EGOV    = "APP_EGOV"
    UNKNOWN     = "UNKNOWN"


# ----- 로그 레벨(심각도)을 구분하는 열거형 -----
class LogLevel(Enum):
    """
    로그의 심각도 단계입니다.
    DEBUG   : 개발용 상세 정보 (가장 낮은 단계)
    INFO    : 일반적인 정보
    WARN    : 주의가 필요한 상황
    ERROR   : 오류 발생
    FATAL   : 치명적 오류 (가장 높은 단계)
    UNKNOWN : 레벨 정보가 없는 로그
    """
    DEBUG   = "DEBUG"
    INFO    = "INFO"
    WARN    = "WARN"
    WARNING = "WARNING"
    ERROR   = "ERROR"
    FATAL   = "FATAL"
    UNKNOWN = "UNKNOWN"


# ----- 로그 한 줄의 모든 정보를 담는 데이터 클래스 -----
@dataclass
class LogEntry:
    """
    로그 파일에서 읽은 한 줄의 정보를 저장하는 그릇입니다.
    파싱(분석)이 끝난 뒤 이 객체 목록을 각 분석기로 넘깁니다.

    필드 설명:
        raw_line     : 원본 로그 줄 (가공 전 텍스트)
        timestamp    : 로그가 기록된 정확한 시각
        log_format   : JEUS 시스템 로그인지, 앱 로그인지
        level        : DEBUG / INFO / WARN / ERROR / FATAL
        source_class : 로그를 남긴 자바 클래스 이름 (앱 로그만 해당)
        line_number  : 자바 소스 코드의 줄 번호 (앱 로그만 해당)
        message      : 실제 로그 메시지 내용
        thread_id    : JEUS 스레드 번호
        container    : JEUS 컨테이너 이름 (예: container1-1)
        session_id   : JEUS 세션 ID
        file_name    : 이 로그가 들어있던 파일 이름
        line_no_in_file : 파일에서의 줄 번호 (디버깅용)
    """
    # 반드시 있어야 하는 필드
    raw_line:        str
    timestamp:       datetime
    log_format:      LogFormat
    message:         str

    # 있을 수도 있고 없을 수도 있는 필드 (Optional = 없으면 None)
    level:           LogLevel          = LogLevel.UNKNOWN
    source_class:    Optional[str]     = None
    line_number:     Optional[int]     = None
    thread_id:       Optional[str]     = None
    container:       Optional[str]     = None
    session_id:      Optional[str]     = None
    file_name:       Optional[str]     = None
    line_no_in_file: int               = 0

    def is_error(self) -> bool:
        """이 로그가 에러 또는 그 이상 심각도인지 확인합니다."""
        return self.level in (LogLevel.ERROR, LogLevel.FATAL)

    def is_warn_or_above(self) -> bool:
        """경고 이상 심각도인지 확인합니다."""
        return self.level in (LogLevel.WARN, LogLevel.WARNING,
                               LogLevel.ERROR, LogLevel.FATAL)

    def contains_keyword(self, keyword: str) -> bool:
        """
        메시지에 특정 단어가 포함되어 있는지 확인합니다.
        대소문자를 구분하지 않습니다.
        예) entry.contains_keyword("wallet") -> True/False
        """
        return keyword.lower() in self.message.lower()


# ----- 분석 결과를 담는 공통 기반 클래스 -----
@dataclass
class AnalysisResult:
    """
    각 분석기(Analyzer)가 반환하는 결과의 공통 기반입니다.
    모든 분석 결과는 이 클래스를 상속하거나 포함합니다.

    필드:
        anomaly_count : 발견된 이상현상 총 개수
        summary       : 한 줄 요약 문장
    """
    anomaly_count: int   = 0
    summary:       str   = ""


# ----- 요청 폭증 분석 결과 -----
@dataclass
class SpikeRecord:
    """
    요청이 갑자기 많아진 시간 구간 하나를 기록합니다.

    필드:
        window_start  : 시간 구간의 시작 시각
        window_label  : 화면에 보여줄 시간 구간 표시 (예: "14:01 ~ 14:02")
        request_count : 해당 구간의 요청 수
        increase_rate : 이전 구간 대비 증가율 (배수)
        window_type   : "1분", "5분", "1시간" 중 하나
    """
    window_start:  datetime
    window_label:  str
    request_count: int
    increase_rate: float
    window_type:   str


# ----- 에러 패턴 분석 결과 -----
@dataclass
class ErrorRecord:
    """
    특정 클래스에서 반복적으로 발생한 에러 패턴을 기록합니다.

    필드:
        source_class    : 에러가 난 자바 클래스 이름
        error_count     : 총 에러 발생 횟수
        first_occurred  : 가장 처음 발생한 시각
        last_occurred   : 가장 최근 발생한 시각
        sample_messages : 대표 에러 메시지 (최대 3개)
    """
    source_class:    str
    error_count:     int
    first_occurred:  datetime
    last_occurred:   datetime
    sample_messages: list[str] = field(default_factory=list)


# ----- 응답시간 지연 분석 결과 -----
@dataclass
class ResponseTimeRecord:
    """
    시작 로그와 종료 로그 쌍을 찾아 처리 시간을 계산한 결과입니다.

    필드:
        method_name   : 측정 대상 메서드(함수) 이름
        duration_ms   : 처리 소요 시간 (밀리초)
        start_time    : 처리 시작 시각
        end_time      : 처리 완료 시각
        start_log     : 시작 로그 원본
        end_log       : 종료 로그 원본
        is_slow       : 느린 처리로 판단되면 True (기준: 3000ms 초과)
    """
    method_name:  str
    duration_ms:  float
    start_time:   datetime
    end_time:     datetime
    start_log:    str
    end_log:      str
    is_slow:      bool = False


# ----- 비정상 접근 분석 결과 -----
@dataclass
class AbnormalAccessRecord:
    """
    단시간에 너무 많은 요청을 보낸 사용자/IP 정보를 기록합니다.

    필드:
        identifier    : 사용자 ID 또는 IP 주소
        request_count : 해당 시간 범위 안의 요청 횟수
        time_range_start : 집중 요청 시작 시각
        time_range_end   : 집중 요청 종료 시각
        sample_messages  : 대표 요청 메시지 (최대 5개)
    """
    identifier:        str
    request_count:     int
    time_range_start:  datetime
    time_range_end:    datetime
    sample_messages:   list[str] = field(default_factory=list)


# ----- 전자지갑 우회 접근 분석 결과 -----
@dataclass
class WalletAnomalyRecord:
    """
    전자지갑 관련 기능에 정상 절차 없이 접근한 케이스를 기록합니다.

    필드:
        user_id       : 의심 사용자 ID (로그에서 추출한 값)
        access_time   : 전자지갑 접근 시각
        access_class  : 접근한 클래스 또는 URL
        anomaly_desc  : 이상 내용 설명 (한국어)
        raw_log       : 원본 로그 줄
    """
    user_id:      str
    access_time:  datetime
    access_class: str
    anomaly_desc: str
    raw_log:      str


# ----- 원서접수 흐름 이상 분석 결과 -----
@dataclass
class ApplicationFlowRecord:
    """
    자격증 원서접수 처리 흐름이 비정상적으로 끊긴 케이스를 기록합니다.

    필드:
        occurred_at   : 이상 발생 시각
        related_class : 연관된 자바 클래스 이름
        anomaly_desc  : 이상 내용 설명 (한국어)
        raw_log       : 원본 로그 줄
    """
    occurred_at:   datetime
    related_class: str
    anomaly_desc:  str
    raw_log:       str
