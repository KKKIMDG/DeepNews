# DeepNews 최종 AI 모델과 검증 기록

이 문서는 개발자가 제공한 실제 학습 코드 및 2026-11-02 재평가 결과를 기록합니다.
이번 추가 파일은 backend, frontend, airflow 및 기존 학습 스크립트를 변경하지 않습니다.

## 파일

| 파일 | 역할 |
| --- | --- |
| train_ad_80_20.py | 기존 광고 모델의 80/20 학습 코드 보존본 |
| train_kobart_v2.py | 실제 EOS 수정 후 KoBART v2 학습 코드 |
| eval_ad.py | 저장된 광고 모델의 기존 검증셋 재평가 |
| eval_summary_fixed.py | 학습 방식으로 검증셋 재구성 후 한국어 ROUGE 평가 |
| demo_kobart.py | 기사 3개 수동 요약 예시; 정량 평가와 구분 |
| evaluation_results/summary_validation_20261102.json | 사용자 실행 로그의 요약 재평가 결과 |

저장소의 train_ad_classifier.py 및 train_kobart_summary.py는 이 기록의 실제 학습 원본과
설정이 다릅니다. 해당 파일을 이 모델들의 학습 근거로 혼용하지 않습니다.
광고 보존본 출처는 커밋 7c7861ce867e4a6fc25f6bbcb83553fc62ffa5d4의
ai/train_ad_classifier.py이며, 80/20 분할과 MLflow 기록 설정이 개발자 설명과 일치합니다.
KoBART 코드는 개발자가 제공한 v2 코드와 같은 학습 설정으로 정리했습니다.

## 광고 모델

- 기반 모델: klue/roberta-base.
- 직접 라벨링 402건(일반 201, 광고 201), 학습 321 / 검증 81.
- sklearn train_test_split(test_size=0.2, random_state=42, stratify=labels).
- 5 epochs, batch size 8, learning rate 2e-5, 입력 최대 512토큰.
- 검증 macro F1이 가장 높은 모델을 저장. MLflow에 학습 설정 및 지표 기록.
- 제공된 검증 성능: Accuracy 88.89%, 광고 Precision 82.98%, Recall 97.50%, F1 89.66%.
- 제공된 혼동행렬: [[33, 8], [1, 39]] (행=정답, 열=예측, 순서=일반/광고).
- 평가 코드의 argmax는 이진 분류에서 확률 0.5 경계에 해당합니다(정확히 같은 확률의 동률은 일반 선택).
- 별도 시험 데이터가 없으며, 모델 선택에 사용한 검증셋 결과입니다.
- 서비스의 광고성 표시/추천 제외 기준과 평가 기준은 별개입니다. 서버 기준은 이 업데이트에서 변경하지 않습니다.

## 요약 모델

- 기반 모델: gogamza/kobart-summarization 추가 학습.
- AI Hub 신문요약 268,535건, 학습 241,681 / 검증 26,854.
- datasets train_test_split(test_size=0.1, seed=42).
- 3 epochs, batch size 16, learning rate 3e-5, 입력 최대 1024 / 정답 최대 200토큰.
- 정답 문자열 끝에 EOS를 추가하고 add_special_tokens=False로 토큰화.
  최대 길이 절단으로 EOS가 잘릴 수 있으므로, 이 코드가 모든 라벨의 EOS를 보장한다고 설명하지 않습니다.
- 검증 eval_loss 기준 최고 체크포인트 저장. report_to="none"이며 MLflow 기록 없음.
- 저장 폴더: kobart_summary_final_v2.
- Gemma+LoRA는 최종 서비스 모델로 사용하지 않습니다.

## 2026-11-02 요약 재평가

| 지표 | 값 |
| --- | ---: |
| ROUGE-1 F1 | 0.3750 |
| ROUGE-2 F1 | 0.2467 |
| ROUGE-L F1 | 0.3302 |
| 평균 생성 시간 | 0.4884초/건 |
| 평가 샘플 | 검증 500건 |
| GPU | NVIDIA GeForce RTX 2060 |

- 학습과 동일한 원본/행 순서라는 조건에서 검증셋을 재구성했습니다. 학습 당시 원본 해시는 제공되지 않았습니다.
- 평가 전에 학습 본문과 동일한 정규화 본문 및 평가 샘플 내 중복을 제외합니다. 근접 중복 검사는 아닙니다.
- NFKC 정규화와 소문자화 후 Unicode 단어 단위로 계산한 기사별 ROUGE F1의 평균입니다.
  형태소 단위 평가는 아니며, 기본 rouge_score 토큰화 및 다른 토큰화 수치와 직접 비교하지 않습니다.
- 생성 시간은 워밍업 후 CUDA 동기화를 적용한 model.generate 시간만 측정했습니다.
  토큰화, ROUGE 계산, 기사 추출, 네트워크 및 전체 API 응답 시간은 포함하지 않습니다.
- 이전 sklearn 분할의 500건 중 재구성한 학습셋에 속한 항목은 466건이었습니다(동일 원본/순서 조건).
  이전 ROUGE 수치는 최종 성능으로 사용하지 않습니다.
- 별도 시험셋 성능이 아니라 검증 성능입니다.

## 실행

명령은 DeepNews 프로젝트 루트에서 실행합니다. 모델과 데이터는 별도 로컬 파일이며 이 추가본에는 포함하지 않습니다.

```powershell
python ai/eval_ad.py
python ai/eval_summary_fixed.py --check-only
python ai/eval_summary_fixed.py
python ai/demo_kobart.py
```

평가 데이터 위치는 ai/data/, 모델 위치는 model/ad_model 및 model/kobart_summary_final_v2입니다.
요약 검증셋 재구성 시 보고된 학습 datasets 버전 4.8.5를 확인합니다.
AI 학습/평가 실행 환경에서 torch, transformers, datasets, scikit-learn, rouge-score 등이 필요하며,
광고 학습에는 MLflow도 필요합니다. 루트 의존성 파일은 이 변경에서 수정하지 않습니다.

학습 스크립트는 원래 A100 환경의 데이터/출력 경로를 보존합니다. 코드 보존과 평가 실행은
재학습을 뜻하지 않습니다. 배포된 모델 교체 및 서버 재시작도 이번 Git 업데이트에 포함하지 않습니다.
실제 서비스 추론 진입점은 backend/domains/analysis/service.py이며 이 추가본에서 수정하지 않습니다.
