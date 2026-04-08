"""
Noto Sans KR 폰트 다운로드 스크립트
실행: python download_fonts.py
"""
import os
import urllib.request

FONT_DIR = os.path.join(os.path.dirname(__file__), "assets", "fonts")
os.makedirs(FONT_DIR, exist_ok=True)

FONTS = {
    "NotoSansKR-Regular.ttf": (
        "https://github.com/google/fonts/raw/main/ofl/notosanskr/NotoSansKR%5Bwght%5D.ttf"
    ),
}

# GitHub Releases에서 직접 다운로드 (더 안정적)
FONTS_DIRECT = {
    "NotoSansKR-Regular.ttf": "https://fonts.gstatic.com/ea/notosanskr/v2/NotoSansKR-Regular.otf",
}


def download_font(filename: str, url: str):
    filepath = os.path.join(FONT_DIR, filename)
    if os.path.exists(filepath):
        print(f"[이미 존재] {filename}")
        return

    print(f"다운로드 중: {filename} ...")
    try:
        urllib.request.urlretrieve(url, filepath)
        print(f"완료: {filepath}")
    except Exception as e:
        print(f"실패: {e}")
        print(f"수동으로 {url} 에서 다운로드하여 {FONT_DIR}에 저장해주세요.")


if __name__ == "__main__":
    print(f"폰트 저장 경로: {FONT_DIR}")
    print()
    print("Noto Sans KR 폰트를 수동으로 다운로드하세요:")
    print("1. https://fonts.google.com/noto/specimen/Noto+Sans+KR")
    print("2. 'Download family' 클릭")
    print(f"3. TTF 파일을 {FONT_DIR} 에 저장")
    print(f"   - NotoSansKR-Regular.ttf")
    print(f"   - NotoSansKR-Bold.ttf")
    print()
    print("※ 폰트 없이도 서비스는 동작하지만 한글이 제대로 표시되지 않을 수 있습니다.")
