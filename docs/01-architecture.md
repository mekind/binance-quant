# 아키텍처 개요

money-maker는 **레이어 분리형 모놀리스**입니다. 각 레이어는 한 방향으로만 의존하며, 위 레이어를 교체해도 아래는 영향 받지 않습니다.

## 레이어 다이어그램

```
┌─────────────────────────────────────────────┐
│  cli.py            (Typer 명령어 진입점)      │
└───────────────┬─────────────────────────────┘
                │
        ┌───────┴────────┐
        ▼                ▼
┌───────────────┐  ┌──────────────────┐
│  strategies/  │  │  backtest/       │
│  - base       │  │  - engine        │
│  - ema_cross  │  │                  │
└───────┬───────┘  └────────┬─────────┘
        │                   │
        └───────┬───────────┘
                ▼
        ┌──────────────┐
        │   data/      │
        │ - downloader │   ← Binance REST
        └──────┬───────┘
               ▼
        ┌──────────────┐
        │  config.py   │   ← .env, pydantic-settings
        └──────────────┘
```

**의존 방향 규칙**: 위에서 아래로만. `data/`가 `strategies/`를 임포트하면 안 됩니다.

## 데이터 흐름

```
Binance REST  →  downloader  →  Parquet (data/raw/)
                                     │
                                     ▼
                                load_klines()
                                     │
                                     ▼
                              DataFrame (OHLCV)
                                     │
                          ┌──────────┴──────────┐
                          ▼                     ▼
                    Strategy.signals()    backtest.engine
                          │                     │
                          └──────────┬──────────┘
                                     ▼
                              BacktestResult
                                     │
                                     ▼
                                 CLI 출력
```

## 모듈 책임

| 모듈 | 책임 | 절대 하면 안 되는 것 |
|------|------|--------------------|
| `config.py` | .env 로딩, 경로 상수 | 도메인 로직 |
| `data/downloader.py` | Binance REST → Parquet | 시그널 계산, 거래 |
| `strategies/*` | OHLCV → 포지션 시그널 | 데이터 다운로드, 백테스트 수행 |
| `backtest/engine.py` | 시그널 + OHLCV → 성과 지표 | 외부 API 호출 |
| `cli.py` | 사용자 명령 라우팅 | 비즈니스 로직 (전부 위임) |

## 왜 이렇게 나눴나

- **테스트 가능성** — 백테스터는 합성 데이터로 검증 가능 (`tests/test_backtest.py`). 네트워크 의존 없음
- **전략 교체 용이** — `Strategy` ABC만 구현하면 새 전략 추가
- **라이브 전환 준비** — 나중에 `live/executor.py`를 추가해도 `strategies/`는 그대로 재사용
- **데이터 캐싱** — Parquet 파일이 캐시 역할. 한 번 다운로드하면 백테스트 반복 시 네트워크 불필요
