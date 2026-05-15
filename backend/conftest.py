import sys
import os

# backend/ 디렉터리를 sys.path에 추가
# 프로젝트 루트에서 pytest를 실행해도 from models.xxx, from services.xxx 등 import가 동작한다
sys.path.insert(0, os.path.dirname(__file__))
