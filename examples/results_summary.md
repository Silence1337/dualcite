# DualCite results summary

Two venue groups compared: **Computational Linguistics (CL)** vs **Information Retrieval (IR)**.

## Corpus overview

- Total papers in corpus: 14,218
- CL papers: 12,487
- IR papers: 1,731
- Papers with country data: 12,784 (89.9%)
- Intra-corpus citations (edges): 18,444
- Total references made (all, including outside the corpus): 587,689
- References resolved within the corpus: 18,444 (3.1%)
- References to works outside the corpus ("other"): 569,245 (96.9%)

> The vast majority of references point outside the single-year corpus (to earlier years or untracked venues). This is expected: most citations in any paper are to prior work. The citation-flow analysis below therefore concerns only the small fraction of references that link two papers *inside* the 2025 corpus — the asymmetry and relative shares matter more than the absolute counts.

## Citation flows between the two communities

*(Only references that resolve to another paper inside the corpus — i.e. 2025→2025 links. The "other" bucket above is excluded here.)*

| Direction | Citations | % of all intra-corpus citations |
|---|---:|---:|
| CL → CL (within CL) | 16,896 | 91.6% |
| IR → IR (within IR) | 518 | 2.8% |
| CL → IR (cross) | 459 | 2.5% |
| IR → CL (cross) | 571 | 3.1% |

- Total cross-community citations: 1,030 (5.6% of all)
- Cross-flow asymmetry (CL→IR vs IR→CL): 459 vs 571  (ratio 0.80)

## References to tracked venues across all years

Unlike the citation flows above (which only link 2025→2025 papers inside the corpus), this counts every reference our 2025 papers make to one of the tracked venues **regardless of the cited work's year**. It is the broader 'do these communities cite each other's venues at all' view, and the numbers are naturally much larger.

### References made by CL papers

- To own community (CL) venues: 88,575 (94.1%)
- To other community venues: 5,517 (5.9%)

| Cited venue | Cluster | References |
|---|---|---:|
| ACL | CL | 41,013 |
| EMNLP | CL | 26,712 |
| COLING | CL | 5,729 |
| IJCNLP | CL | 943 |
| NAACL | CL | 9,447 |
| LREC | CL | 2,978 |
| EACL | CL | 1,753 |
| SIGIR | IR | 2,645 |
| WWW | IR | 1,086 |
| CIKM | IR | 896 |
| WSDM | IR | 583 |
| ECIR | IR | 275 |
| CHIIR | IR | 32 |

### References made by IR papers

- To own community (IR) venues: 9,225 (69.5%)
- To other community venues: 4,052 (30.5%)

| Cited venue | Cluster | References |
|---|---|---:|
| ACL | CL | 1,831 |
| EMNLP | CL | 1,487 |
| COLING | CL | 194 |
| IJCNLP | CL | 35 |
| NAACL | CL | 389 |
| LREC | CL | 76 |
| EACL | CL | 40 |
| SIGIR | IR | 4,840 |
| WWW | IR | 949 |
| CIKM | IR | 1,770 |
| WSDM | IR | 995 |
| ECIR | IR | 451 |
| CHIIR | IR | 220 |

*Note: this counts references whose cited venue name could be matched to a tracked venue. References to venues outside the tracked set, or that GROBID couldn't parse a venue name for, are not counted here.*

## Internal / external / other — matched against all-years lists

Every outgoing reference from the 2025 papers, matched against full all-years reference lists of **CL** and **IR** and classified as internal (same community, any year), external (other community, any year), or other (in neither list). This is the most complete view of how the two communities cite each other.

*(Reference lists: CL — 120,552 titles / 0 DOIs; IR — 27,256 titles / 27,333 DOIs.)*

### References made by CL papers

| Target | References | % |
|---|---:|---:|
| Internal (→ CL, any year) | 148,782 | 28.7% |
| External (→ IR, any year) | 5,041 | 1.0% |
| Other (neither) | 364,814 | 70.3% |
| **Total** | **518,637** | 100% |

- Internal-to-external ratio: 29.5 (CL cites its own community 29.5× more than the other)

### References made by IR papers

| Target | References | % |
|---|---:|---:|
| Internal (→ IR, any year) | 8,581 | 12.4% |
| External (→ CL, any year) | 6,929 | 10.0% |
| Other (neither) | 53,541 | 77.5% |
| **Total** | **69,051** | 100% |

- Internal-to-external ratio: 1.2 (IR cites its own community 1.2× more than the other)

### Cross-community comparison (all years)

- CL → IR references: 5,041
- IR → CL references: 6,929
- Asymmetry ratio (CL→IR : IR→CL): 0.73

*Note: the two reference lists may differ in coverage (e.g. one spans an entire anthology, the other a fixed set of venues), so the 'internal' share is more complete for the better-covered community. The cross-community asymmetry is unaffected by this.*

## Per-venue breakdown

| Venue | Cluster | Papers | Citations made | Cross-cluster citations made |
|---|---|---:|---:|---:|
| ACL | CL | 4,512 | 6,283 | 166 |
| EMNLP | CL | 4,184 | 7,911 | 196 |
| COLING | CL | 1,228 | 679 | 25 |
| IJCNLP | CL | 631 | 969 | 29 |
| NAACL | CL | 1,932 | 1,513 | 43 |
| LREC | CL | 0 | 0 | 0 |
| EACL | CL | 0 | 0 | 0 |
| SIGIR | IR | 678 | 579 | 275 |
| WWW | IR | 0 | 0 | 0 |
| CIKM | IR | 859 | 460 | 275 |
| WSDM | IR | 150 | 41 | 19 |
| ECIR | IR | 0 | 0 | 0 |
| CHIIR | IR | 44 | 9 | 2 |

## Bridge venues (most cross-community citations)

Venues ranked by how many cross-community citations their papers make (outgoing) — candidates for 'bridges' between the two fields.

| Venue | Cross-cluster citations made |
|---|---:|
| SIGIR | 275 |
| CIKM | 275 |
| EMNLP | 196 |
| ACL | 166 |
| NAACL | 43 |
| IJCNLP | 29 |
| COLING | 25 |
| WSDM | 19 |
| CHIIR | 2 |

## Top countries — CL

| Rank | Country | Papers |
|---:|---|---:|
| 1 | China (CN) | 3,551 |
| 2 | United States (US) | 3,144 |
| 3 | United Kingdom (GB) | 831 |
| 4 | Germany (DE) | 803 |
| 5 | India (IN) | 544 |
| 6 | Korea, Republic of (KR) | 511 |
| 7 | Singapore (SG) | 459 |
| 8 | Canada (CA) | 424 |
| 9 | Hong Kong (HK) | 397 |
| 10 | Japan (JP) | 359 |
| 11 | France (FR) | 299 |
| 12 | Australia (AU) | 271 |
| 13 | Italy (IT) | 227 |
| 14 | Netherlands (NL) | 219 |
| 15 | Switzerland (CH) | 167 |
| 16 | Spain (ES) | 151 |
| 17 | Denmark (DK) | 113 |
| 18 | Bangladesh (BD) | 105 |
| 19 | Israel (IL) | 101 |
| 20 | United Arab Emirates (AE) | 100 |

## Top countries — IR

| Rank | Country | Papers |
|---:|---|---:|
| 1 | China (CN) | 748 |
| 2 | United States (US) | 454 |
| 3 | Italy (IT) | 352 |
| 4 | Australia (AU) | 155 |
| 5 | Korea, Republic of (KR) | 144 |
| 6 | United Kingdom (GB) | 92 |
| 7 | Netherlands (NL) | 88 |
| 8 | Germany (DE) | 88 |
| 9 | Canada (CA) | 79 |
| 10 | Singapore (SG) | 51 |
| 11 | India (IN) | 38 |
| 12 | Japan (JP) | 38 |
| 13 | France (FR) | 33 |
| 14 | Spain (ES) | 22 |
| 15 | Switzerland (CH) | 18 |
| 16 | Belgium (BE) | 18 |
| 17 | Austria (AT) | 18 |
| 18 | Taiwan, Province of China (TW) | 16 |
| 19 | Israel (IL) | 14 |
| 20 | Norway (NO) | 14 |

## Top institutions — CL

| Rank | Institution | Papers |
|---:|---|---:|
| 1 | Tsinghua University | 377 |
| 2 | University of California | 271 |
| 3 | Chinese Academy of Sciences | 271 |
| 4 | University of Chinese Academy of Sciences | 271 |
| 5 | Zhejiang University | 264 |
| 6 | Peking University | 260 |
| 7 | National University of Singapore | 205 |
| 8 | Harbin Institute of Technology | 205 |
| 9 | Fudan University | 195 |
| 10 | Carnegie Mellon University | 190 |
| 11 | Nanyang Technological University | 186 |
| 12 | Shanghai Jiao Tong University | 185 |
| 13 | Renmin University of China | 162 |
| 14 | Northeastern University | 154 |
| 15 | Indian Institute of Technology | 149 |
| 16 | Stanford University | 144 |
| 17 | University of Science and Technology of China | 135 |
| 18 | Seoul National University | 125 |
| 19 | University of Cambridge | 124 |
| 20 | New York University | 120 |

## Top institutions — IR

| Rank | Institution | Papers |
|---:|---|---:|
| 1 | University of Amsterdam | 58 |
| 2 | Renmin University of China | 58 |
| 3 | Tsinghua University | 49 |
| 4 | University of Science and Technology of China Hefei | 49 |
| 5 | National University of Singapore | 34 |
| 6 | Chinese Academy of Sciences | 33 |
| 7 | The University of Queensland Brisbane | 30 |
| 8 | Fudan University | 30 |
| 9 | University of Glasgow | 28 |
| 10 | RMIT University | 27 |
| 11 | Zhejiang University | 26 |
| 12 | University of California | 26 |
| 13 | University of Waterloo | 25 |
| 14 | Peking University | 25 |
| 15 | Kuaishou Technology | 25 |
| 16 | City University of Hong Kong | 20 |
| 17 | Alibaba Group | 20 |
| 18 | Nanyang Technological University | 19 |
| 19 | Shanghai Jiao Tong University | 19 |
| 20 | University of Chinese Academy of Sciences | 18 |

## Top co-authoring country pairs

Pairs of countries that most often appear together on the same paper (international collaboration).

| Rank | Country pair | Papers |
|---:|---|---:|
| 1 | China – United States | 506 |
| 2 | China – Singapore | 274 |
| 3 | China – Hong Kong | 254 |
| 4 | China – United Kingdom | 157 |
| 5 | United Kingdom – United States | 154 |
| 6 | China – Italy | 152 |
| 7 | Canada – United States | 134 |
| 8 | Australia – China | 123 |
| 9 | Germany – United States | 110 |
| 10 | India – United States | 97 |
| 11 | Singapore – United States | 89 |
| 12 | Korea, Republic of – United States | 84 |
| 13 | Italy – United States | 77 |
| 14 | Australia – United States | 76 |
| 15 | Hong Kong – United States | 71 |
| 16 | Canada – China | 62 |
| 17 | Germany – United Kingdom | 59 |
| 18 | United Kingdom – Italy | 56 |
| 19 | Japan – United States | 45 |
| 20 | Germany – Italy | 44 |

## Most-cited papers within the corpus

Top papers by total in-corpus citations, with how many come from the *other* community (cross-community incoming).

| Rank | Cluster | Venue | In-cites (total) | of which cross | Title |
|---:|---|---|---:|---:|---|
| 1 | CL | ACL | 1700 | 98 | DenseLoRA: Dense Low-Rank Adaptation of Large Language Models |
| 2 | CL | NAACL | 875 | 18 | KMMLU: Measuring Massive Multitask Language Understanding in Korean |
| 3 | CL | ACL | 340 | 21 | Scaling Laws for Multilingual Language Models |
| 4 | IR | SIGIR | 162 | 137 | Axioms for Retrieval-Augmented Generation |
| 5 | CL | ACL | 115 | 4 | Smarter, Better, Faster, Longer: A Modern Bidirectional Encoder for Fa |
| 6 | CL | EMNLP | 113 | 9 | FinMTEB: Finance Massive Text Embedding Benchmark |
| 7 | CL | NAACL | 106 | 1 | RewardBench: Evaluating Reward Models for Language Modeling |
| 8 | CL | EMNLP | 82 | 4 | Protein Large Language Models: A Comprehensive Survey |
| 9 | CL | ACL | 69 | 0 | SemEval-2025 Task 11: Bridging the Gap in Text-Based Emotion Detection |
| 10 | CL | ACL | 66 | 0 | Ensemble Watermarks for Large Language Models |
| 11 | IR | SIGIR | 63 | 55 | Parametric Retrieval Augmented Generation |
| 12 | CL | NAACL | 61 | 2 | Knowledge Distillation for Language Models |
| 13 | CL | ACL | 60 | 6 | Knowledge Boundary of Large Language Models: A Survey |
| 14 | CL | EMNLP | 60 | 3 | From Generation to Judgment: Opportunities and Challenges of LLM-as-a- |
| 15 | CL | NAACL | 57 | 10 | GRAG: Graph Retrieval-Augmented Generation |
| 16 | IR | CIKM | 52 | 23 | Local Large Language Models for Recommendation. |
| 17 | CL | NAACL | 49 | 3 | GPT-NER: Named Entity Recognition via Large Language Models |
| 18 | IR | SIGIR | 49 | 14 | Intent Representation Learning with Large Language Model for Recommend |
| 19 | CL | ACL | 45 | 0 | ShortGPT: Layers in Large Language Models are More Redundant Than You  |
| 20 | CL | COLING | 45 | 0 | Evaluating the Capabilities of Large Language Models for Multi-label E |
| 21 | CL | ACL | 42 | 0 | SemEval-2025 Task 3: Mu-SHROOM, the Multilingual Shared-task on Halluc |
| 22 | CL | ACL | 40 | 0 | ProcessBench: Identifying Process Errors in Mathematical Reasoning |
| 23 | CL | NAACL | 40 | 0 | NormAd: A Framework for Measuring the Cultural Adaptability of Large L |
| 24 | CL | EMNLP | 39 | 3 | Continual Learning of Large Language Models |
| 25 | CL | ACL | 38 | 1 | The Lessons of Developing Process Reward Models in Mathematical Reason |
