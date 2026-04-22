# ============================================================
# wallet_analyzer.py - 전자지갑 우회 접근 탐지 분석기
# ============================================================
# 전자지갑 관련 기능에 접근했지만 그 직전에 정상적인
# 전자지갑 생성/등록 절차가 없는 케이스를 찾습니다.
#
# 탐지 키워드:
#   전자지갑, ewallet, wallet, digitalWallet (대소문자 무관)
#
# 정상 흐름:
#   [전자지갑 생성/등록] → [전자지갑 조회/사용]
#
# 이상 케이스:
#   생성/등록 로그 없이 바로 조회/사용 로그가 나타남
# ============================================================

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import List, Optional

from models.log_entry import LogEntry, WalletAnomalyRecord


# 전자지갑 관련 키워드 목록 (이 중 하나라도 포함되면 관련 로그로 봄)
_WALLET_KEYWORDS = [
    "전자지갑", "ewallet", "wallet", "digitalwallet", "e-wallet",
]

# 전자지갑 생성/등록 키워드 (이게 있으면 정상 선행 로그로 봄)
_WALLET_CREATE_KEYWORDS = [
    "생성", "등록", "create", "register", "insert", "save", "신규",
]

# 전자지갑 접근/사용 키워드 (선행 로그 없이 이것만 있으면 이상)
_WALLET_ACCESS_KEYWORDS = [
    "조회", "사용", "access", "get", "query", "select", "use", "apply",
    "결제", "payment", "charge",
]

# 정상 선행 행위를 인정하는 시간 범위 (분): 이 시간 안에 생성이 있었으면 정상
_PRECEDING_WINDOW_MINUTES = 30


class WalletAnalyzer:
    """
    전자지갑 우회 접근을 탐지하는 분석기입니다.

    동작 원리:
        1. 전자지갑 관련 키워드를 포함한 로그를 모두 찾습니다.
        2. 각 접근 로그 직전 N분 이내에 생성/등록 로그가 있었는지 확인합니다.
        3. 생성/등록 없이 바로 접근하면 이상으로 기록합니다.
    """

    def __init__(
        self,
        preceding_window_minutes: int = _PRECEDING_WINDOW_MINUTES,
    ) -> None:
        """
        분석기를 초기화합니다.

        매개변수:
            preceding_window_minutes: 정상 선행 행위를 인정하는 시간 범위 (분).
                                      기본값 30분
        """
        self.preceding_window = timedelta(minutes=preceding_window_minutes)

    def analyze(self, entries: List[LogEntry]) -> List[WalletAnomalyRecord]:
        """
        로그 엔트리 목록에서 전자지갑 우회 접근을 탐지합니다.

        매개변수:
            entries: 파싱된 LogEntry 객체 목록

        반환:
            WalletAnomalyRecord 목록 (발생 시각 순서로 정렬)
        """
        if not entries:
            return []

        # 전자지갑 관련 로그만 필터링합니다
        wallet_entries = [e for e in entries if self._is_wallet_related(e.message)]

        if not wallet_entries:
            return []

        # 시간순 정렬
        wallet_entries.sort(key=lambda e: e.timestamp)

        # 생성/등록 로그의 시각을 추적합니다 (정상 선행 기록)
        # 리스트에 시각을 쌓고, 오래된 것은 제거합니다
        create_timestamps: List[datetime] = []

        results: List[WalletAnomalyRecord] = []

        for entry in wallet_entries:
            msg_lower = entry.message.lower()

            if self._is_wallet_create(msg_lower):
                # 생성/등록 로그: 타임스탬프를 기록합니다
                create_timestamps.append(entry.timestamp)
                # 오래된 생성 기록은 제거합니다 (윈도우 밖)
                cutoff = entry.timestamp - self.preceding_window
                create_timestamps = [t for t in create_timestamps if t >= cutoff]

            elif self._is_wallet_access(msg_lower):
                # 접근/사용 로그: 직전에 생성 기록이 있는지 확인합니다
                cutoff = entry.timestamp - self.preceding_window
                recent_creates = [t for t in create_timestamps if t >= cutoff]

                if not recent_creates:
                    # 선행 생성 기록 없음 → 이상으로 기록
                    class_name = entry.source_class or entry.file_name or "알수없음"
                    user_id    = self._extract_user_id(entry.message) or "알수없음"

                    results.append(WalletAnomalyRecord(
                        user_id      = user_id,
                        access_time  = entry.timestamp,
                        access_class = class_name,
                        anomaly_desc = (
                            f"전자지갑 접근/사용 로그 발생 ({entry.timestamp.strftime('%H:%M:%S')}) "
                            f"직전 {_PRECEDING_WINDOW_MINUTES}분 이내에 생성/등록 로그 없음"
                        ),
                        raw_log      = entry.raw_line[:300],
                    ))

        return results

    @staticmethod
    def _is_wallet_related(message: str) -> bool:
        """
        메시지가 전자지갑 관련 내용인지 확인합니다.
        키워드 목록 중 하나라도 포함되면 True를 반환합니다.
        """
        msg_lower = message.lower()
        return any(kw in msg_lower for kw in _WALLET_KEYWORDS)

    @staticmethod
    def _is_wallet_create(msg_lower: str) -> bool:
        """
        전자지갑 관련 메시지가 생성/등록 행위인지 확인합니다.
        """
        return any(kw in msg_lower for kw in _WALLET_CREATE_KEYWORDS)

    @staticmethod
    def _is_wallet_access(msg_lower: str) -> bool:
        """
        전자지갑 관련 메시지가 접근/사용 행위인지 확인합니다.
        """
        return any(kw in msg_lower for kw in _WALLET_ACCESS_KEYWORDS)

    @staticmethod
    def _extract_user_id(message: str) -> Optional[str]:
        """
        메시지에서 사용자 ID를 추출합니다.
        여러 패턴을 시도하고 첫 번째 매칭 값을 반환합니다.
        """
        patterns = [
            re.compile(r'userId[=:\s]+([A-Za-z0-9_@.\-]+)', re.IGNORECASE),
            re.compile(r'user[=:\s]+([A-Za-z0-9_@.\-]+)',   re.IGNORECASE),
            re.compile(r'id[=:\s]+([A-Za-z0-9_@.\-]{3,})',  re.IGNORECASE),
        ]
        for pattern in patterns:
            match = pattern.search(message)
            if match:
                val = match.group(1)
                if len(val) >= 3 and not val.isdigit():
                    return val
        return None


# ============================================================
# application_flow_analyzer.py 기능도 이 파일에 통합
# (원서접수 흐름 이상 탐지)
# ============================================================

# 원서접수 관련 키워드
_APP_FLOW_KEYWORDS = [
    "rcv", "원서접수", "자격증", "접수", "application",
    "certificate", "exam", "시험", "신청",
]

# 원서접수 정상 완료를 나타내는 키워드
_APP_FLOW_SUCCESS = [
    "완료", "success", "저장 확인", "종료", "처리완료", "정상",
]

# 원서접수 오류를 나타내는 키워드
_APP_FLOW_ERROR = [
    "실패", "error", "fail", "오류", "exception", "중단", "비정상",
    "롤백", "rollback", "timeout",
]

from models.log_entry import ApplicationFlowRecord


class ApplicationFlowAnalyzer:
    """
    자격증 원서접수 관련 로그의 흐름 이상을 탐지하는 분석기입니다.

    동작 원리:
        1. 원서접수 관련 키워드가 있는 로그를 모두 찾습니다.
        2. 오류/실패 키워드가 포함된 경우를 이상으로 기록합니다.
        3. ERROR/FATAL 레벨의 원서접수 로그도 이상으로 기록합니다.
    """

    def analyze(self, entries: List[LogEntry]) -> List[ApplicationFlowRecord]:
        """
        로그 엔트리 목록에서 원서접수 흐름 이상을 분석합니다.

        매개변수:
            entries: 파싱된 LogEntry 객체 목록

        반환:
            ApplicationFlowRecord 목록 (발생 시각 순서로 정렬)
        """
        if not entries:
            return []

        results: List[ApplicationFlowRecord] = []

        for entry in entries:
            msg_lower = entry.message.lower()

            # 원서접수 관련 로그인지 확인
            if not any(kw in msg_lower for kw in _APP_FLOW_KEYWORDS):
                continue

            # 오류 키워드가 있거나 ERROR/FATAL 레벨이면 이상
            has_error_keyword = any(kw in msg_lower for kw in _APP_FLOW_ERROR)
            is_error_level    = entry.is_error()

            if has_error_keyword or is_error_level:
                class_name = entry.source_class or entry.file_name or "알수없음"

                # 이상 내용 설명 생성
                if is_error_level and has_error_keyword:
                    desc = f"[{entry.level.value}] 원서접수 중 오류 발생 - 오류 키워드 및 에러 레벨 동시 탐지"
                elif is_error_level:
                    desc = f"[{entry.level.value}] 원서접수 관련 에러 레벨 로그 발생"
                else:
                    # 어떤 오류 키워드가 발견됐는지 알려줍니다
                    found = [kw for kw in _APP_FLOW_ERROR if kw in msg_lower]
                    desc = f"원서접수 흐름 이상 - 오류 키워드 발견: {', '.join(found)}"

                results.append(ApplicationFlowRecord(
                    occurred_at   = entry.timestamp,
                    related_class = class_name,
                    anomaly_desc  = desc,
                    raw_log       = entry.raw_line[:300],
                ))

        # 발생 시각 순서로 정렬
        results.sort(key=lambda r: r.occurred_at)
        return results
