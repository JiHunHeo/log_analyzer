#!/bin/bash
# 진단 스크립트 - 파싱이 안 될 때 원인을 찾아줍니다
cd "$(dirname "$0")"

# 가상환경 활성화
if [ -d "venv" ]; then
    source venv/bin/activate
fi

python3 - << 'PYEOF'
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tkinter import filedialog
import tkinter as tk

# 파일 선택 창 열기
root = tk.Tk()
root.withdraw()
filepath = filedialog.askopenfilename(
    title="진단할 로그 파일을 선택하세요",
    filetypes=[("로그 파일", "*.log *.txt *.out *.*")]
)
root.destroy()

if not filepath:
    print("파일을 선택하지 않았습니다.")
    input("\n아무 키나 누르면 종료...")
    sys.exit()

from pathlib import Path
path = Path(filepath)

print(f"파일: {path.name}")
print(f"크기: {path.stat().st_size / 1024 / 1024:.1f} MB")
print()

# 1. 인코딩 감지
print("=== 인코딩 감지 ===")
raw = path.read_bytes()[:5000]
for enc in ["cp949", "euc-kr", "utf-8", "utf-8-sig"]:
    try:
        decoded = raw.decode(enc)
        print(f"  {enc}: 성공 ✓")
    except Exception as e:
        print(f"  {enc}: 실패 ({e})")

print()

# 2. 실제 첫 5줄 출력 (cp949로)
print("=== 파일 첫 5줄 (cp949 인코딩) ===")
try:
    with path.open(encoding="cp949", errors="replace") as f:
        for i, line in enumerate(f):
            if i >= 5:
                break
            print(f"  [{i+1}] {repr(line[:100])}")
except Exception as e:
    print(f"  오류: {e}")

print()

# 3. 패턴 매칭 테스트
import re
JEUS = re.compile(
    r'^\[(\d{4}\.\d{2}\.\d{2}\s+\d{2}:\d{2}:\d{2}:\d{3})\]'
    r'\[(\d+)\]\s+\[([^\]]+)\]\s+(?:\[([^\]]*)\]\s+)?(?:<([^>]+)>\s+)?(.+)$'
)
EGOV = re.compile(
    r'^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}),\s*(\d+)\s+'
    r'(DEBUG|INFO|WARN|WARNING|ERROR|FATAL)\s+'
    r'[\[\{]([^\.\]\}]+\.java)\((\d+)\)[\]\}]\s*(.+)$'
)

print("=== 첫 20줄 패턴 매칭 테스트 ===")
matched = 0
with path.open(encoding="cp949", errors="replace") as f:
    for i, raw_line in enumerate(f):
        if i >= 20:
            break
        line = raw_line.rstrip("\n\r")
        if not line.strip():
            continue
        j = "JEUS" if JEUS.match(line) else ""
        e = "EGOV" if EGOV.match(line) else ""
        result = j or e or "X(인식불가)"
        if j or e:
            matched += 1
        print(f"  [{result}] {repr(line[:80])}")

print()
print(f"첫 20줄 중 {matched}줄 파싱 성공")

input("\n아무 키나 누르면 종료...")
PYEOF
