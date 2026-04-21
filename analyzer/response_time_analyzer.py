# ============================================================
# response_time_analyzer.py - 응답시간 지연 분석기
# ============================================================
# "@@@~메서드명 ... - 시작 ~@@@" 와
# "@@@~메서드명 ... - 종료 ~@@@" 로그 쌍을 찾아서
# 두 시각의 차이로 처리 소요 시간을 계산합니다.
#
# 예시 로그:
#   "@@@~Rcv202Ctrl.rcv20220s04 원서접수 => 1차 원서접수 DB 저장 확인 - 시작 ~@@@"
#   "@@@~Rcv202Ctrl.rcv20220s04 원서접수 => 1차 원서접수 DB 저장 확인 - 종료 ~@@@"
# ============================================================

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from models.log_entry import LogEntry, ResponseTimeRecord


# "@@@~메서드정보 - 시작 ~@@@" 또는 "- 종료 ~@@@" 패턴을 찾는 정규식
_MARKER_PATTERN = re.compile(
    r'@@@~(.+?)\s*-\s*(시작|종료|START|END|start|end)\s*~@@@',
    re.IGNORECASE  # 대소문자 무시
)

# 느린 응답으로 판단하는 기준 시간 (밀리초)
_SLOW_THRESHOLD_MS = 3000.0  # 3초


class ResponseTimeAnalyzer:
    """
    로그에서 시작/종료 쌍을 찾아 처리 시간을 측정하는 분석기입니다.

    동작 원리:
        1. "@@@~" 마커가 있는 로그를 모두 찾습니다.
        2. 같은 메서드 이름의 시작/종료 쌍을 매칭합니다.
        3. 시간 차이를 계산하고 느린 경우(3초 초과)를 표시합니다.
    """

    def __init__(self, slow_threshold_ms: float = _SLOW_THRESHOLD_MS) -> None:
        """
        분석기를 초기화합니다.

        매개변수:
            slow_threshold_ms: 느린 응답 기준 (밀리초). 기본값 3000ms
        """
        self.slow_threshold_ms = slow_threshold_ms

    def analyze(self, entries: List[LogEntry]) -> List[ResponseTimeRecord]:
        """
        로그 엔트리 목록에서 응답시간을 분석합니다.

        매개변수:
            entries: 파싱된 LogEntry 객체 목록

        반환:
            ResponseTimeRecord 목록 (처리 시간 내림차순 정렬)
        """
        if not entries:
            return []

        # 시작 마커를 임시 저장하는 딕셔너리
        # 키: 메서드 식별 문자열, 값: (LogEntry, 시작 로그 원본)
        # 같은 메서드가 동시에 여러 번 시작될 수 있으므로 list로 보관합니다
        pending_starts: Dict[str, List[LogEntry]] = {}

        results: List[ResponseTimeRecord] = []

        for entry in entries:
            marker_info = self._extract_marker(entry.message)
            if marker_info is None:
                continue  # 마커가 없는 로그는 건너뜁니다

            method_key, marker_type = marker_info

            if marker_type in ("시작", "start", "START"):
                # 시작 마커: 대기 목록에 추가합니다
                if method_key not in pending_starts:
                    pending_starts[method_key] = []
                pending_starts[method_key].append(entry)

            elif marker_type in ("종료", "end", "END"):
                # 종료 마커: 대응하는 시작 마커를 찾습니다
                start_entry = self._pop_matching_start(pending_starts, method_key)
                if start_entry is None:
                    # 시작 로그 없이 종료 로그만 있는 경우: 건너뜁니다
                    continue

                # 처리 시간 계산 (밀리초 단위)
                duration_ms = self._calc_duration_ms(
                    start_entry.timestamp, entry.timestamp
                )

                # 음수 시간은 로그 순서 오류이므로 건너뜁니다
                if duration_ms < 0:
                    continue

                record = ResponseTimeRecord(
                    method_name  = method_key,
                    duration_ms  = round(duration_ms, 2),
                    start_time   = start_entry.timestamp,
                    end_time     = entry.timestamp,
                    start_log    = start_entry.raw_line[:300],
                    end_log      = entry.raw_line[:300],
                    is_slow      = duration_ms > self.slow_threshold_ms,
                )
                results.append(record)

        # 처리 시간 내림차순 정렬 (가장 오래 걸린 것을 위에 표시)
        results.sort(key=lambda r: r.duration_ms, reverse=True)
        return results

    @staticmethod
    def _extract_marker(message: str) -> Optional[Tuple[str, str]]:
        """
        메시지에서 "@@@~메서드명 - 시작/종료 ~@@@" 패턴을 찾습니다.

        매개변수:
            message: 로그 메시지 텍스트

        반환:
            (메서드 식별 문자열, "시작" 또는 "종료") 튜플,
            패턴이 없으면 None
        """
        match = _MARKER_PATTERN.search(message)
        if not match:
            return None

        # 메서드 정보와 시작/종료 구분
        method_part = match.group(1).strip()
        marker_type = match.group(2).strip()

        return method_part, marker_type

    @staticmethod
    def _pop_matching_start(
        pending: Dict[str, List[LogEntry]],
        method_key: str
    ) -> Optional[LogEntry]:
        """
        대기 중인 시작 마커 목록에서 해당 메서드의 가장 최근 시작을 꺼냅니다.
        스택(LIFO) 방식으로 처리합니다.

        매개변수:
            pending   : 시작 마커 대기 딕셔너리
            method_key: 찾을 메서드 식별 문자열

        반환:
            LogEntry (찾으면), None (없으면)
        """
        if method_key not in pending or not pending[method_key]:
            return None
        # 가장 최근에 추가된 시작 마커를 꺼냅니다 (pop = 목록에서 제거)
        entry = pending[method_key].pop()
        # 빈 목록은 딕셔너리에서 제거합니다 (메모리 절약)
        if not pending[method_key]:
            del pending[method_key]
        return entry

    @staticmethod
    def _calc_duration_ms(start_dt, end_dt) -> float:
        """
        두 datetime의 차이를 밀리초로 계산합니다.

        매개변수:
            start_dt: 시작 시각
            end_dt  : 종료 시각

        반환:
            밀리초 단위 시간 (float)
        """
        delta = end_dt - start_dt
        # timedelta.total_seconds() × 1000 = 밀리초
        return delta.total_seconds() * 1000
