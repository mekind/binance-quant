# money-maker docs

Binance spot 단타 퀀트 트레이딩 시스템 문서.

## 읽는 순서

1. **[01-architecture.md](01-architecture.md)** — 레이어 구조, 의존 방향, 데이터 흐름
2. **[02-modules.md](02-modules.md)** — 파일별 책임, API, 결정사항
3. **[03-workflow.md](03-workflow.md)** — 셋업, 일상 흐름, 새 전략 추가법, 결과 해석
4. **[04-roadmap.md](04-roadmap.md)** — 현재 위치(Stage 1), 다음 마일스톤

## 빠른 참조

```bash
# 셋업 (최초 1회)
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# 동작 확인
pytest                                            # 스모크 테스트
mm info                                           # 설정 확인
mm download --start 2025-01-01 --end 2025-02-01   # 1달치 BTCUSDT 1m
mm backtest --fast 12 --slow 26                   # 백테스트
```

## 현재 상태

- **Stage 1 완료**: 오프라인 백테스트 인프라
- **다음**: Stage 2 — 전략 다양화 (변동성 돌파, RSI 평균회귀)
- **실거래까지**: Stage 6 (Walk-forward 검증 + Testnet 페이퍼 4주 후)

## 핵심 원칙

1. **실거래 코드는 항상 Testnet 먼저** — `BINANCE_TESTNET=true`가 기본값
2. **백테스트는 항상 부풀려진다** — walk-forward와 페이퍼 트레이딩 없이 라이브 금지
3. **`.env` 절대 커밋 금지** — `.gitignore`에 등록되어 있지만 다시 확인
4. **Look-ahead bias 차단** — 엔진은 next-bar open에서 체결
5. **수수료 0.1% 항상 적용** — Binance taker 기본값, 0으로 하면 환상에 빠짐
