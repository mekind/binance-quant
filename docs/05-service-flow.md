# 서비스 플로우

money-maker는 CLI(`mm`) 하나로 **오프라인 리서치/검증**과 **라이브/페이퍼 트레이딩** 두 파이프라인을 묶습니다. 이 문서는 각 플로우를 Mermaid 다이어그램으로 정리합니다.

> 코드 기준: Stage 5 (리스크 매니저 포함). 백테스트 → 검증 → Testnet 페이퍼까지 동작.

## 1. 전체 개요

```mermaid
flowchart TB
    User([User]) -->|mm CLI| CLI{{cli.py · Typer}}

    subgraph RESEARCH["🔬 오프라인 리서치/검증"]
        direction TB
        DL[mm download<br/>downloader.py] -->|Parquet| DATA[(data/raw/*.parquet)]
        DATA --> BT[mm backtest / compare<br/>backtest/engine.py]
        DATA --> VAL[mm grid / walkforward<br/>mc / feesweep<br/>validation/]
        STRAT[strategies/registry<br/>ema_cross·vol_breakout<br/>rsi_mr·bbands_atr] --> BT
        STRAT --> VAL
        BT --> REP[리포트/플롯<br/>summary · PNG]
        VAL --> REP
    end

    subgraph LIVE["⚡ 라이브 / 페이퍼 트레이딩"]
        direction TB
        WS[Binance WS<br/>ws_client.py] --> RUN[run_live<br/>runner.py]
        STRAT2[strategy] --> RUN
        RUN --> EXEC[PaperExecutor<br/>+ RiskManager]
        EXEC --> ROUTER{OrderRouter}
        ROUTER -->|sim| SIM[SimulatedRouter]
        ROUTER -->|testnet| TN[BinanceTestnetRouter<br/>REST 주문]
    end

    KILL[mm kill<br/>kill.py] -->|패닉 청산| ROUTER

    CLI --> RESEARCH
    CLI --> LIVE
    CLI --> KILL
```

## 2. 오프라인 리서치 플로우

`download` → 전략 시그널 → 백테스트 → (선택) 검증. 모두 네트워크 의존이 없고(`download` 제외) 재현 가능합니다.

```mermaid
flowchart LR
    DL[mm download] -->|REST 캔들| PARQ[(data/raw/*.parquet)]
    PARQ --> LOAD[load_klines<br/>DataFrame OHLCV]
    REG[registry.build<br/>전략 선택] --> SIG[strategy.signals]
    LOAD --> SIG
    SIG --> ENG[run_backtest<br/>next-bar-open · fee]
    ENG --> RES[BacktestResult<br/>sharpe·mdd·win·trades]

    LOAD --> GRID[grid_search<br/>파라미터 스윕]
    LOAD --> WF[walk_forward<br/>OOS 검증]
    LOAD --> MC[montecarlo_shuffle<br/>유의성]
    LOAD --> FEE[fee_sweep<br/>수수료 민감도]

    RES --> OUT[CLI 표 / PNG 리포트]
    GRID --> OUT
    WF --> OUT
    MC --> OUT
    FEE --> OUT
```

| 명령 | 모듈 | 산출물 |
|------|------|--------|
| `mm backtest` | `backtest/engine.py` | 단일 성과 요약 + 선택적 PNG |
| `mm compare` | `backtest/engine.py` | 전 전략 비교 표 |
| `mm grid` | `validation/sensitivity.py` | Sharpe 상위 파라미터 조합 |
| `mm walkforward` | `validation/walkforward.py` | 롤링 윈도우 OOS Sharpe |
| `mm mc` | `validation/montecarlo.py` | 수익률 셔플 분포 대비 관측값 |
| `mm feesweep` | `validation/fees.py` | 수수료 레벨별 성과 |

## 3. 라이브 트레이딩 파이프라인

WS 피드 → 시그널 엔진 → 페이퍼 체결 → 라우터. 리스크 매니저(사이저 + 일일 손실 컷)가 항상 진입 경로에 끼어듭니다.

```mermaid
flowchart LR
    subgraph FEED["피드"]
        BWS[(Binance Kline WS<br/>testnet/prod)]
        BWS --> KS[kline_stream<br/>자동 재연결·백오프]
        KS -->|KlineEvent| RUN
    end

    subgraph ENGINE["시그널 엔진"]
        RUN[run_live runner] -->|on_kline| SE[SignalEngine]
        SE -->|is_closed 봉만<br/>버퍼 N개| DF[DataFrame 재구성]
        DF --> SIG[strategy.signals]
        SIG --> CMP{desired_position<br/>≠ last?}
        CMP -->|동일| SKIP[무시 / 멱등]
        CMP -->|변경| SEV[SignalEvent<br/>+ ATR]
    end

    subgraph EXECUTION["체결 + 리스크"]
        SEV --> EX[PaperExecutor.on_signal]
        EX --> RG{RiskManager}
        RG -->|allow_entry?<br/>DailyLossGuard| GATE{일일 손실<br/>한도 초과?}
        GATE -->|차단| BLOCK[진입 차단]
        GATE -->|허용| SZ[size_for<br/>Fixed / ATR sizer]
        SZ --> ORD[router.buy / sell]
        ORD --> R1[SimulatedRouter]
        ORD --> R2[BinanceTestnetRouter]
        ORD --> TR[Trade 기록<br/>PnL·슬리피지]
        TR -->|on_trade_closed| RG
    end
```

## 4. 시그널 → 주문 시퀀스 (한 사이클)

```mermaid
sequenceDiagram
    participant WS as kline_stream
    participant R as run_live
    participant SE as SignalEngine
    participant ST as Strategy
    participant EX as PaperExecutor
    participant RM as RiskManager
    participant RT as OrderRouter

    WS->>R: KlineEvent (봉 마감)
    R->>SE: on_kline(event)
    SE->>SE: 봉 버퍼 추가 (warmup 확인)
    SE->>ST: signals(df)
    ST-->>SE: position 시계열
    alt 포지션 변경 없음
        SE-->>R: None (무시)
    else 진입 신호 (0→1)
        SE-->>EX: SignalEvent(+ATR)
        EX->>RM: allow_entry(now)?
        alt 일일 손실 한도 초과
            RM-->>EX: False → 진입 차단
        else 허용
            RM->>RM: size_for(price, atr)
            EX->>RT: buy(symbol, quote, price)
            RT-->>EX: Order(filled)
        end
    else 청산 신호 (1→0)
        SE-->>EX: SignalEvent
        EX->>RT: sell(symbol, qty, price)
        RT-->>EX: Order(filled)
        EX->>EX: Trade 기록 (PnL·슬리피지)
        EX->>RM: on_trade_closed(trade)
    end
```

## 5. 킬스위치 플로우

`mm kill`은 봇의 in-memory 상태가 아니라 **거래소 잔고**를 조회해 전량 시장가 청산합니다. 러너 가동 여부와 무관한 패닉 버튼입니다.

```mermaid
flowchart LR
    CLI[mm kill --symbol] --> LIQ[liquidate]
    LIQ --> BAL[router.get_free_balance<br/>base 자산 조회]
    BAL --> CHK{free > dust?}
    CHK -->|No| NOOP[청산할 것 없음]
    CHK -->|Yes| SELL[router.sell 전량<br/>MARKET]
    SELL --> DONE[체결 결과 출력]
```

## 6. 핵심 설계 포인트

- **멱등성 이중 방어** — `SignalEngine`이 포지션 변화 시에만 이벤트를 내보내고, `PaperExecutor`가 다시 현재 포지션과 비교해 중복 주문을 막습니다. (REST 폴링·리플레이 같은 미래 입력 소스 대비)
- **라우터 추상화** — `OrderRouter` 프로토콜로 `SimulatedRouter`(네트워크 없음)와 `BinanceTestnetRouter`(실제 REST)를 동일 인터페이스로 교체 (`--router sim|testnet`).
- **리스크 관리 분리** — `PositionSizer`(Fixed/ATR) + `DailyLossGuard`를 `RiskManager`가 합성. 순수·동기 함수라 이벤트 루프/클럭 없이 단위 테스트 가능.
- **킬스위치 독립성** — 거래소 잔고 기준 청산이라 러너가 죽어도 동작. 러너는 별도로 Ctrl-C로 종료.
- **Look-ahead 차단** — 백테스트는 next-bar-open 체결 + `shift`로 미래 정보 누수를 막고, 라이브는 `is_closed` 봉만 처리.
- **Testnet 우선** — `BINANCE_TESTNET=true`가 기본값. 실거래 코드는 항상 Testnet에서 먼저 검증.

## 관련 문서

- [01-architecture.md](01-architecture.md) — 레이어 구조, 의존 방향
- [02-modules.md](02-modules.md) — 파일별 책임
- [03-workflow.md](03-workflow.md) — 셋업·일상 흐름
- [04-roadmap.md](04-roadmap.md) — 마일스톤
