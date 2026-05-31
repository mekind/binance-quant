# 전문 퀀트 회사는 어떻게 하는가 (그리고 우리가 따라할 수 있는 것)

> **이 문서의 위치.** [06-why-swing-not-scalping.md](06-why-swing-not-scalping.md)가
> "왜 단타가 아닌가"였다면, 이 문서는 "그럼 *진짜로 돈 버는* 퀀트 회사는 어떻게
> 하는가"를 조사해 정리한다. 결론을 먼저 말하면: **그들의 엣지는 천재적 신호
> 하나가 아니라 ① 가설→검증의 잔혹한 규율, ② 수백 개 시장에 걸친 분산, ③ 실행을
> 별도 과학으로 다루는 것, ④ 리스크를 신호보다 우선하는 것에서 나온다.** 우리가
> 베낄 수 있는 건 ①과 ④이고, ②와 ③은 구조적으로 제한적이다.

---

## 1. 퀀트 회사의 5가지 유형 — 우리가 들어갈 수 있는 판은 하나뿐

| 유형 | 대표 | 엣지의 원천 | 리테일 가능? |
|---|---|---|---|
| **HFT / 마켓메이킹** | Citadel Securities, Jane Street, Jump | 마이크로초 속도, 큐 우선순위, 리베이트 | ❌ 구조적 불가 |
| **통계적 차익(stat arb)** | 다수 멀티전략 펀드 | 공적분(cointegration)된 자산쌍의 일시적 괴리 | △ 가능하나 어려움 |
| **시스테마틱 트렌드 / CTA** | Winton, Man AHL, Two Sigma | **광범위 분산 + 추세 + 변동성 관리** | ✅ **우리에게 가장 가까움** |
| **팩터 / 퀀트 매크로** | AQR, Renaissance(Medallion) | 학술 팩터, 독점 데이터, 비공개 | △ 일부 팩터만 |
| **평균회귀** | 다수 | 단기 과매도/과매수 되돌림 | △ 추세장에 약함 |

핵심: **속도 게임(HFT)은 포기.** 우리가 정직하게 도전할 수 있는 건 **CTA식
시스테마틱 트렌드추종**이다 — 마침 [04-roadmap.md](04-roadmap.md)가 향하는 방향.

## 2. 전략 개발 라이프사이클 — "백테스트 잘 나옴 → 라이브"가 아니다

전문 회사의 프로세스는 **입력(신호) → 예측 엔진 → 포트폴리오 구성** 3단계로
나뉘고, 각 신호는 다음을 통과해야 실전에 들어간다:

```
경제적 가설 (왜 이게 먹히는가?)  ← 데이터 마이닝이 아니라 여기서 시작
   ↓
인샘플 백테스트
   ↓
아웃오브샘플(OOS) + 워크포워드 검증  ← 최적화에 안 쓴 데이터로
   ↓
페이퍼/시뮬레이션 (실행비용 포함)
   ↓
소액 라이브 → 점진적 증액
```

**가장 중요한 원칙들** (조사에서 반복 등장):
- **경제적 근거가 먼저** — "왜 이 패턴이 존재하고 지속되는가"를 설명 못 하면 그건
  노이즈일 확률이 높다. 데이터를 고문해서 찾은 패턴은 OOS에서 죽는다.
- **단순한 규칙이 이긴다** — 복잡할수록 과적합하고 실행이 흔들린다.
- **샤프 단독은 OOS 예측력이 거의 없다** — 한 연구에선 백테스트 샤프의 OOS
  예측력 R² < 0.025. 오히려 **변동성·최대낙폭·헤징 구조**가 더 예측력 있었다.

## 3. 과적합과의 전쟁 — 이게 퀀트 회사의 진짜 핵심 역량

> "퀀트가 한 전략을 백테스트할수록, 백테스트와 실전의 괴리는 커진다." — 다중검정의 저주

Marcos López de Prado(전 Guggenheim/AQR 퀀트)의 연구가 업계 표준 경고다:

- **백테스트 과적합 확률(PBO, Probability of Backtest Overfitting)** — 여러 전략을
  시험해 "최고"를 고르면, 그 최고가 사실은 운빨일 확률을 정량화.
- **Deflated Sharpe Ratio(DSR)** — 샤프를 두 가지로 보정한다: ① **다중검정 선택편향**
  (전략 100개 돌려서 best 하나 고른 효과), ② **수익률 비정규성**. 보정 후에도
  살아남아야 진짜 발견.
- **"머신러닝 펀드가 실패하는 10가지 이유"** — 대부분 방법론적 자기기만이다.

**우리에게 직접 적용 가능**: `validation/` 모듈에 이미 walk-forward / Monte Carlo가
있다. 여기에 **시험한 파라미터 조합 수를 반영한 DSR/PBO**를 추가하면, 그리드서치로
"최고"를 골랐을 때 그게 통계적 플루크인지 걸러낼 수 있다. ([04-roadmap.md](04-roadmap.md)
Stage 3 게이트 강화 후보)

## 4. 데이터 인프라 — "깨끗한 과거"에 돈을 쓴다

전문 회사가 데이터에 집착하는 이유:
- **Point-in-time / 생존편향 제거** — "그 시점에 실제로 알 수 있던 데이터"만 사용.
  상장폐지된 종목을 빼고 백테스트하면 결과가 거짓말한다(생존편향). 크립토에서
  죽은 알트코인을 빼면 똑같은 함정.
- **틱/호가창 데이터** — 실행비용을 현실적으로 모델링하려면 봉이 아니라 호가가 필요.
- **다중 소스 교차검증** — 한 거래소 데이터만 믿지 않음.

**우리 현실**: BTC/ETH는 다년치 깨끗한 데이터가 있지만 저시총 알트는 짧고 더럽다 →
검증을 신뢰할 수 있는 자산에서만 시작해야 하는 이유. (지난 결정: BTCUSDT 우선)

## 5. 실행(execution)은 별개의 과학 — 전담 트레이더가 있다

전문 회사에서 **신호를 만드는 사람(researcher)과 주문을 넣는 사람(execution trader)은
다르다.** 실행팀의 유일한 KPI는 "비용 최소화, 체결 최대화"다. 도구:

| 알고리즘 | 목적 |
|---|---|
| **TWAP** (시간가중) | 큰 주문을 시간에 고르게 쪼갬, 변동적 거래량 프로파일에 적합 |
| **VWAP** (거래량가중) | 예상 거래량 패턴에 맞춰 쪼갬, 시장충격 최소화 |
| **POV** (참여율) | 시장 거래량의 X%만 따라감 |
| **Implementation Shortfall(IS)** | "결정 시점 가격 vs 실제 체결가" 차이를 최소화. 시장충격 vs 타이밍 리스크의 균형 (Perold 1988) |

핵심 개념 **Implementation Shortfall** = 이론상 포트폴리오 수익 − 실제 구현된 수익.
이 괴리가 우리 코드의 `entry_slip_bps`/`exit_slip_bps`가 측정하려는 바로 그것이다.

**우리 현실**: 스윙은 거래가 드물고 주문이 작아 시장충격이 미미 → 다행히 정교한
실행 알고리즘 없이 시장가로도 큰 손해는 안 본다. (단타였다면 이게 치명적이었음 —
[06](06-why-swing-not-scalping.md) 참조) 그래도 **슬리피지 측정은 계속 해야** 백테스트
대비 실전 괴리를 안다.

## 6. 포트폴리오 구성 & 리스크 — 신호보다 리스크가 먼저

전문 회사는 "리스크를 세 숫자로 정의한다: **예상 변동성, 예상 최대낙폭, 최악의
유동성**." 그리고 포트폴리오가 그 숫자 안에 들어오게 구성한다.

- **변동성 타게팅(volatility targeting)** — 목표 변동성에 맞춰 포지션 크기 조절.
  변동성 오르면 줄이고 내리면 늘림. ⚠️ **함정: 절차적 순응성(procyclical)** —
  변동성 급등 후 팔고 진정 후 사서, 바닥에서 팔고 천장에서 사는 꼴이 될 수 있음.
  (우리 코드의 `AtrSizer`가 바로 변동성 타게팅 — 이 함정을 인지하고 써야 함)
- **리스크 패리티(risk parity)** — 자본이 아니라 *리스크 기여도*를 균등 배분.
  변동성 큰 자산은 비중 축소.
- **드로다운 한도 / VaR** — 손실이 한도에 닿으면 강제 축소·중단. (우리 코드의
  `DailyLossGuard`가 단순화 버전)

## 7. 팀 구조 — 리테일은 이 4명을 혼자 한다

| 역할 | 하는 일 | 우리 프로젝트에서 |
|---|---|---|
| **Researcher** | 신호 발굴, 백테스트, 포트폴리오 블렌딩 | `strategies/`, `backtest/`, `validation/` |
| **Developer** | 신호를 견고한 실시간 시스템으로, "데이터 빠지면?" 처리 | `live/`, `data/` |
| **Trader** | 라이브 리스크 관리, 실행비용 최소화, 이상상황 감시 | `mm live` 운영자(=당신) |
| **Risk** | 한도 설정, 강제 축소, 사후 검증 | `risk.py` + 게이트 규율 |

작은 펀드도 최소 2~3명(researcher+dev+trader). **혼자 다 하면 각 역할의 검증
규율이 무너지기 쉽다** — 그래서 우리는 "코드가 규율을 강제"하게 만든다(게이트,
B&H 벤치마크, 자동 검증).

## 8. CTA 트렌드추종이 우리에게 가장 중요한 이유 — 그리고 가장 큰 함정

조사에서 가장 일관된 사실: **시스테마틱 트렌드추종(CTA)의 엣지는 "광범위한 분산"에서
나온다.**

- Winton·Man AHL의 공식: **중장기 추세를 따르되, 아주 넓게 분산하고, 변동성을
  통제해 한 시장도 지배하지 못하게 한다.**
- 학술 연구: **71개 선물 계약**(주식·채권·통화·원자재)에 걸친 시계열 모멘텀 효과 문서화.
- 트렌드추종은 **팻테일(fat-tail) 큰 움직임**을 잡는 전략 — 작은 손실을 자주 보고
  큰 추세에서 크게 번다(승률 낮고 손익비 높음).
- Winton 분석: **느린 추세 모델일수록 샤프 감쇠가 적었다**(빠른 신호는 경쟁으로 닳음).

### ⚠️ 우리의 구조적 약점: 분산이 안 된다

CTA의 샤프(0.3~0.5대)는 *한 시장의 완벽한 신호*가 아니라 **수십~수백 개 비상관
시장의 합**에서 나온다. 그런데:
- 우리 코드는 **단일 심볼 0/1 구조** (다종목은 미구현)
- 설령 다종목으로 가도 **크립토는 대부분 BTC와 고상관** → "분산"이 환상

**함의**: BTCUSDT 단일 트렌드추종은 CTA의 핵심 무기(분산)를 못 쓴다. 그래서
- 총수익으로 BTC B&H를 이기긴 어렵고, **하락장 낙폭 회피로 위험조정에서 이기는 것**이
  현실적 목표다 (느린 추세 + 변동성 관리).
- 분산을 흉내내려면 **약상관 자산 소수**(예: BTC·ETH + 비크립토는 불가)나 **여러
  타임프레임/신호의 앙상블** 정도가 현실적 상한.

## 9. 요약: 우리가 채택 / 변형 / 포기하는 것

| 전문 회사 관행 | 우리 | 이유 |
|---|---|---|
| 가설→OOS→페이퍼→소액 라이브 규율 | ✅ **그대로 채택** | 돈 안 드는 규율, 자기기만 방지의 핵심 |
| DSR / PBO로 과적합 정량화 | ✅ **채택 (Stage 3 추가)** | 그리드서치 best가 플루크인지 거름 |
| B&H 등 벤치마크 대비 평가 | ✅ **채택 (Stage 1)** | 이미 로드맵에 반영 |
| 변동성 타게팅 / 드로다운 한도 | ✅ **단순화 채택** | `AtrSizer`/`DailyLossGuard` (순응성 함정 주의) |
| 생존편향 없는 깨끗한 데이터 | ✅ **채택** | BTC/ETH 위주, 저시총 알트 회피 |
| 느린 추세 + 넓은 분산 | △ **변형** | 추세는 채택, 분산은 크립토 고상관으로 제한적 |
| VWAP/IS 정교한 실행 | △ **최소화** | 스윙은 거래 드물어 시장가로 충분, 슬리피지만 측정 |
| HFT / 마이크로초 실행 | ❌ **포기** | 인프라·속도 구조적 불가 |
| 100+ 명 연구팀, 독점 데이터 | ❌ **포기** | 대신 "코드가 규율을 강제"로 대체 |

**한 줄 요약**: 우리는 전문 회사의 *방법론적 규율*(검증·벤치마크·리스크 우선)은
완전히 베끼고, *물량전*(속도·분산·인력·데이터)은 못 베낀다. 그래서 승부처는
"규율로 자기기만을 제거하고, 느린 추세에서 위험조정 우위를 찾을 수 있는가"다.

---

## 출처

- [The Deflated Sharpe Ratio (Bailey & López de Prado)](https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf)
- [The Probability of Backtest Overfitting (SSRN)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2326253)
- [The 10 Reasons Most Machine Learning Funds Fail (López de Prado, GARP)](https://www.garp.org/hubfs/Whitepapers/a1Z1W0000054x6lUAA.pdf)
- [Statistical Overfitting and Backtest Performance (Bailey et al.)](https://sdm.lbl.gov/oapapers/ssrn-id2507040-bailey.pdf)
- [Demystifying Managed Futures (AQR)](https://www.aqr.com/-/media/AQR/Documents/Insights/Journal-Article/Demystifying-Managed-Futures.pdf)
- [Citadel — Global Quantitative Strategies](https://www.citadel.com/what-we-do/global-quantitative-strategies/)
- [Quant Researcher vs Trader vs Developer (Quant Blueprint)](https://www.quantblueprint.com/glossary/quant-researcher-vs-trader-vs-developer)
- [A Brief History of Implementation Shortfall (Quantitative Brokers)](https://www.quantitativebrokers.com/blog/a-brief-history-of-implementation-shortfall)
- [Implementation Shortfall — One Objective, Many Algorithms (UPenn)](https://www.cis.upenn.edu/~mkearns/finread/impshort.pdf)
- [Risk Parity Portfolio (QuantInsti)](https://blog.quantinsti.com/risk-parity-portfolio/)
- [Decoding CTA Allocations by Trend Horizon (CFA Institute)](https://blogs.cfainstitute.org/investor/2026/01/28/decoding-cta-allocations-by-trend-horizon/)
- [Quantitative Alpha in Crypto Markets: A Systematic Review (SSRN)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5225612)
