# ============================================================
# main.py - JEUS 서버 로그 분석기 진입점 + GUI
# ============================================================
# 이 파일이 프로그램의 시작점입니다.
# tkinter로 GUI(그래픽 화면)를 만들고,
# 버튼 클릭 시 파서와 분석기를 호출해서 결과를 Excel로 저장합니다.
# ============================================================

from __future__ import annotations

# 경로 문제 해결: 현재 폴더를 파이썬 경로에 추가합니다
# 이렇게 해야 parser, analyzer 등 하위 모듈을 import할 수 있습니다
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import List, Optional

# 직접 만든 모듈들 가져오기
from parser.log_parser import LogParser
from analyzer.spike_analyzer import SpikeAnalyzer
from analyzer.error_analyzer import ErrorAnalyzer
from analyzer.response_time_analyzer import ResponseTimeAnalyzer
from analyzer.access_analyzer import AccessAnalyzer
from analyzer.wallet_analyzer import WalletAnalyzer, ApplicationFlowAnalyzer
from reporter.excel_reporter import ExcelReporter
from models.log_entry import LogEntry


# ============================================================
# 색상 및 스타일 상수
# ============================================================
BG_WHITE        = "#FFFFFF"   # 배경 흰색
BTN_BLUE        = "#2E75B6"   # 버튼 파란색
BTN_BLUE_HOVER  = "#1F5280"   # 버튼 마우스오버 색상
BTN_GREEN       = "#70AD47"   # 분석 시작 버튼 초록색
BTN_GREEN_HOVER = "#4E7A33"
TEXT_DARK       = "#1F1F1F"   # 진한 텍스트
TEXT_GRAY       = "#595959"   # 회색 텍스트

# 운영체제별 폰트 자동 선택
# Windows: 맑은 고딕, macOS: Apple SD Gothic Neo, Linux: DejaVu Sans
import platform as _platform
_os = _platform.system()
if _os == "Windows":
    _FONT_NAME = "맑은 고딕"
elif _os == "Darwin":   # macOS
    _FONT_NAME = "Apple SD Gothic Neo"
else:                   # Linux 등
    _FONT_NAME = "DejaVu Sans"

FONT_MAIN  = (_FONT_NAME, 10)
FONT_TITLE = (_FONT_NAME, 16, "bold")
FONT_SMALL = (_FONT_NAME, 9)


class HoverButton(tk.Button):
    """
    마우스를 올리면 색이 바뀌는 커스텀 버튼입니다.
    일반 tk.Button을 상속해서 마우스 이벤트를 추가했습니다.
    """

    def __init__(self, master, normal_color: str, hover_color: str, **kwargs):
        """
        버튼을 초기화합니다.

        매개변수:
            master       : 부모 위젯
            normal_color : 기본 상태 배경색
            hover_color  : 마우스 올렸을 때 배경색
        """
        super().__init__(master, bg=normal_color, **kwargs)
        self._normal_color = normal_color
        self._hover_color  = hover_color

        # 마우스 이벤트 등록
        self.bind("<Enter>", self._on_enter)   # 마우스가 버튼 위로 들어올 때
        self.bind("<Leave>", self._on_leave)   # 마우스가 버튼에서 나갈 때

    def _on_enter(self, event) -> None:
        """마우스가 버튼 위에 올라오면 hover 색상으로 변경합니다."""
        self.config(bg=self._hover_color)

    def _on_leave(self, event) -> None:
        """마우스가 버튼에서 나가면 기본 색상으로 복원합니다."""
        self.config(bg=self._normal_color)


class LogAnalyzerApp:
    """
    JEUS 로그 분석기의 메인 GUI 애플리케이션 클래스입니다.

    역할:
        - tkinter 윈도우와 위젯(버튼, 텍스트창 등)을 만들고 관리합니다.
        - 파일 선택, 분석 시작, 결과 표시 등 사용자 인터랙션을 처리합니다.
        - 분석 작업은 별도 스레드에서 실행해 GUI가 멈추지 않게 합니다.
    """

    def __init__(self, root: tk.Tk) -> None:
        """
        앱을 초기화하고 GUI 위젯을 배치합니다.

        매개변수:
            root: tkinter 최상위 윈도우 객체
        """
        self.root = root
        self._setup_window()

        # 선택된 파일 경로 목록 (사용자가 선택한 로그 파일들)
        self.selected_files: List[Path] = []

        # 분석 실행 중 여부 (동시에 두 번 실행 방지)
        self.is_running: bool = False

        # GUI 위젯들을 만들고 배치합니다
        self._build_ui()

    def _setup_window(self) -> None:
        """윈도우 기본 설정을 합니다 (제목, 크기, 배경색 등)."""
        self.root.title("JEUS 서버 로그 분석기")
        self.root.geometry("900x700")
        self.root.minsize(800, 600)
        self.root.configure(bg=BG_WHITE)

        # 윈도우 아이콘이 없어도 에러가 나지 않도록 처리합니다
        try:
            self.root.iconbitmap(default="")
        except Exception:
            pass

        # 창 닫기 버튼(X)을 누르면 확인창을 보여줍니다
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self) -> None:
        """모든 GUI 위젯을 만들고 배치합니다."""

        # ---- 상단 제목 영역 ----
        title_frame = tk.Frame(self.root, bg=BTN_BLUE, pady=15)
        title_frame.pack(fill=tk.X)

        tk.Label(
            title_frame,
            text  = "JEUS 서버 로그 분석기",
            font  = FONT_TITLE,
            bg    = BTN_BLUE,
            fg    = "white",
        ).pack()
        tk.Label(
            title_frame,
            text  = "전자정부프레임워크 4.2 기반 자격증 신청 시스템 이상현상 탐지",
            font  = FONT_SMALL,
            bg    = BTN_BLUE,
            fg    = "#D6E4F7",
        ).pack()

        # ---- 메인 콘텐츠 영역 ----
        main_frame = tk.Frame(self.root, bg=BG_WHITE, padx=20, pady=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # ---- 파일 선택 섹션 ----
        self._build_file_section(main_frame)

        # ---- 출력 경로 섹션 ----
        self._build_output_section(main_frame)

        # ---- 분석 버튼 ----
        self._build_action_section(main_frame)

        # ---- 진행 상태 바 ----
        self._build_progress_section(main_frame)

        # ---- 결과 텍스트 창 ----
        self._build_result_section(main_frame)

        # ---- 하단 상태바 ----
        self._build_status_bar()

    def _build_file_section(self, parent: tk.Frame) -> None:
        """파일 선택 버튼과 선택된 파일 목록 표시 영역을 만듭니다."""
        section = tk.LabelFrame(
            parent,
            text       = "  1단계: 로그 파일 선택  ",
            bg         = BG_WHITE,
            fg         = BTN_BLUE,
            font       = ("맑은 고딕", 10, "bold"),
            padx       = 10,
            pady       = 8,
        )
        section.pack(fill=tk.X, pady=(0, 8))

        # 버튼 행
        btn_row = tk.Frame(section, bg=BG_WHITE)
        btn_row.pack(fill=tk.X)

        HoverButton(
            btn_row,
            normal_color = BTN_BLUE,
            hover_color  = BTN_BLUE_HOVER,
            text         = "파일 선택 (여러 파일 가능)",
            font         = FONT_MAIN,
            fg           = "white",
            relief       = tk.FLAT,
            padx         = 12,
            pady         = 6,
            cursor       = "hand2",
            command      = self._select_files,
        ).pack(side=tk.LEFT, padx=(0, 8))

        HoverButton(
            btn_row,
            normal_color = "#E74C3C",
            hover_color  = "#C0392B",
            text         = "목록 초기화",
            font         = FONT_MAIN,
            fg           = "white",
            relief       = tk.FLAT,
            padx         = 12,
            pady         = 6,
            cursor       = "hand2",
            command      = self._clear_files,
        ).pack(side=tk.LEFT)

        # 선택 파일 수 레이블
        self.file_count_label = tk.Label(
            btn_row,
            text = "선택된 파일: 0개",
            font = FONT_SMALL,
            bg   = BG_WHITE,
            fg   = TEXT_GRAY,
        )
        self.file_count_label.pack(side=tk.RIGHT)

        # 파일 목록 표시 (스크롤 가능한 리스트박스)
        list_frame = tk.Frame(section, bg=BG_WHITE)
        list_frame.pack(fill=tk.X, pady=(6, 0))

        scrollbar = tk.Scrollbar(list_frame, orient=tk.VERTICAL)
        self.file_listbox = tk.Listbox(
            list_frame,
            height          = 4,
            font            = FONT_SMALL,
            bg              = "#F8F9FA",
            fg              = TEXT_DARK,
            selectmode      = tk.EXTENDED,
            yscrollcommand  = scrollbar.set,
            relief          = tk.SUNKEN,
            borderwidth     = 1,
        )
        scrollbar.config(command=self.file_listbox.yview)
        self.file_listbox.pack(side=tk.LEFT, fill=tk.X, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    def _build_output_section(self, parent: tk.Frame) -> None:
        """결과 파일 저장 경로 선택 영역을 만듭니다."""
        section = tk.LabelFrame(
            parent,
            text   = "  2단계: 결과 저장 경로  ",
            bg     = BG_WHITE,
            fg     = BTN_BLUE,
            font   = ("맑은 고딕", 10, "bold"),
            padx   = 10,
            pady   = 8,
        )
        section.pack(fill=tk.X, pady=(0, 8))

        row = tk.Frame(section, bg=BG_WHITE)
        row.pack(fill=tk.X)

        # 경로 입력 필드
        self.output_path_var = tk.StringVar(
            value=str(Path.home() / "Desktop" / "JEUS로그분석결과.xlsx")
        )
        path_entry = tk.Entry(
            row,
            textvariable = self.output_path_var,
            font         = FONT_SMALL,
            relief       = tk.SUNKEN,
            borderwidth  = 1,
        )
        path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))

        HoverButton(
            row,
            normal_color = BTN_BLUE,
            hover_color  = BTN_BLUE_HOVER,
            text         = "경로 선택",
            font         = FONT_SMALL,
            fg           = "white",
            relief       = tk.FLAT,
            padx         = 10,
            pady         = 5,
            cursor       = "hand2",
            command      = self._select_output_path,
        ).pack(side=tk.RIGHT)

    def _build_action_section(self, parent: tk.Frame) -> None:
        """분석 시작 버튼 영역을 만듭니다."""
        action_frame = tk.Frame(parent, bg=BG_WHITE)
        action_frame.pack(fill=tk.X, pady=(0, 8))

        # 분석 시작 버튼 (크고 눈에 띄게 만듭니다)
        self.analyze_btn = HoverButton(
            action_frame,
            normal_color = BTN_GREEN,
            hover_color  = BTN_GREEN_HOVER,
            text         = "분석 시작",
            font         = ("맑은 고딕", 12, "bold"),
            fg           = "white",
            relief       = tk.FLAT,
            padx         = 30,
            pady         = 10,
            cursor       = "hand2",
            command      = self._start_analysis,
        )
        self.analyze_btn.pack(side=tk.LEFT)

        # 분석 중단 버튼
        self.stop_btn = HoverButton(
            action_frame,
            normal_color = "#95A5A6",
            hover_color  = "#7F8C8D",
            text         = "중단",
            font         = FONT_MAIN,
            fg           = "white",
            relief       = tk.FLAT,
            padx         = 15,
            pady         = 10,
            cursor       = "hand2",
            command      = self._stop_analysis,
            state        = tk.DISABLED,  # 처음에는 비활성화
        )
        self.stop_btn.pack(side=tk.LEFT, padx=(8, 0))

        # 우측 도움말 텍스트
        tk.Label(
            action_frame,
            text = "※ 대용량 파일은 수 분이 소요될 수 있습니다.",
            font = FONT_SMALL,
            bg   = BG_WHITE,
            fg   = TEXT_GRAY,
        ).pack(side=tk.RIGHT)

    def _build_progress_section(self, parent: tk.Frame) -> None:
        """진행 상태 바를 만듭니다."""
        progress_frame = tk.Frame(parent, bg=BG_WHITE)
        progress_frame.pack(fill=tk.X, pady=(0, 4))

        # 상태 레이블 (현재 작업 설명)
        self.progress_label = tk.Label(
            progress_frame,
            text = "대기 중...",
            font = FONT_SMALL,
            bg   = BG_WHITE,
            fg   = TEXT_GRAY,
        )
        self.progress_label.pack(anchor=tk.W)

        # 프로그레스 바 (0~100%)
        self.progress_bar = ttk.Progressbar(
            progress_frame,
            orient = tk.HORIZONTAL,
            mode   = "determinate",  # 퍼센트로 진행 표시
            length = 400,
        )
        self.progress_bar.pack(fill=tk.X)

    def _build_result_section(self, parent: tk.Frame) -> None:
        """분석 결과 요약 텍스트 출력창을 만듭니다."""
        section = tk.LabelFrame(
            parent,
            text   = "  분석 결과 요약  ",
            bg     = BG_WHITE,
            fg     = BTN_BLUE,
            font   = ("맑은 고딕", 10, "bold"),
            padx   = 10,
            pady   = 8,
        )
        section.pack(fill=tk.BOTH, expand=True)

        # 스크롤 가능한 텍스트 위젯
        text_scroll = tk.Scrollbar(section, orient=tk.VERTICAL)
        self.result_text = tk.Text(
            section,
            font         = ("Consolas", 9),  # 고정폭 폰트로 정렬을 맞춥니다
            bg           = "#1E1E1E",        # 어두운 배경 (터미널 느낌)
            fg           = "#D4D4D4",        # 밝은 텍스트
            wrap         = tk.WORD,
            relief       = tk.FLAT,
            yscrollcommand = text_scroll.set,
            state        = tk.DISABLED,      # 사용자가 직접 수정하지 못하게
        )
        text_scroll.config(command=self.result_text.yview)
        self.result_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        text_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # 텍스트 색상 태그 정의 (로그 레벨별 색상)
        self.result_text.tag_configure("info",    foreground="#4EC9B0")  # 청록
        self.result_text.tag_configure("success", foreground="#6DC85C")  # 초록
        self.result_text.tag_configure("warning", foreground="#FFD700")  # 노랑
        self.result_text.tag_configure("error",   foreground="#F44747")  # 빨강
        self.result_text.tag_configure("title",   foreground="#569CD6",
                                       font=("Consolas", 10, "bold"))   # 파랑 굵게

    def _build_status_bar(self) -> None:
        """화면 맨 아래 상태바를 만듭니다."""
        status_frame = tk.Frame(self.root, bg="#F0F0F0", relief=tk.SUNKEN,
                                 borderwidth=1)
        status_frame.pack(fill=tk.X, side=tk.BOTTOM)

        self.status_var = tk.StringVar(value="준비")
        tk.Label(
            status_frame,
            textvariable = self.status_var,
            font         = FONT_SMALL,
            bg           = "#F0F0F0",
            fg           = TEXT_GRAY,
            anchor       = tk.W,
            padx         = 8,
        ).pack(side=tk.LEFT, fill=tk.X)

    # ----------------------------------------------------------
    # 이벤트 핸들러 (사용자 동작에 반응하는 함수들)
    # ----------------------------------------------------------

    def _select_files(self) -> None:
        """
        파일 선택 대화상자를 열어 로그 파일을 선택합니다.
        여러 파일을 동시에 선택할 수 있습니다.
        """
        files = filedialog.askopenfilenames(
            title      = "로그 파일 선택 (여러 파일 선택 가능)",
            filetypes  = [
                ("로그 파일", "*.log *.txt *.out *.LOG"),
                ("모든 파일", "*.*"),
            ],
            initialdir = str(Path.home()),
        )

        if not files:
            return  # 취소하면 아무것도 안 합니다

        # 중복 없이 추가합니다
        existing = {str(p) for p in self.selected_files}
        for f in files:
            if f not in existing:
                self.selected_files.append(Path(f))
                existing.add(f)

        self._refresh_file_list()

    def _clear_files(self) -> None:
        """선택된 파일 목록을 모두 지웁니다."""
        self.selected_files.clear()
        self._refresh_file_list()
        self._log("파일 목록을 초기화했습니다.", "info")

    def _refresh_file_list(self) -> None:
        """리스트박스에 현재 선택된 파일 목록을 다시 표시합니다."""
        self.file_listbox.delete(0, tk.END)  # 기존 목록 삭제
        for path in self.selected_files:
            # 파일 크기도 함께 표시합니다
            try:
                size_mb = path.stat().st_size / (1024 * 1024)
                self.file_listbox.insert(tk.END, f"{path.name}  ({size_mb:.1f} MB)")
            except OSError:
                self.file_listbox.insert(tk.END, str(path.name))

        # 파일 수 레이블 업데이트
        count = len(self.selected_files)
        self.file_count_label.config(text=f"선택된 파일: {count}개")

    def _select_output_path(self) -> None:
        """결과 파일 저장 경로를 선택하는 대화상자를 엽니다."""
        path = filedialog.asksaveasfilename(
            title      = "결과 파일 저장 위치 선택",
            defaultextension = ".xlsx",
            filetypes  = [("Excel 파일", "*.xlsx")],
            initialfile = "JEUS로그분석결과.xlsx",
        )
        if path:
            self.output_path_var.set(path)

    def _start_analysis(self) -> None:
        """
        분석을 시작합니다.
        파일 선택 여부를 확인하고, 별도 스레드에서 분석을 실행합니다.
        GUI가 멈추지 않도록 threading을 사용합니다.
        """
        # 입력 유효성 검사
        if not self.selected_files:
            messagebox.showwarning("파일 없음", "먼저 로그 파일을 선택해주세요.")
            return

        output_path = self.output_path_var.get().strip()
        if not output_path:
            messagebox.showwarning("경로 없음", "결과 파일 저장 경로를 입력해주세요.")
            return

        if self.is_running:
            messagebox.showinfo("분석 중", "이미 분석이 진행 중입니다.")
            return

        # 분석 시작 상태로 UI 변경
        self.is_running = True
        self._set_ui_running(True)
        self._clear_result_text()

        # 분석을 별도 스레드에서 실행합니다
        # (메인 스레드에서 실행하면 GUI가 멈춥니다)
        worker = threading.Thread(
            target = self._run_analysis,
            args   = (self.selected_files[:], output_path),
            daemon = True,  # 메인 프로그램이 종료되면 같이 종료
        )
        worker.start()

    def _stop_analysis(self) -> None:
        """
        분석 중단 요청을 합니다.
        실제 중단은 스레드가 플래그를 확인할 때 반영됩니다.
        """
        self.is_running = False
        self._log("분석 중단을 요청했습니다...", "warning")

    def _run_analysis(self, files: List[Path], output_path: str) -> None:
        """
        실제 분석 작업을 수행하는 함수입니다. 별도 스레드에서 실행됩니다.

        매개변수:
            files      : 분석할 로그 파일 경로 목록
            output_path: 결과 Excel 파일 저장 경로
        """
        try:
            self._update_progress(0, "로그 파일 읽는 중...")
            self._log("=" * 55, "title")
            self._log("  JEUS 서버 로그 분석 시작", "title")
            self._log("=" * 55, "title")
            self._log(f"  대상 파일: {len(files)}개", "info")
            self._log(f"  분석 시작: {datetime.now().strftime('%H:%M:%S')}", "info")
            self._log("-" * 55)

            # ---- 1단계: 로그 파싱 ----
            self._log("1단계: 로그 파일 파싱 중...")
            parser  = LogParser()
            entries: List[LogEntry] = []

            for i, file_path in enumerate(files):
                if not self.is_running:
                    self._log("분석이 중단되었습니다.", "warning")
                    return

                self._log(f"  읽는 중: {file_path.name}", "info")

                def make_callback(file_index, total_files):
                    def callback(pct):
                        overall = int(
                            (file_index / total_files + pct / 100 / total_files) * 30
                        )
                        self._update_progress(
                            overall, f"파싱 중: {file_path.name} ({pct}%)"
                        )
                    return callback

                for entry in parser.parse_file(
                    file_path,
                    progress_callback=make_callback(i, len(files))
                ):
                    entries.append(entry)

            stats = parser.stats
            self._log(
                f"  파싱 완료: 유효 로그 {len(entries):,}건 "
                f"(JEUS:{stats['jeus']:,}, 앱:{stats['egov']:,}, "
                f"인식불가:{stats['unknown']:,})",
                "success",
            )

            if not entries:
                self._log("파싱된 로그가 없습니다. 파일 형식을 확인해주세요.", "error")
                return

            # ---- 2단계: 6가지 이상현상 분석 ----
            self._log("-" * 55)
            self._log("2단계: 이상현상 분석 중...")

            total_steps = 6

            # 요청 폭증
            self._update_progress(35, "요청 폭증 분석 중...")
            self._log("  [1/6] 요청 폭증 분석...")
            spike_records = SpikeAnalyzer().analyze(entries)
            self._log(f"        탐지: {len(spike_records)}건", "success" if spike_records else "info")

            if not self.is_running: return

            # 에러 패턴
            self._update_progress(48, "에러 패턴 분석 중...")
            self._log("  [2/6] 에러 패턴 분석...")
            error_records = ErrorAnalyzer().analyze(entries)
            self._log(f"        탐지: {len(error_records)}개 클래스", "success" if error_records else "info")

            if not self.is_running: return

            # 응답시간 지연
            self._update_progress(61, "응답시간 분석 중...")
            self._log("  [3/6] 응답시간 지연 분석...")
            response_records = ResponseTimeAnalyzer().analyze(entries)
            self._log(f"        탐지: {len(response_records)}건", "success" if response_records else "info")

            if not self.is_running: return

            # 비정상 접근
            self._update_progress(74, "비정상 접근 분석 중...")
            self._log("  [4/6] 비정상 접근 분석...")
            access_records = AccessAnalyzer().analyze(entries)
            self._log(f"        탐지: {len(access_records)}건", "success" if access_records else "info")

            if not self.is_running: return

            # 전자지갑 이상
            self._update_progress(84, "전자지갑 이상 분석 중...")
            self._log("  [5/6] 전자지갑 우회 접근 분석...")
            wallet_records = WalletAnalyzer().analyze(entries)
            self._log(f"        탐지: {len(wallet_records)}건", "success" if wallet_records else "info")

            if not self.is_running: return

            # 원서접수 흐름
            self._update_progress(91, "원서접수 흐름 분석 중...")
            self._log("  [6/6] 원서접수 흐름 이상 분석...")
            app_flow_records = ApplicationFlowAnalyzer().analyze(entries)
            self._log(f"        탐지: {len(app_flow_records)}건", "success" if app_flow_records else "info")

            # ---- 3단계: Excel 파일 저장 ----
            self._log("-" * 55)
            self._log("3단계: Excel 파일 저장 중...")
            self._update_progress(95, "Excel 파일 생성 중...")

            reporter = ExcelReporter()
            saved_path = reporter.save(
                output_path      = output_path,
                total_entries    = len(entries),
                parse_stats      = stats,
                spike_records    = spike_records,
                error_records    = error_records,
                response_records = response_records,
                access_records   = access_records,
                wallet_records   = wallet_records,
                app_flow_records = app_flow_records,
            )

            # ---- 완료 ----
            self._update_progress(100, "분석 완료!")
            self._log("=" * 55, "title")
            self._log("  분석 완료!", "success")
            self._log("=" * 55, "title")
            self._log(f"  저장 경로: {saved_path}", "info")
            self._log(f"  완료 시각: {datetime.now().strftime('%H:%M:%S')}", "info")
            self._log("")
            self._log("  [이상현상 탐지 요약]")
            self._log(f"    요청 폭증:     {len(spike_records):4d}건",
                      "warning" if spike_records else "info")
            self._log(f"    에러 패턴:     {len(error_records):4d}개 클래스",
                      "warning" if error_records else "info")
            self._log(f"    응답시간 지연: {len(response_records):4d}건",
                      "warning" if response_records else "info")
            self._log(f"    비정상 접근:   {len(access_records):4d}건",
                      "warning" if access_records else "info")
            self._log(f"    전자지갑 이상: {len(wallet_records):4d}건",
                      "error" if wallet_records else "info")
            self._log(f"    원서접수 이상: {len(app_flow_records):4d}건",
                      "error" if app_flow_records else "info")

            # 완료 메시지박스 (GUI 스레드에서 실행되도록 after 사용)
            self.root.after(
                100,
                lambda: messagebox.showinfo(
                    "분석 완료",
                    f"분석이 완료되었습니다!\n\n"
                    f"결과 파일:\n{saved_path}\n\n"
                    f"총 이상현상: "
                    f"{sum([len(spike_records), len(error_records), len(response_records), len(access_records), len(wallet_records), len(app_flow_records)])}건"
                )
            )

        except FileNotFoundError as e:
            self._log(f"파일 오류: {e}", "error")
            self.root.after(100, lambda: messagebox.showerror("파일 오류", str(e)))

        except PermissionError:
            msg = f"파일 저장 권한이 없습니다: {output_path}\n다른 경로를 선택해주세요."
            self._log(msg, "error")
            self.root.after(100, lambda: messagebox.showerror("저장 오류", msg))

        except Exception as e:
            import traceback
            err_detail = traceback.format_exc()
            self._log(f"오류 발생: {e}", "error")
            self._log(err_detail, "error")
            self.root.after(
                100,
                lambda: messagebox.showerror(
                    "오류 발생",
                    f"분석 중 오류가 발생했습니다:\n{e}\n\n"
                    "상세 내용은 결과 창을 확인해주세요."
                )
            )

        finally:
            # 분석 완료 또는 오류 시 항상 UI를 정상 상태로 복원합니다
            self.is_running = False
            self.root.after(100, lambda: self._set_ui_running(False))

    # ----------------------------------------------------------
    # UI 업데이트 헬퍼 함수들
    # (스레드에서 호출 시 root.after를 통해 GUI 스레드로 전달합니다)
    # ----------------------------------------------------------

    def _log(self, message: str, tag: str = "") -> None:
        """
        결과 텍스트 창에 메시지를 추가합니다.
        스레드 안전하도록 root.after()를 통해 메인 스레드에서 실행합니다.

        매개변수:
            message: 출력할 텍스트
            tag    : 색상 태그 ("info", "success", "warning", "error", "title")
        """
        def _do():
            self.result_text.config(state=tk.NORMAL)
            self.result_text.insert(tk.END, message + "\n", tag)
            self.result_text.see(tk.END)  # 자동 스크롤 (최신 로그가 보이도록)
            self.result_text.config(state=tk.DISABLED)

        self.root.after(0, _do)

    def _clear_result_text(self) -> None:
        """결과 텍스트 창을 비웁니다."""
        self.result_text.config(state=tk.NORMAL)
        self.result_text.delete("1.0", tk.END)
        self.result_text.config(state=tk.DISABLED)

    def _update_progress(self, value: int, message: str = "") -> None:
        """
        진행 상태 바와 레이블을 업데이트합니다.

        매개변수:
            value  : 0~100 사이의 진행률
            message: 진행 상태 설명 텍스트
        """
        def _do():
            self.progress_bar["value"] = value
            if message:
                self.progress_label.config(text=message)
                self.status_var.set(message)

        self.root.after(0, _do)

    def _set_ui_running(self, running: bool) -> None:
        """
        분석 실행 중/완료 상태에 따라 버튼 활성화 여부를 변경합니다.

        매개변수:
            running: True이면 실행 중 상태, False이면 대기 상태
        """
        if running:
            self.analyze_btn.config(state=tk.DISABLED, text="분석 중...")
            self.stop_btn.config(state=tk.NORMAL)
        else:
            self.analyze_btn.config(state=tk.NORMAL, text="분석 시작")
            self.stop_btn.config(state=tk.DISABLED)
            self.status_var.set("완료")

    def _on_close(self) -> None:
        """창 닫기 버튼을 눌렀을 때 확인 후 종료합니다."""
        if self.is_running:
            if not messagebox.askyesno(
                "분석 중",
                "분석이 진행 중입니다. 종료하시겠습니까?"
            ):
                return
        self.root.destroy()


# ============================================================
# 프로그램 시작점
# ============================================================

def main() -> None:
    """
    프로그램의 진입점(entry point)입니다.
    tkinter 윈도우를 만들고 앱을 시작합니다.
    """
    # tkinter 루트 윈도우 생성
    root = tk.Tk()

    # Windows에서 고해상도(HiDPI) 디스플레이 대응
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass  # Windows가 아니거나 지원하지 않으면 무시합니다

    # 앱 인스턴스 생성
    app = LogAnalyzerApp(root)

    # 이벤트 루프 시작 (이 줄부터 사용자 입력을 처리합니다)
    root.mainloop()


if __name__ == "__main__":
    # 이 파일을 직접 실행할 때만 main()을 호출합니다
    # (다른 파일에서 import했을 때는 실행되지 않습니다)
    main()
