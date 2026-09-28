# Validation results

## Citation matching: precision per stratum

| Stratum | Population | Labeled | Correct | Precision | 95% interval |
|---|---:|---:|---:|---:|---:|
| doi | 1,145 | 30 | 30 | 100.0% | 88.6% to 100.0% |
| exact | 11,046 | 40 | 40 | 100.0% | 91.2% to 100.0% |
| fuzzy 95-100 | 620 | 30 | 28 | 93.3% | 78.7% to 98.2% |
| fuzzy 90-95 | 624 | 30 | 26 | 86.7% | 70.3% to 94.7% |
| fuzzy 85-90 | 1,246 | 30 | 14 | 46.7% | 30.2% to 63.9% |
| fuzzy 80-85 (below threshold) | 3,059 | 30 | 10 | 33.3% | 19.2% to 51.2% |
| rejected by year check | 6,517 | 20 | 0 | 0.0% | 0.0% to 16.1% |

Correct fuzzy matches marked as a renamed preprint: 1

## Estimated precision of all accepted links by fuzzy threshold

Stratum precisions weighted by current stratum sizes (year check applied).

| Threshold | Accepted links | Estimated precision | Estimated false links |
|---:|---:|---:|---:|
| 80 | 17,740 | 84.1% | 2,828 |
| 85 | 14,681 | 94.6% | 789 |
| 90 | 13,435 | 99.1% | 125 |
| 95 | 12,811 | 99.7% | 41 |
| no fuzzy | 12,191 | 100.0% | 0 |

## Affiliations: accuracy by how the countries were found

| Stratum | Population | Labeled | Countries correct | 95% interval | Institutions correct |
|---|---:|---:|---:|---:|---:|
| address | 492 | 20 | 75.0% | 53.1% to 88.8% | 70.0% |
| explicit | 7,040 | 40 | 95.0% | 83.5% to 98.6% | 80.0% |
| inferred | 6,362 | 40 | 90.0% | 76.9% to 96.0% | 72.5% |

Weighted country accuracy over all papers with a country: 92.0%

## Errors found in the citation sample

- [fuzzy 95-100, 97.4] "NTTSU at WMT2024 general translation task" vs "NTTSU at WMT2025 General Translation Task"
- [fuzzy 95-100, 98.6] "QUESPA submission for the IWSLT 2024 dialectal and low-resou" vs "QUESPA Submission for the IWSLT 2025 Dialectal and Low-resou"
- [fuzzy 90-95, 92] "Continual learning for large language models: A survey" vs "Continual Learning of Large Language Models"
- [fuzzy 90-95, 91.1] "A survey on posttraining of large language models" vs "A Survey of Post-Training Scaling in Large Language Models"
- [fuzzy 90-95, 93.7] "Representation learning with large language models for recom" vs "Intent Representation Learning with Large Language Model for"
- [fuzzy 90-95, 93.7] "Representation learning with large language models for recom" vs "Intent Representation Learning with Large Language Model for"
- [fuzzy 85-90, 85.7] "Bayesian low-rank adaptation for large language models" vs "DenseLoRA: Dense Low-Rank Adaptation of Large Language Model"
- [fuzzy 85-90, 85.4] "A survey on knowledge distillation of large language models" vs "Knowledge Distillation for Language Models"
- [fuzzy 85-90, 87.1] "A survey on large language models for recommendation" vs "Local Large Language Models for Recommendation."
- [fuzzy 85-90, 86.1] "2023a. A watermark for large language models" vs "Ensemble Watermarks for Large Language Models"
- [fuzzy 85-90, 87.2] "Inference scaling for long-context retrieval augmented gener" vs "Inference Scaling for Bridging Retrieval and Augmented Gener"
- [fuzzy 85-90, 85.4] "Corrective retrieval augmented generation" vs "Parametric Retrieval Augmented Generation"
- [fuzzy 85-90, 86] "Combining knowledge graphs and large language models" vs "Refining Noisy Knowledge Graph with Large Language Models"
- [fuzzy 85-90, 85.4] "Corrective retrieval augmented generation" vs "Parametric Retrieval Augmented Generation"
- [fuzzy 85-90, 89.1] "Lora: Low-rank adaptation of large language models" vs "DenseLoRA: Dense Low-Rank Adaptation of Large Language Model"
- [fuzzy 85-90, 85.4] "Corrective retrieval augmented generation" vs "Parametric Retrieval Augmented Generation"
- [fuzzy 85-90, 85.4] "A survey on knowledge distillation of large language models" vs "Knowledge Distillation for Language Models"
- [fuzzy 85-90, 88.7] "Towards robust multimodal sentiment analysis with incomplete" vs "Proxy-Driven Robust Multimodal Sentiment Analysis with Incom"
- [fuzzy 85-90, 89.1] "Cruxeval: a benchmark for code reasoning, understanding and " vs "CRUXEVAL-X: A Benchmark for Multilingual Code Reasoning, Und"
- [fuzzy 85-90, 88.5] "2024b. Efficient multimodal large language models: A survey" vs "Self-Improvement in Multimodal Large Language Models: A Surv"
- [fuzzy 85-90, 85.4] "A Survey on Knowledge Distillation of Large Language Models" vs "Knowledge Distillation for Language Models"
- [fuzzy 85-90, 87.1] "A survey on large language models for recommendation" vs "Local Large Language Models for Recommendation."
- [fuzzy 80-85 (below threshold), 80] "A Survey of Large Language Models" vs "Conformity in Large Language Models"
- [fuzzy 80-85 (below threshold), 81.1] "An empirical study on information extraction using large lan" vs "RUIE: Retrieval-based Unified Information Extraction using L"
- [fuzzy 80-85 (below threshold), 84.4] "Cultural bias and cultural alignment of large language model" vs "Self-Pluralising Culture Alignment for Large Language Models"
- [fuzzy 80-85 (below threshold), 80] "Towards tool use alignment of large language models" vs "SafeLawBench: Towards Safe Alignment of Large Language Model"
- [fuzzy 80-85 (below threshold), 80] "A Survey of Large Language Models" vs "Conformity in Large Language Models"
- [fuzzy 80-85 (below threshold), 81.2] "Excgec: A benchmark for edit-wise explainable chinese gramma" vs "VisCGEC: Benchmarking the Visual Chinese Grammatical Error C"
- [fuzzy 80-85 (below threshold), 81.4] "2024a. Cumulative reasoning with large language models" vs "Out-of-Context Reasoning in Large Language Models"
- [fuzzy 80-85 (below threshold), 84.4] "Cultural bias and cultural alignment of large language model" vs "Self-Pluralising Culture Alignment for Large Language Models"
- [fuzzy 80-85 (below threshold), 80.4] "Pedagogical Alignment of Large Language Models" vs "DeAL: Decoding-time Alignment for Large Language Models"
- [fuzzy 80-85 (below threshold), 81.8] "Mitigating hallucinations in large vision-language models (L" vs "Mitigating Hallucinations in Large Vision-Language Models vi"
- [fuzzy 80-85 (below threshold), 83.5] "Longbench: A bilingual, multitask benchmark for long context" vs "LC-Eval: A Bilingual Multi-Task Evaluation Benchmark for Lon"
- [fuzzy 80-85 (below threshold), 80] "Reasoning with large language models, a survey" vs "Prompt Compression for Large Language Models: A Survey"
- [fuzzy 80-85 (below threshold), 83.5] "A survey on evaluation of large language models" vs "Source Attribution for Large Language Models"
- [fuzzy 80-85 (below threshold), 81.4] "Bias and fairness in large language models: A survey" vs "Causal Inference with Large Language Model: A Survey"
- [fuzzy 80-85 (below threshold), 80] "A survey of large language models" vs "Conformity in Large Language Models"
- [fuzzy 80-85 (below threshold), 80] "Evaluating large language models for causal modeling" vs "Evaluating Large Language Models for Narrative Topic Labelin"
- [fuzzy 80-85 (below threshold), 83.5] "A survey on evaluation of large language models" vs "Source Attribution for Large Language Models"
- [fuzzy 80-85 (below threshold), 81.2] "The geometry of tokens in internal representations of large " vs "High-Dimensional Interlingual Representations of Large Langu"
- [fuzzy 80-85 (below threshold), 83.5] "A Survey on Evaluation of Large Language Models" vs "Source Attribution for Large Language Models"
- [fuzzy 80-85 (below threshold), 80] "Posix: A prompt sensitivity index for large language models" vs "Benchmarking Prompt Sensitivity in Large Language Models"
- [rejected by year check, 83.1] "Query rewriting in retrievalaugmented large language models" vs "Entropy-Based Decoding for Retrieval-Augmented Large Languag"
- [rejected by year check, 89.1] "Lora: Low-rank adaptation of large language models" vs "DenseLoRA: Dense Low-Rank Adaptation of Large Language Model"
- [rejected by year check, 89.1] "LoRA: Low-rank adaptation of large language models" vs "DenseLoRA: Dense Low-Rank Adaptation of Large Language Model"
- [rejected by year check, 88.5] "Measuring massive multitask language understanding" vs "KMMLU: Measuring Massive Multitask Language Understanding in"
- [rejected by year check, 80] "A survey of large language models" vs "Conformity in Large Language Models"
- [rejected by year check, 80] "A survey of large language models" vs "Conformity in Large Language Models"
- [rejected by year check, 89.1] "LoRA: Low-Rank Adaptation of Large Language Models" vs "DenseLoRA: Dense Low-Rank Adaptation of Large Language Model"
- [rejected by year check, 83.1] "Query rewriting in retrievalaugmented large language models" vs "Entropy-Based Decoding for Retrieval-Augmented Large Languag"
- [rejected by year check, 89.1] "Lora: Low-rank adaptation of large language models" vs "DenseLoRA: Dense Low-Rank Adaptation of Large Language Model"
- [rejected by year check, 80] "A survey of large language models" vs "Conformity in Large Language Models"
- [rejected by year check, 89.1] "Lora: Low-rank adaptation of large language models" vs "DenseLoRA: Dense Low-Rank Adaptation of Large Language Model"
- [rejected by year check, 88.5] "Measuring massive multitask language understanding" vs "KMMLU: Measuring Massive Multitask Language Understanding in"
- [rejected by year check, 86.8] "Scaling laws for neural language models" vs "Scaling Laws for Multilingual Language Models"
- [rejected by year check, 80] "A survey on conversational recommender systems" vs "Continual Recommender Systems."
- [rejected by year check, 89.1] "Lora: Low-rank adaptation of large language models" vs "DenseLoRA: Dense Low-Rank Adaptation of Large Language Model"
- [rejected by year check, 89.1] "Lora: Low-rank adaptation of large language models" vs "DenseLoRA: Dense Low-Rank Adaptation of Large Language Model"
- [rejected by year check, 81.5] "Grammatical error correction in low-resource scenarios" vs "Hi-GEC: Hindi Grammar Error Correction in Low Resource Scena"
- [rejected by year check, 88.5] "Measuring massive multitask language understanding" vs "KMMLU: Measuring Massive Multitask Language Understanding in"
- [rejected by year check, 82] "Bbq: A hand-built bias benchmark for question answering" vs "GG-BBQ: German Gender Bias Benchmark for Question Answering"
- [rejected by year check, 85.1] "Universal prompt tuning for graph neural networks" vs "Fairness-aware Prompt Tuning for Graph Neural Networks"

## Errors found in the affiliation sample

- [explicit] countries 1 / institutions 0: wrong= missing= Dupe
- [explicit] countries 1 / institutions 0: wrong= missing= Dupe
- [explicit] countries 1 / institutions 0: wrong= missing=
- [explicit] countries 1 / institutions 0: wrong= missing=
- [explicit] countries 1 / institutions 0: wrong= missing=
- [explicit] countries 1 / institutions 0: wrong= missing=
- [explicit] countries 1 / institutions 0: wrong= missing=
- [explicit] countries 0 / institutions 1: wrong= missing=
- [explicit] countries 0 / institutions 1: wrong=AU missing=
- [explicit] countries 1 / institutions 0: wrong= missing= Author name
- [inferred] countries 1 / institutions 0: wrong= missing=
- [inferred] countries 1 / institutions 0: wrong= missing= Hong Kong removed
- [inferred] countries 1 / institutions 0: wrong= missing= London removed
- [inferred] countries 0 / institutions 0: wrong= missing=CH MIT
- [inferred] countries 1 / institutions 0: wrong= missing= Hong Kong removed
- [inferred] countries 1 / institutions 0: wrong= missing=
- [inferred] countries 0 / institutions 0: wrong= missing=QA
- [inferred] countries 0 / institutions 0: wrong= missing=CA Not full
- [inferred] countries 1 / institutions 0: wrong= missing=
- [inferred] countries 1 / institutions 0: wrong= missing= Dupe
- [inferred] countries 0 / institutions 1: wrong= missing=BD
- [inferred] countries 1 / institutions 0: wrong= missing=
- [address] countries 0 / institutions 0: wrong=CO missing=
- [address] countries 1 / institutions 0: wrong= missing= Authors
- [address] countries 1 / institutions 0: wrong= missing=
- [address] countries 1 / institutions 0: wrong= missing= Hong Kong removed
- [address] countries 0 / institutions 1: wrong=AR missing=US
- [address] countries 0 / institutions 1: wrong=CA missing=
- [address] countries 1 / institutions 0: wrong= missing= Hong Kong removed
- [address] countries 0 / institutions 1: wrong=MH missing=
- [address] countries 0 / institutions 0: wrong=AD,BO missing=
