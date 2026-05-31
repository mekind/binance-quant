# money-maker docs

Binance spot 스윙 퀀트 트레이딩 시스템 문서.

## 읽는 순서

1. **[01-architecture.md](01-architecture.md)** — 레이어 구조, 의존 방향, 데이터 흐름
2. **[02-modules.md](02-modules.md)** — 파일별 책임, API, 결정사항
3. **[03-workflow.md](03-workflow.md)** — 셋업, 일상 흐름, 새 전략 추가법, 결과 해석
4. **[04-roadmap.md](04-roadmap.md)** — 미션(스윙·실제수익·B&H 벤치마크), 스테이지, KPI
5. **[05-service-flow.md](05-service-flow.md)** — 서비스 플로우 다이어그램 (리서치·라이브·킬스위치)
6. **[06-why-swing-not-scalping.md](06-why-swing-not-scalping.md)** — 단타 대신 스윙을 택한 근거
7. **[07-how-quant-firms-work.md](07-how-quant-firms-work.md)** — 전문 퀀트 회사 운영 방식 + 우리가 채택/포기할 것

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

- **미션 개정 (2026-05-31)**: 1분봉 단타 → **스윙(4h~1d) 기반 실제 수익**. 근거는 [06-why-swing-not-scalping.md](06-why-swing-not-scalping.md)
- **구축 완료**: 백테스트·검증·실시간·리스크 인프라 (단타 기준으로 지어졌으나 타임프레임 독립적이라 재사용)
- **현재 위치**: 새 무대에서 **재출발** — B&H 벤치마크 추가 + 다년치 데이터로 전 전략 재검증 ([04-roadmap.md](04-roadmap.md) Stage 1)

## 핵심 원칙

1. **실거래 코드는 항상 Testnet 먼저** — `BINANCE_TESTNET=true`가 기본값
2. **백테스트는 항상 부풀려진다** — walk-forward와 페이퍼 트레이딩 없이 라이브 금지
3. **`.env` 절대 커밋 금지** — `.gitignore`에 등록되어 있지만 다시 확인
4. **Look-ahead bias 차단** — 엔진은 next-bar open에서 체결
5. **수수료 0.1% 항상 적용** — Binance taker 기본값, 0으로 하면 환상에 빠짐
