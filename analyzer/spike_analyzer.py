# ============================================================
# spike_analyzer.py - 요청 폭증(Spike) 분석기
# ============================================================
# 특정 시간대에 로그(요청)가 갑자기 많아지는 구간을 찾습니다.
# 1분, 5분, 1시간 단위로 집계해서 이전 구간 대비 N배 이상
# 증가했을 때 이상으로 판단합니다.
# ============================================================

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import List

from models.log_entry import LogEntry, SpikeRecord


class SpikeAnalyzer:
    """
    시간대별 요청 수를 집계하고 폭증 구간을 찾아내는 분석기입니다.

    동작 원리:
        1. 로그 엔트리를 1분/5분/1시간 단위로 버킷(묶음)에 넣습니다.
        2. 각 버킷의 요청 수를 직전 버킷과 비교합니다.
        3. 증가율이 기준(threshold)을 넘으면 폭증으로 판정합니다.
    """

    def __init__(
        self,
        spike_threshold_ratio: float = 3.0,
        min_requests_for_spike: int  = 10,
    ) -> None:
        """
        분석기를 초기화합니다.

        매개변수:
            spike_threshold_ratio : 이전 구간 대비 몇 배 이상이면 폭증인지.
                                    기본값 3.0 = 이전 구간보다 3배 이상 많으면 이상
            min_requests_for_spike: 폭증으로 판단하기 위한 최소 요청 수.
                                    너무 적은 수의 증가는 무시합니다. 기본값 10
        """
        self.spike_threshold_ratio  = spike_threshold_ratio
        self.min_requests_for_spike = min_requests_for_spike

    def analyze(self, entries: List[LogEntry]) -> List[SpikeRecord]:
        """
        로그 엔트리 목록을 분석해서 요청 폭증 구간 목록을 반환합니다.

        매개변수:
            entries: 파싱된 LogEntry 객체 목록

        반환:
            SpikeRecord 목록 (폭증 구간 정보)
        """
        if not entries:
            return []

        results: List[SpikeRecord] = []

        # 1분, 5분, 1시간 세 단위로 각각 분석합니다
        for window_minutes, window_label in [(1, "1분"), (5, "5분"), (60, "1시간")]:
            spikes = self._detect_spikes(entries, window_minutes, window_label)
            results.extend(spikes)

        # 증가율 내림차순으로 정렬 (가장 심각한 폭증을 위에 표시)
        results.sort(key=lambda r: r.increase_rate, reverse=True)
        return results

    def _detect_spikes(
        self,
        entries: List[LogEntry],
        window_minutes: int,
        window_type: str,
    ) -> List[SpikeRecord]:
        """
        특정 시간 단위(window_minutes)로 요청을 묶어 폭증 구간을 찾습니다.

        매개변수:
            entries        : 로그 엔트리 목록
            window_minutes : 시간 창 크기 (분 단위)
            window_type    : 표시용 단위 이름 ("1분", "5분", "1시간")

        반환:
            SpikeRecord 목록
        """
        # 시간대별 요청 수를 세는 딕셔너리
        # 키: 시간 구간 시작 시각, 값: 요청 수
        bucket: dict[datetime, int] = defaultdict(int)

        window_delta = timedelta(minutes=window_minutes)

        for entry in entries:
            # 각 로그의 시각을 window_minutes 단위로 내림(floor)합니다.
            # 예) window_minutes=5, 시각=14:07 → 버킷 키=14:05
            ts = entry.timestamp
            floored = self._floor_datetime(ts, window_minutes)
            bucket[floored] += 1

        # 시간순으로 정렬합니다
        sorted_times = sorted(bucket.keys())

        spikes: List[SpikeRecord] = []
        # 두 번째 구간부터 이전 구간과 비교합니다
        for i in range(1, len(sorted_times)):
            current_time  = sorted_times[i]
            previous_time = sorted_times[i - 1]

            current_count  = bucket[current_time]
            previous_count = bucket[previous_time]

            # 이전 구간이 0이면 나눗셈 오류 방지를 위해 1로 처리합니다
            if previous_count == 0:
                previous_count = 1

            increase_rate = current_count / previous_count

            # 폭증 조건: 증가율 초과 AND 최소 요청 수 초과
            if (increase_rate >= self.spike_threshold_ratio
                    and current_count >= self.min_requests_for_spike):

                # 화면에 보여줄 시간 범위 문자열 만들기
                end_time = current_time + window_delta
                label = (
                    f"{current_time.strftime('%Y-%m-%d %H:%M')}"
                    f" ~ {end_time.strftime('%H:%M')}"
                )

                spikes.append(SpikeRecord(
                    window_start  = current_time,
                    window_label  = label,
                    request_count = current_count,
                    increase_rate = round(increase_rate, 2),
                    window_type   = window_type,
                ))

        return spikes

    @staticmethod
    def _floor_datetime(dt: datetime, window_minutes: int) -> datetime:
        """
        datetime을 window_minutes 단위로 내림(버림)합니다.
        예) 14:07:32 를 5분 단위로 내리면 → 14:05:00

        매개변수:
            dt             : 원본 시각
            window_minutes : 내림 단위 (분)

        반환:
            내림된 datetime 객체
        """
        # 하루 시작(자정)으로부터 몇 분이 지났는지 계산
        total_minutes = dt.hour * 60 + dt.minute
        # window_minutes 단위로 내림
        floored_minutes = (total_minutes // window_minutes) * window_minutes
        # 내림된 시각으로 새 datetime 만들기
        return dt.replace(
            hour        = floored_minutes // 60,
            minute      = floored_minutes % 60,
            second      = 0,
            microsecond = 0,
        )
