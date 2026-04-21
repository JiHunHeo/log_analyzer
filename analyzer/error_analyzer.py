# ============================================================
# error_analyzer.py - 에러/예외 패턴 분석기
# ============================================================
# ERROR, FATAL 레벨 로그를 클래스별·시간대별로 집계합니다.
# 같은 클래스에서 반복되는 에러를 하나의 패턴으로 묶어서
# 어느 클래스에서 에러가 가장 많이 발생하는지 보여줍니다.
# ============================================================

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import List

from models.log_entry import ErrorRecord, LogEntry, LogLevel


class ErrorAnalyzer:
    """
    에러 및 예외 패턴을 분석하는 클래스입니다.

    동작 원리:
        1. ERROR/FATAL 레벨 로그를 클래스 이름별로 그룹화합니다.
        2. 각 그룹의 발생 횟수, 첫 발생, 마지막 발생 시각을 기록합니다.
        3. 대표 에러 메시지 샘플을 최대 3개까지 보관합니다.
    """

    def __init__(self, top_n: int = 50) -> None:
        """
        분석기를 초기화합니다.

        매개변수:
            top_n: 결과로 반환할 상위 에러 클래스 수. 기본값 50
        """
        self.top_n = top_n

    def analyze(self, entries: List[LogEntry]) -> List[ErrorRecord]:
        """
        로그 엔트리 목록에서 에러 패턴을 분석합니다.

        매개변수:
            entries: 파싱된 LogEntry 객체 목록

        반환:
            ErrorRecord 목록 (에러 건수 내림차순 정렬)
        """
        if not entries:
            return []

        # 클래스별 에러 정보를 모아두는 딕셔너리
        # 키: 클래스명, 값: {"count", "first", "last", "samples"} 딕셔너리
        class_errors: dict[str, dict] = defaultdict(lambda: {
            "count":   0,
            "first":   None,   # 첫 발생 시각
            "last":    None,   # 마지막 발생 시각
            "samples": [],     # 메시지 샘플 목록
        })

        for entry in entries:
            # ERROR 또는 FATAL 레벨만 처리합니다
            if entry.level not in (LogLevel.ERROR, LogLevel.FATAL):
                continue

            # 클래스명이 없으면 파일명을 대신 사용합니다
            key = entry.source_class or entry.file_name or "알수없음"

            info = class_errors[key]
            info["count"] += 1

            # 첫 발생 시각: 처음에만 설정합니다
            if info["first"] is None:
                info["first"] = entry.timestamp
            # 마지막 발생 시각: 항상 갱신합니다
            info["last"] = entry.timestamp

            # 메시지 샘플은 최대 3개까지만 보관합니다 (중복 제외)
            if (len(info["samples"]) < 3
                    and entry.message not in info["samples"]):
                info["samples"].append(entry.message[:200])  # 200자 제한

        # 딕셔너리를 ErrorRecord 목록으로 변환합니다
        results: List[ErrorRecord] = []
        for class_name, info in class_errors.items():
            results.append(ErrorRecord(
                source_class    = class_name,
                error_count     = info["count"],
                first_occurred  = info["first"] or datetime.min,
                last_occurred   = info["last"]  or datetime.min,
                sample_messages = info["samples"],
            ))

        # 에러 건수 내림차순으로 정렬 (가장 많이 발생한 클래스를 위에)
        results.sort(key=lambda r: r.error_count, reverse=True)

        # 상위 N개만 반환합니다
        return results[: self.top_n]
