# ============================================================
# access_analyzer.py - 비정상 접근 패턴 분석기
# ============================================================
# 동일한 사용자 ID 또는 IP 주소가 단시간에 과도하게
# 요청을 보내는 경우를 탐지합니다.
#
# 탐지 방법:
#   로그 메시지에서 사용자 ID 패턴(userId=, user=, ip= 등)을
#   정규식으로 추출하고, 5분 내에 임계값 이상 요청하면 이상으로 판단합니다.
# ============================================================

from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from models.log_entry import AbnormalAccessRecord, LogEntry


# 로그 메시지에서 사용자 ID를 추출하는 정규식 패턴들
# 하나씩 시도해서 첫 번째로 매칭되는 값을 사용합니다
_USER_ID_PATTERNS = [
    re.compile(r'userId[=:\s]+([A-Za-z0-9_@.\-]+)', re.IGNORECASE),
    re.compile(r'user[=:\s]+([A-Za-z0-9_@.\-]+)',   re.IGNORECASE),
    re.compile(r'loginId[=:\s]+([A-Za-z0-9_@.\-]+)', re.IGNORECASE),
    re.compile(r'id[=:\s]+([A-Za-z0-9_@.\-]{3,})',  re.IGNORECASE),
]

# IP 주소 추출 정규식 (IPv4)
_IP_PATTERN = re.compile(
    r'\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b'
)

# 비정상 접근 판단 기준
_WINDOW_MINUTES  = 5    # 관찰 시간 창 (분)
_REQUEST_LIMIT   = 30   # 이 횟수를 넘으면 비정상으로 판단


class AccessAnalyzer:
    """
    사용자 ID 또는 IP 기반으로 비정상 접근 패턴을 분석합니다.

    동작 원리:
        1. 로그에서 사용자 ID 또는 IP를 추출합니다.
        2. 5분 단위 슬라이딩 윈도우로 요청 수를 셉니다.
        3. 임계값을 초과하는 경우 AbnormalAccessRecord를 생성합니다.
    """

    def __init__(
        self,
        window_minutes: int = _WINDOW_MINUTES,
        request_limit:  int = _REQUEST_LIMIT,
    ) -> None:
        """
        분석기를 초기화합니다.

        매개변수:
            window_minutes: 관찰 시간 창 (분). 기본값 5분
            request_limit : 비정상 판단 기준 요청 횟수. 기본값 30회
        """
        self.window_minutes = window_minutes
        self.request_limit  = request_limit

    def analyze(self, entries: List[LogEntry]) -> List[AbnormalAccessRecord]:
        """
        로그 엔트리 목록에서 비정상 접근 패턴을 분석합니다.

        매개변수:
            entries: 파싱된 LogEntry 객체 목록

        반환:
            AbnormalAccessRecord 목록 (요청 횟수 내림차순 정렬)
        """
        if not entries:
            return []

        # 사용자/IP별로 (시각, 메시지) 쌍을 모읍니다
        # 키: 식별자(userId 또는 IP), 값: [(datetime, message), ...]
        access_log: Dict[str, List[tuple]] = defaultdict(list)

        for entry in entries:
            identifier = self._extract_identifier(entry.message)
            if identifier is None:
                continue
            access_log[identifier].append((entry.timestamp, entry.message))

        # 각 식별자별로 슬라이딩 윈도우 분석 수행
        results: List[AbnormalAccessRecord] = []
        window = timedelta(minutes=self.window_minutes)

        for identifier, events in access_log.items():
            # 시간순 정렬
            events.sort(key=lambda e: e[0])

            # 슬라이딩 윈도우: 각 이벤트를 시작점으로 window 내 이벤트 수 카운트
            anomalies = self._find_anomalies(identifier, events, window)
            results.extend(anomalies)

        # 요청 횟수 내림차순 정렬
        results.sort(key=lambda r: r.request_count, reverse=True)

        # 동일 식별자 중복 제거 (가장 심각한 건만 남깁니다)
        return self._deduplicate(results)

    def _find_anomalies(
        self,
        identifier: str,
        events: List[tuple],
        window: timedelta,
    ) -> List[AbnormalAccessRecord]:
        """
        특정 식별자의 이벤트 목록에서 시간 창 내 과다 요청을 찾습니다.

        매개변수:
            identifier: 사용자 ID 또는 IP
            events    : (datetime, message) 튜플 목록 (시간순 정렬)
            window    : 관찰 시간 창

        반환:
            AbnormalAccessRecord 목록
        """
        anomalies: List[AbnormalAccessRecord] = []
        n = len(events)

        # 두 포인터 방법으로 슬라이딩 윈도우를 구현합니다
        # left: 윈도우 시작, right: 윈도우 끝
        left = 0
        for right in range(n):
            window_end_time = events[right][0]

            # 윈도우 시작을 조정합니다: 너무 오래된 이벤트는 제외
            while (window_end_time - events[left][0]) > window:
                left += 1

            count_in_window = right - left + 1

            # 임계값 초과 시 이상으로 기록합니다
            if count_in_window > self.request_limit:
                # 해당 윈도우 내 메시지 샘플 (최대 5개)
                sample_range = events[left: left + 5]
                samples = [msg[:150] for _, msg in sample_range]

                anomalies.append(AbnormalAccessRecord(
                    identifier        = identifier,
                    request_count     = count_in_window,
                    time_range_start  = events[left][0],
                    time_range_end    = events[right][0],
                    sample_messages   = samples,
                ))

        return anomalies

    @staticmethod
    def _extract_identifier(message: str) -> Optional[str]:
        """
        로그 메시지에서 사용자 ID 또는 IP 주소를 추출합니다.
        사용자 ID 패턴을 먼저 시도하고, 없으면 IP를 시도합니다.

        매개변수:
            message: 로그 메시지 텍스트

        반환:
            식별자 문자열, 없으면 None
        """
        # 사용자 ID 패턴 시도
        for pattern in _USER_ID_PATTERNS:
            match = pattern.search(message)
            if match:
                value = match.group(1)
                # 너무 짧거나 숫자만 있는 것은 제외 (라인 번호 등 오탐 방지)
                if len(value) >= 3 and not value.isdigit():
                    return f"USER:{value}"

        # IP 주소 시도
        ip_match = _IP_PATTERN.search(message)
        if ip_match:
            return f"IP:{ip_match.group(1)}"

        return None

    @staticmethod
    def _deduplicate(
        records: List[AbnormalAccessRecord],
    ) -> List[AbnormalAccessRecord]:
        """
        같은 식별자의 중복된 이상 기록 중 가장 심각한 것만 남깁니다.

        매개변수:
            records: AbnormalAccessRecord 목록

        반환:
            중복 제거된 목록
        """
        seen: set[str] = set()
        unique: List[AbnormalAccessRecord] = []

        for record in records:
            if record.identifier not in seen:
                seen.add(record.identifier)
                unique.append(record)

        return unique
