# 로드맵

현재 위치는 **Stage 1: 오프라인 검증**. 실거래까진 한참 남았습니다.

## Stage 1 — 오프라인 검증 ✅ (현재)

- [x] 프로젝트 스캐폴딩
- [x] Binance REST 다운로더 → Parquet
- [x] 벡터화 백테스터 (next-bar open, 수수료)
- [x] EMA 크로스 베이스라인
- [x] 합성 데이터 스모크 테스트

## Stage 2 — 전략 다양화 ✅

목표: 비교 가능한 전략 3개 이상.

- [x] **변동성 돌파** (Larry Williams) — rolling 변동성 × k 돌파 시 진입
- [x] **RSI 평균회귀** — 상태머신 (oversold → long → exit_level → flat)
- [x] 전략 레지스트리 (`registry.build(name, **params)`)
- [x] 전략 비교 리포트 (`mm compare`)
- [x] **볼린저 밴드 + ATR 손절** — 하단 밴드 진입, 중앙 회귀 또는 ATR×k 손절
- [x] 백테스트 결과 시각화 (equity curve, drawdown, monthly returns 히트맵) — `--plot-dir`

## Stage 3 — 견고성 검증 ✅

단일 백테스트는 거의 항상 과적합. 진짜 통계적 우위인지 검증.

- [x] **Walk-forward 분석** — 롤링 윈도우로 train/test 반복 (`mm walkforward`)
- [x] **파라미터 민감도** — 그리드 서치 + 결과 분포 (`mm grid`)
- [x] **Monte Carlo 셔플** — 리턴 순서 섞어 무작위 대비 우위 확인 (`mm mc`)
- [x] **거래비용 민감도** — fee 스윕 (`mm feesweep`)

## Stage 4 — 실시간 인프라 ⬜

여기서부터 위험 영역. **무조건 Testnet부터.**

- [ ] Binance WebSocket 클라이언트 (kline, depth, trades 스트림)
- [ ] 실시간 시그널 엔진 — 봉 종가 확정 시 strategy 호출
- [ ] **페이퍼 트레이더** — Binance Testnet에 실제 주문 (실돈 X)
- [ ] 주문 상태 머신 (NEW → PARTIALLY_FILLED → FILLED → CLOSED)
- [ ] 재연결/이중화 (WebSocket 끊김 처리)

## Stage 5 — 리스크 매니저 ⬜

- [ ] 포지션 사이저 (고정비율 → Kelly 일부 → ATR 기반)
- [ ] 일일 손실 컷 (`max_daily_loss_usdt` 도달 시 거래 중단)
- [ ] 동시 포지션 한도
- [ ] **킬 스위치** — 단일 명령으로 모든 포지션 청산
- [ ] 체결 슬리피지 측정 (실제 fill vs 시그널 가격)

## Stage 6 — 실거래 ⬜

조건:
- Stage 3 walk-forward 통과 (out-of-sample Sharpe > 1.0)
- Stage 4 페이퍼 트레이딩 **최소 4주** 실행, 백테스트와 PnL 편차 측정
- Stage 5 모든 안전 장치 활성

- [ ] 실제 API 키 연동
- [ ] **소액부터** (max_position_usdt=50 정도)
- [ ] Telegram/Discord 알림
- [ ] 일일 PnL 리포트
- [ ] 매주 페이퍼 vs 라이브 PnL 비교

## Stage 7 — 운영 ⬜

- [ ] VPS 배포 (도쿄 리전, Binance와 가까운 곳)
- [ ] systemd/Docker 자동 재시작
- [ ] 로그 영구 보관
- [ ] 대시보드 (Grafana 또는 간단 웹 UI)
- [ ] 정기 백테스트 갱신 (성과 저하 자동 탐지)

## 안 할 것 (적어도 당분간)

- 마켓 메이킹 / HFT — 지연시간 인프라 필요, Python으론 한계
- 옵션 — 복잡도 ↑, 입문 단계 부적합
- 대체 거래소 통합 — Binance 한 곳 마스터 후
- ML 기반 가격 예측 — 피처 엔지니어링 인프라부터 갖춰야

## KPI

| Stage | 성공 기준 |
|-------|-----------|
| 2 | 전략 3개, 베이스라인 Sharpe 비교 가능 |
| 3 | 최고 전략 walk-forward OOS Sharpe > 1.0 |
| 4 | Testnet 페이퍼 4주, 백테스트 대비 PnL 편차 < 30% |
| 5 | 킬 스위치 1초 내 동작 |
| 6 | 라이브 1개월 누적 수익 > 0, drawdown < 10% |
