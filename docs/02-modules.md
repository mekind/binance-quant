# 모듈 레퍼런스

각 파일이 무엇을, 왜, 어떻게 하는지.

---

## `config.py`

**역할**: `.env` 로딩 + 프로젝트 경로 상수 제공.

```python
from money_maker.config import settings, DATA_RAW
print(settings.default_symbol)  # "BTCUSDT"
```

| 필드 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| `binance_api_key` | str | "" | API 키 (실거래/Testnet) |
| `binance_api_secret` | str | "" | API 시크릿 |
| `binance_testnet` | bool | True | True면 Testnet 라우팅 |
| `default_symbol` | str | "BTCUSDT" | CLI 기본 심볼 |
| `default_interval` | str | "1m" | CLI 기본 주기 |
| `max_position_usdt` | float | 100 | 리스크 한도 (라이브용) |
| `max_daily_loss_usdt` | float | 20 | 일일 손실 컷 |

**경로**: `DATA_RAW = ROOT/data/raw`, `DATA_PROCESSED = ROOT/data/processed`.

---

## `data/downloader.py`

**역할**: Binance 공개 REST에서 캔들을 받아 Parquet으로 저장.

### 주요 함수

```python
download_klines(symbol, interval, start, end=None) -> Path
load_klines(symbol, interval) -> pd.DataFrame
```

- **인증 불필요** — 시장 데이터는 퍼블릭 엔드포인트
- **재시도 내장** — `tenacity`로 5회, exponential backoff
- **레이트리밋** — 청크당 250ms sleep (Binance 1200 req/min 한도 안전)
- **청크 크기** — 1000봉 (Binance 하드캡)
- **인덱스** — `open_time` UTC datetime
- **컬럼** — open, high, low, close, volume, quote_volume, trades, taker_buy_base, taker_buy_quote, close_time

### 출력 예시

```
data/raw/BTCUSDT_1m.parquet   # 1달 1분봉 ≈ 5MB, 44k 행
```

### 한계

- 단일 심볼/주기씩만 받음 (병렬화 안 됨)
- 갭 탐지 안 함 (Binance 휴장 없으니 보통 문제 없음)

---

## `strategies/`

### `base.py` — Strategy ABC

```python
class Strategy(ABC):
    name: str
    @abstractmethod
    def signals(self, df: pd.DataFrame) -> pd.Series: ...
```

**계약**:
- 입력: OHLCV DataFrame (인덱스 = datetime)
- 출력: `df.index`와 정렬된 Series, 값은 `{-1, 0, +1}` (spot은 0/+1)
- **Look-ahead 금지** — bar `t`의 시그널 계산에 `t+1`의 데이터를 쓰면 백테스트가 거짓말함

### `ema_cross.py` — EMA 크로스오버

```python
EmaCross(fast=12, slow=26).signals(df)
```

- 빠른 EMA > 느린 EMA → +1 (long), 아니면 0 (flat)
- `pandas.ewm(span=N, adjust=False)` — 표준 지수 가중
- **베이스라인용**. 단독으론 보통 수수료 못 이김 — 다른 전략 비교 기준으로 쓰세요

---

## `backtest/engine.py`

**역할**: 벡터화 백테스터. 시그널 → 성과 지표.

### 핵심 결정사항

1. **Next-bar open 체결** — `position[t] = signal[t-1]`. 봉 종가 보고 그 봉에서 사면 look-ahead
2. **수익률 정의** — `bar_ret[t] = open[t+1]/open[t] - 1`. 진입/청산이 둘 다 open이라 일관됨
3. **수수료** — 포지션 변화 1당 `fee` 차감 (진입+청산 모두 부과)
4. **샤프 연환산** — 봉 간격에서 자동 추론 (1분봉이면 `√(525,600)`)

### 결과 객체

```python
@dataclass
class BacktestResult:
    equity: pd.Series         # 자본곡선 (시작 1.0)
    returns: pd.Series        # 봉별 net 수익률
    positions: pd.Series      # 실제 보유 포지션
    trades: int               # 진입 횟수
    total_return: float
    sharpe: float
    max_drawdown: float
    win_rate: float           # 트레이드 단위 승률
```

### 알려진 단순화

- 슬리피지 모델 없음 (수수료 인상으로 근사하세요)
- 부분 체결 없음
- 펀딩비 없음 (spot이라 무관)
- 사이즈 = 자본 100% (켈리/고정비율 사이저 미구현)

---

## `cli.py`

**역할**: Typer 기반 사용자 진입점. `pyproject.toml`에서 `mm` 명령으로 등록.

| 명령 | 설명 |
|------|------|
| `mm download --symbol BTCUSDT --interval 1m --start 2025-01-01` | 캔들 다운로드 |
| `mm backtest --fast 12 --slow 26` | EMA 백테스트 실행 |
| `mm info` | 로드된 설정 출력 (시크릿은 마스킹) |

---

## `tests/`

**철학**: 네트워크/디스크 없이 돌아야 함. 합성 데이터로 백테스터 invariant만 확인.

- `test_ema_cross_runs_and_produces_valid_result` — 시그널 형식, drawdown 범위, equity 시작값
- `test_zero_signal_is_flat` — 시그널이 전부 0이면 거래 0, PnL 0
