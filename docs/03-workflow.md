# 개발 워크플로우

## 환경 셋업 (최초 1회)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

`.env`는 처음엔 비워둬도 됩니다. 백테스트는 API 키 없이 동작합니다.

## 일상 흐름

```
1. 데이터 다운로드   →  mm download ...
2. 백테스트 반복     →  mm backtest --fast X --slow Y
3. 노트북 분석       →  jupyter lab notebooks/
4. 새 전략 추가      →  src/money_maker/strategies/<name>.py
5. 테스트            →  pytest
6. (라이브는 아직)
```

## 새 전략 추가하기

1. `src/money_maker/strategies/<name>.py` 생성

```python
from .base import Strategy
import pandas as pd

class VolBreakout(Strategy):
    name = "vol_breakout"

    def __init__(self, lookback: int = 20, k: float = 1.5):
        self.lookback = lookback
        self.k = k

    def signals(self, df: pd.DataFrame) -> pd.Series:
        prev_range = (df["high"] - df["low"]).shift(1).rolling(self.lookback).mean()
        target = df["open"] + self.k * prev_range
        return (df["high"] > target).astype(int)
```

2. `cli.py` `backtest` 명령에 `--strategy` 옵션 추가하거나 별도 명령 등록
3. `tests/`에 합성 데이터 스모크 테스트 작성
4. `pytest`로 통과 확인

## 백테스트 결과 해석

| 지표 | 좋은 신호 | 나쁜 신호 |
|------|-----------|-----------|
| `trades` | 너무 많으면(>1000/월) 수수료에 잡아먹힘 | 너무 적으면(<10) 통계 무의미 |
| `sharpe` | >1.5 (수수료 후) | <0.5는 무작위와 다를 바 없음 |
| `max_drawdown` | -10% 이내 | -30% 넘으면 라이브에서 못 버팀 |
| `win_rate` | 단타는 50~60% 흔함 | 80% 넘으면 의심 (룩어헤드?) |
| `total_return` | 백테스트는 항상 부풀려짐 | - |

**경고**: 단일 백테스트 결과는 거의 항상 과적합입니다. **walk-forward** 또는 **out-of-sample**로 검증하세요 (다음 마일스톤).

## 자주 하는 실수

| 실수 | 결과 | 방지 |
|------|------|------|
| 종가 보고 그 봉에서 체결 | look-ahead, 백테스트 환상적으로 보임 | engine은 자동으로 next-bar open 사용 |
| 수수료 0으로 설정 | 단타 전략이 다 통과해 보임 | `fee=0.001` 유지 |
| In-sample만 튜닝 | 라이브 가면 망함 | 다음 단계에 walk-forward 도입 예정 |
| `.env` 커밋 | API 키 유출 | `.gitignore`에 이미 등록됨 |

## 디버깅

```bash
# 백테스터 동작 확인
pytest tests/ -v

# 다운로드 로그 보기
mm download --symbol BTCUSDT --interval 1m --start 2025-01-01 --end 2025-01-02

# 설정 확인
mm info
```
