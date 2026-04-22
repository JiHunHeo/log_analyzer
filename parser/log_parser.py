# ============================================================
# log_parser.py - 로그 파일을 읽어서 LogEntry 객체로 변환
# ============================================================
# 로그 파일은 두 가지 형식이 섞여 있습니다.
# 이 파일은 각 줄을 읽으면서 어떤 형식인지 판별하고,
# 날짜·시각·클래스명·메시지 등을 분리해서 LogEntry에 담습니다.
#
# 스트리밍 방식: 파일 전체를 한꺼번에 메모리에 올리지 않고
# 한 줄씩 읽어 처리합니다. 대용량 파일에도 안전합니다.
# ============================================================

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Generator, Optional

from models.log_entry import LogEntry, LogFormat, LogLevel


# ============================================================
# 정규식(Regular Expression) 패턴 정의
# 정규식은 텍스트에서 원하는 부분을 뽑아내는 특수 문법입니다.
# ============================================================

# 형식 1 - JEUS 시스템 로그 패턴
# 예: [2026.03.23 14:01:01:112][2] [container1-1-479847] [D_SESSION-3105] <container1-1> 메시지
_JEUS_PATTERN = re.compile(
    r'^\[(\d{4}\.\d{2}\.\d{2}\s+\d{2}:\d{2}:\d{2}:\d{3})\]'  # [날짜 시간:밀리초]
    r'\[(\d+)\]\s+'                                               # [스레드번호]
    r'\[([^\]]+)\]\s+'                                            # [컨테이너-스레드ID]
    r'(?:\[([^\]]*)\]\s+)?'                                       # [세션ID] (없을 수도 있음)
    r'(?:<([^>]+)>\s+)?'                                          # <컨테이너명> (없을 수도 있음)
    r'(.+)$'                                                      # 나머지 메시지 전부
)

# 형식 2 - 애플리케이션(eGovFramework) 로그 패턴
# 실제 파일에서 두 가지 변형이 확인됨:
#   변형 A: 2026-03-23 14:11:17,658  INFO [BizRcvExamRecpt.java(133)] 메시지  ← 대괄호 []
#   변형 B: 2026-03-23 14:01:01, 113 ERROR {Rcv202Ctrl.java(674)] 메시지     ← 중괄호 {
# → [\[\{] 로 두 가지 모두 처리
_EGOV_PATTERN = re.compile(
    r'^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}),\s*(\d+)\s+'   # 날짜 시간, 밀리초
    r'(DEBUG|INFO|WARN|WARNING|ERROR|FATAL)\s+'                   # 로그 레벨
    r'[\[\{]([^\.\]\}]+\.java)\((\d+)\)[\]\}]\s*'               # [클래스.java(줄번호)] 또는 {클래스.java(줄번호)}
    r'(.+)$'                                                      # 메시지
)

# 형식 2 변형 - 클래스 정보 없이 레벨만 있는 경우
_EGOV_SIMPLE_PATTERN = re.compile(
    r'^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}),\s*(\d+)\s+'
    r'(DEBUG|INFO|WARN|WARNING|ERROR|FATAL)\s+'
    r'(.+)$'
)

# 형식 3 - 시간만 있는 단순 로그 (날짜 없이 시간만 기록)
# 예: [14:11:17] getBeforeOpen rtnList size1
_TIME_ONLY_PATTERN = re.compile(
    r'^\[(\d{2}:\d{2}:\d{2})\]\s+(.+)$'
)

# 날짜 파싱 포맷 (형식 1: 점으로 구분)
_JEUS_DATETIME_FMT = "%Y.%m.%d %H:%M:%S"

# 날짜 파싱 포맷 (형식 2: 하이픈으로 구분)
_EGOV_DATETIME_FMT = "%Y-%m-%d %H:%M:%S"


class LogParser:
    """
    로그 파일을 파싱(분석)하는 클래스입니다.
    파일을 한 줄씩 읽어 LogEntry 객체로 변환합니다.

    사용 예시:
        parser = LogParser()
        for entry in parser.parse_file("server.log"):
            print(entry.timestamp, entry.message)
    """

    def __init__(self, slow_threshold_ms: int = 3000) -> None:
        """
        파서를 초기화합니다.

        매개변수:
            slow_threshold_ms: 응답 지연으로 판단할 기준 시간(밀리초).
                               기본값 3000ms = 3초
        """
        # 느린 응답 판단 기준 (밀리초)
        self.slow_threshold_ms = slow_threshold_ms

        # 파싱 통계: 각 형식이 몇 줄씩 처리됐는지 기록
        self.stats = {
            "total":       0,   # 전체 줄 수
            "jeus":        0,   # JEUS 형식 줄 수
            "egov":        0,   # 앱 형식 줄 수
            "unknown":     0,   # 인식 불가 줄 수
            "parse_errors": 0,  # 파싱 오류 줄 수
        }

    def parse_file(
        self,
        file_path: str | Path,
        encoding: str = "cp949",
        progress_callback=None
    ) -> Generator[LogEntry, None, None]:
        """
        로그 파일을 한 줄씩 읽어 LogEntry 객체를 yield(하나씩 반환)합니다.
        yield를 사용하기 때문에 대용량 파일도 메모리 걱정 없이 처리됩니다.

        매개변수:
            file_path        : 읽을 로그 파일 경로
            encoding         : 파일 인코딩 (기본: cp949 - 한국 Windows 서버 기본값)
            progress_callback: 진행률 업데이트용 콜백 함수 (선택)

        반환:
            LogEntry 객체를 하나씩 반환하는 제너레이터
        """
        path = Path(file_path)
        file_name = path.name  # 파일 이름만 추출 (경로 제외)

        # 파일이 없으면 예외를 발생시켜 사용자에게 알립니다
        if not path.exists():
            raise FileNotFoundError(f"파일을 찾을 수 없습니다: {file_path}")

        # 인코딩 자동 감지: cp949 → utf-8 → utf-8-sig(BOM 있는 UTF-8) 순서로 시도
        # 한국 Windows 서버 로그는 대부분 cp949(EUC-KR)입니다
        detected_encoding = self._detect_encoding(path)

        # 파일 전체 줄 수를 먼저 세어 진행률 계산에 사용합니다
        total_lines = self._count_lines(path, detected_encoding)

        line_no = 0
        processed = 0

        # 파일을 열고 한 줄씩 읽습니다 (with 문은 파일을 자동으로 닫아줍니다)
        with path.open(encoding=detected_encoding, errors="replace") as f:
            for raw_line in f:
                line_no += 1
                self.stats["total"] += 1

                # 앞뒤 공백·줄바꿈 문자를 제거합니다
                stripped = raw_line.rstrip("\n\r")

                # 빈 줄은 건너뜁니다
                if not stripped.strip():
                    continue

                # 한 줄을 파싱해서 LogEntry로 변환합니다
                entry = self._parse_line(stripped, file_name, line_no)

                if entry is not None:
                    yield entry

                # 진행률 콜백이 있으면 주기적으로 호출합니다
                processed += 1
                if progress_callback and processed % 5000 == 0:
                    pct = int(processed / max(total_lines, 1) * 100)
                    progress_callback(pct)

    def _detect_encoding(self, path: Path) -> str:
        """
        로그 파일의 인코딩을 자동으로 감지합니다.
        파일 앞부분의 BOM(바이트 순서 표시)을 보고 판단합니다.

        감지 순서:
          1. UTF-16 LE BOM (FF FE) → 'utf-16'
          2. UTF-16 BE BOM (FE FF) → 'utf-16'
          3. UTF-8 BOM (EF BB BF)  → 'utf-8-sig'
          4. cp949 디코딩 성공     → 'cp949'  (한국 Windows 기본)
          5. 그 외                 → 'utf-8'
        """
        try:
            bom = path.read_bytes()[:4]
        except Exception:
            return "cp949"

        # UTF-16 LE BOM: FF FE
        if bom[:2] == b'\xff\xfe':
            return "utf-16"

        # UTF-16 BE BOM: FE FF
        if bom[:2] == b'\xfe\xff':
            return "utf-16"

        # UTF-8 BOM: EF BB BF
        if bom[:3] == b'\xef\xbb\xbf':
            return "utf-8-sig"

        # BOM 없으면 cp949(한국 Windows)로 시도
        try:
            path.read_bytes()[:5000].decode("cp949")
            return "cp949"
        except (UnicodeDecodeError, LookupError):
            pass

        return "utf-8"

    def _count_lines(self, path: Path, encoding: str) -> int:
        """
        파일의 총 줄 수를 빠르게 셉니다.
        진행률(%) 계산에 사용됩니다.
        """
        try:
            with path.open(encoding=encoding, errors="replace") as f:
                return sum(1 for _ in f)
        except Exception:
            return 0

    def _parse_line(
        self,
        line: str,
        file_name: str,
        line_no: int
    ) -> Optional[LogEntry]:
        """
        로그 한 줄을 받아서 JEUS 형식인지 앱 형식인지 판별하고
        LogEntry 객체로 만들어 반환합니다.

        매개변수:
            line      : 파싱할 로그 줄 텍스트
            file_name : 소속 파일 이름 (결과에 기록)
            line_no   : 파일 내 줄 번호

        반환:
            성공 시 LogEntry, 실패 시 None
        """
        try:
            # 형식 1 시도: JEUS 시스템 로그 ([날짜 시간] 으로 시작)
            if line.startswith("["):
                # 먼저 JEUS 전체 날짜 형식 시도
                entry = self._try_parse_jeus(line, file_name, line_no)
                if entry:
                    self.stats["jeus"] += 1
                    return entry
                # [HH:MM:SS] 시간만 있는 단순 로그 형식 시도
                entry = self._try_parse_time_only(line, file_name, line_no)
                if entry:
                    self.stats["egov"] += 1
                    return entry

            # 형식 2 시도: 앱 로그 (숫자 날짜로 시작, 예: 2026-)
            if re.match(r'^\d{4}-', line):
                entry = self._try_parse_egov(line, file_name, line_no)
                if entry:
                    self.stats["egov"] += 1
                    return entry

            # 두 형식 모두 해당 없음 → UNKNOWN 처리
            self.stats["unknown"] += 1
            return None  # 인식 불가 줄은 결과에 포함하지 않습니다

        except Exception:
            # 예상치 못한 파싱 오류 시 조용히 건너뜁니다
            self.stats["parse_errors"] += 1
            return None

    def _try_parse_jeus(
        self,
        line: str,
        file_name: str,
        line_no: int
    ) -> Optional[LogEntry]:
        """
        JEUS 시스템 로그 형식으로 파싱을 시도합니다.

        예: [2026.03.23 14:01:01:112][2] [container1-1-479847] [D_SESSION-3105] <container1-1> 메시지
        """
        match = _JEUS_PATTERN.match(line)
        if not match:
            return None

        # 정규식에서 각 그룹(괄호 부분)을 꺼냅니다
        dt_str, thread_id, container_thread, session_id, container, message = match.groups()

        # "2026.03.23 14:01:01:112" → datetime 객체로 변환
        # 밀리초 부분(:112)이 붙어 있으므로 마지막 콜론 앞까지만 파싱합니다
        try:
            # 밀리초 분리: "14:01:01:112" → "14:01:01" + 112
            dt_base, ms_str = dt_str.rsplit(":", 1)
            dt = datetime.strptime(dt_base.strip(), _JEUS_DATETIME_FMT)
            ms = int(ms_str)
            # microsecond는 밀리초 × 1000 입니다
            dt = dt.replace(microsecond=ms * 1000)
        except (ValueError, IndexError):
            return None

        # 로그 레벨은 JEUS 시스템 로그에 명시되지 않으므로
        # 메시지 내용으로 유추합니다
        level = self._infer_level_from_message(message or "")

        return LogEntry(
            raw_line        = line,
            timestamp       = dt,
            log_format      = LogFormat.JEUS_SYSTEM,
            message         = (message or "").strip(),
            level           = level,
            thread_id       = thread_id,
            container       = container,
            session_id      = session_id,
            file_name       = file_name,
            line_no_in_file = line_no,
        )

    def _try_parse_egov(
        self,
        line: str,
        file_name: str,
        line_no: int
    ) -> Optional[LogEntry]:
        """
        eGovFramework 애플리케이션 로그 형식으로 파싱을 시도합니다.

        예: 2026-03-23 14:01:01, 113 ERROR {Rcv202Ctrl.java(674)] 메시지
        """
        # 상세 형식(클래스명 포함) 시도
        match = _EGOV_PATTERN.match(line)
        if match:
            dt_str, ms_str, level_str, class_file, lineno_str, message = match.groups()
            source_class = class_file.replace(".java", "")  # ".java" 제거
            line_number  = int(lineno_str)
        else:
            # 간단 형식 시도 (클래스명 없는 경우)
            match = _EGOV_SIMPLE_PATTERN.match(line)
            if not match:
                return None
            dt_str, ms_str, level_str, message = match.groups()
            source_class = None
            line_number  = None

        # "2026-03-23 14:01:01" + "113" → datetime 객체
        try:
            dt = datetime.strptime(dt_str.strip(), _EGOV_DATETIME_FMT)
            ms = int(ms_str.strip())
            dt = dt.replace(microsecond=ms * 1000)
        except ValueError:
            return None

        # 로그 레벨 문자열을 열거형으로 변환
        level = self._str_to_level(level_str)

        return LogEntry(
            raw_line        = line,
            timestamp       = dt,
            log_format      = LogFormat.APP_EGOV,
            message         = message.strip(),
            level           = level,
            source_class    = source_class,
            line_number     = line_number,
            file_name       = file_name,
            line_no_in_file = line_no,
        )

    def _try_parse_time_only(
        self,
        line: str,
        file_name: str,
        line_no: int
    ) -> Optional[LogEntry]:
        """
        시간만 있는 단순 로그 형식을 파싱합니다.
        날짜 없이 시간만 기록하는 애플리케이션 내부 출력 로그입니다.

        예: [14:11:17] getBeforeOpen rtnList size1
        """
        match = _TIME_ONLY_PATTERN.match(line)
        if not match:
            return None

        time_str, message = match.groups()

        try:
            # 시간만 있으므로 날짜는 1900-01-01로 임시 설정합니다
            # (분석 시 날짜 없는 로그임을 인지할 수 있도록 source_class를 TIME_ONLY로 표시)
            dt = datetime.strptime(time_str, "%H:%M:%S")
        except ValueError:
            return None

        level = self._infer_level_from_message(message)

        return LogEntry(
            raw_line        = line,
            timestamp       = dt,
            log_format      = LogFormat.APP_EGOV,
            message         = message.strip(),
            level           = level,
            source_class    = "TIME_ONLY",  # 날짜 없는 로그임을 표시
            file_name       = file_name,
            line_no_in_file = line_no,
        )

    @staticmethod
    def _str_to_level(level_str: str) -> LogLevel:
        """
        'ERROR', 'WARN' 같은 문자열을 LogLevel 열거형으로 변환합니다.
        알 수 없는 값이면 UNKNOWN을 반환합니다.
        """
        mapping = {
            "DEBUG":   LogLevel.DEBUG,
            "INFO":    LogLevel.INFO,
            "WARN":    LogLevel.WARN,
            "WARNING": LogLevel.WARNING,
            "ERROR":   LogLevel.ERROR,
            "FATAL":   LogLevel.FATAL,
        }
        return mapping.get(level_str.upper(), LogLevel.UNKNOWN)

    @staticmethod
    def _infer_level_from_message(message: str) -> LogLevel:
        """
        JEUS 시스템 로그처럼 레벨 표기가 없는 줄에서
        메시지 내용을 보고 레벨을 추측합니다.
        """
        msg_lower = message.lower()
        if any(w in msg_lower for w in ("exception", "error", "failed", "failure")):
            return LogLevel.ERROR
        if any(w in msg_lower for w in ("warn", "warning", "caution")):
            return LogLevel.WARN
        return LogLevel.INFO

    def reset_stats(self) -> None:
        """파싱 통계를 초기화합니다. 새 파일 세트를 처리하기 전에 호출하세요."""
        for key in self.stats:
            self.stats[key] = 0
