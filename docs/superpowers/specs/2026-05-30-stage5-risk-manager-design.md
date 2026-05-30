# Stage 5 — 리스크 매니저 설계

작성일: 2026-05-30
상태: 승인됨

## 목표

라이브 페이퍼 트레이딩 파이프라인(Stage 4)에 안전 장치를 추가한다. 실거래(Stage 6)
진입 전 필수 조건. 단일 심볼 아키텍처를 유지하면서 포지션 사이징, 일일 손실 컷,
킬 스위치, 슬리피지 측정을 구현한다.

## 설계 결정 (확정)

1. **포지션 사이저**: 고정비율 + ATR 기반(변동성 타게팅). Kelly는 보류(거래 이력 통계 인프라 필요).
2. **킬 스위치**: 별도 CLI 명령 `mm kill`. 실행 중인 봇과 독립. 거래소측 잔고를 청산.
3. **범위**: 단일 심볼 유지(동시 포지션 한도는 0/1 포지션에 자명). 슬리피지 측정 포함.

## 아키텍처

### 새 모듈: `src/money_maker/live/risk.py`

```
PositionSizer (Protocol: size(price: float, atr: float | None) -> float)  # 반환=quote USDT
├─ FixedFractionSizer(max_position_usdt)
│     size() = max_position_usdt  (항상 전액 — 기존 동작 보존)
└─ AtrSizer(max_position_usdt, target_vol_pct=0.005)
      vol = atr / price                         # 봉당 변동성 비율
      size = max_position_usdt * min(1.0, target_vol_pct / vol)
      # atr 없거나 vol<=0 이면 max_position_usdt 전액 (안전 폴백)
      # 변동성이 target보다 클수록 포지션 축소, 절대 max를 넘지 않음

DailyLossGuard(max_daily_loss_usdt)
├─ _day: date | None          # 현재 추적 중인 UTC 날짜
├─ _cum_pnl: float            # 그날 누적 실현 손익
├─ record(pnl: float, now: datetime) -> None
│     now.date() 가 _day와 다르면 리셋 후 누적
├─ can_trade(now: datetime) -> bool
│     날짜 바뀌면 리셋. _cum_pnl > -max_daily_loss_usdt 이면 True
└─ 한도 0이면 무제한(항상 True)

RiskManager(sizer: PositionSizer, daily_guard: DailyLossGuard)
├─ allow_entry(now) -> bool        # = daily_guard.can_trade(now)
├─ size_for(price, atr) -> float   # = sizer.size(price, atr)
└─ on_trade_closed(trade, now)     # daily_guard.record(trade.pnl_quote, now)
```

### 기존 파일 수정

**`signal_engine.py`**
- `SignalEvent`에 `atr: float | None` 필드 추가.
- `SignalEngine.on_kline`이 봉 버퍼로 ATR(period=14) 계산해 이벤트에 실음.
- ATR = 단순이동평균(True Range). TR = max(high-low, |high-prev_close|, |low-prev_close|).
- 봉이 period+1개 미만이면 atr=None.

**`paper_executor.py`**
- `PaperExecutor`에 `risk: RiskManager | None = None` 필드.
- 진입(BUY) 신호:
  - `risk and not risk.allow_entry(ev.timestamp)` → 진입 스킵 + 경고 로그(일일 손실 컷).
  - 주문 금액 = `risk.size_for(ev.last_close, ev.atr)` (risk 없으면 `max_position_usdt`).
- 청산(SELL) 신호: 항상 허용(리스크 차단과 무관하게 보유분은 닫을 수 있어야 함).
  - 청산 후 `risk.on_trade_closed(trade, ev.timestamp)` 호출.
- `Trade`에 `entry_slip_bps: float`, `exit_slip_bps: float` 추가.
  - slip_bps = (체결가 / 시그널가 - 1) * 1e4
  - 진입: 시그널가 = 진입 SignalEvent.last_close, 체결가 = 진입 order.avg_price
  - 청산: 시그널가 = 청산 SignalEvent.last_close, 체결가 = 청산 order.avg_price
  - 진입 시그널가를 닫을 때까지 보관(`open_signal_price` 필드).

**`router.py`**
- `OrderRouter` Protocol에 `get_free_balance(asset: str) -> float` 추가.
- `SimulatedRouter`: 내부 `holdings: dict[str, float]` 추적. buy 시 base += qty, sell 시 base -= qty. `get_free_balance(asset)`는 holdings 반환.

**`testnet_router.py`**
- `_signed_get(path, params)` 헬퍼 추가(서명 GET).
- `get_free_balance(asset)`: GET `/api/v3/account` → 해당 자산 free 잔고(float).

### CLI (`cli.py`)

**`mm kill`** (신규)
```
mm kill --symbol BTCUSDT --router testnet
```
1. 라우터 생성(testnet 또는 sim).
2. base 자산 = symbol에서 quote(settings.base_quote) 떼어낸 것. 예: BTCUSDT → BTC.
3. `get_free_balance(base)` 조회.
4. dust(예: 1e-8) 초과면 전량 `router.sell(symbol, free, ref_price=0)`.
5. 청산 수량/체결가 출력. 잔고 0이면 "nothing to liquidate".
6. **실행 중 봇과 독립** — 거래소측 포지션만 비운다. 봇 자체는 Ctrl-C로 종료.

**`mm live`** (수정)
- 옵션 추가: `--sizer fixed|atr` (기본 fixed), `--target-vol FLOAT` (기본 0.005).
- RiskManager 자동 배선: 선택한 사이저 + DailyLossGuard(settings.max_daily_loss_usdt).
- PaperExecutor에 risk 주입.
- 종료 시 슬리피지 요약 출력(평균 entry/exit slip bps).

## 데이터 흐름

```
WS → SignalEngine(ATR 계산) → SignalEvent{desired_position, last_close, atr}
   → PaperExecutor
        진입: RiskManager.allow_entry? → size_for(price, atr) → router.buy
        청산: router.sell → Trade(slip 기록) → RiskManager.on_trade_closed
```

## 에러 처리

- ATR=None(워밍업 부족): AtrSizer는 전액 폴백. 슬리피지는 정상 계산.
- 일일 손실 한도 0: 무제한(가드 비활성).
- 킬 스위치 잔고 0: no-op, 정상 종료.
- 킬 스위치 testnet 인증 실패: httpx 예외 전파(사용자에게 보임).

## 테스트 (`tests/test_risk.py`)

- `FixedFractionSizer` 항상 전액 반환.
- `AtrSizer`: 변동성↑ → 사이즈↓, 절대 max 초과 안 함, atr=None 폴백.
- `DailyLossGuard`: 한도 도달 시 차단, UTC 자정 리셋, 한도 0이면 항상 허용.
- 슬리피지: SimulatedRouter 경로 0 bps, 가짜 체결가 주입 시 bps 정확.
- 킬 스위치: sim holdings 청산 후 잔고 0, 빈 잔고 no-op.
- 통합: 손실 한도 트립 후 신규 진입 차단되지만 청산은 허용.

기존 55개 테스트는 모두 통과 유지(하위 호환: risk=None이면 기존 동작).

## 비범위 (Stage 5에서 안 함)

- Kelly 사이저 (거래 이력 통계 인프라 선행 필요).
- 멀티 심볼 / 진짜 동시 포지션.
- 실행 중 봇의 파일 플래그 감시(킬은 CLI 독립 청산으로 충분).
- 슬리피지를 사이징에 피드백(측정만, 자동 조정 안 함).
