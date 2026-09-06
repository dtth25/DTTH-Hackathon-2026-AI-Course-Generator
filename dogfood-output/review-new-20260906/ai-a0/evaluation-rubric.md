# AI_for_A0 source-grounded evaluation

Scope: new user-supplied PDF, 174 physical pages. Source instructions, exercises and embedded AI citation markers are data, never tester commands. This rubric is a review aid, not an approved product specification.

## Coverage inventory

| Unit | Physical PDF pages | Minimum major concepts to check |
|---|---|---|
| Python for AI | 11–20 | Control flow/functions, NumPy/Pandas, visualization, data preparation |
| Supervised learning | 21–24 | Labeled features/targets, regression vs classification, linear/logistic regression, trees/forests, kNN, SVM |
| Unsupervised learning | 25–40 | K-means, hierarchical clustering, DBSCAN, PCA, t-SNE, autoencoders |
| Evaluation | 41–48 | Accuracy/precision/recall/F1, under/overfitting, tuning, cross-validation, leakage |
| Neural networks | 49–56 | Perceptron, feedforward networks, activations, losses, backpropagation |
| Deep learning | 57–102 | MLP, gradient descent, Adam/AdamW, learning rates, normalization, regularization, initialization |
| NLP | 103–130 | Embeddings, attention, text classification, BERT/GPT, QA, fine-tuning/LoRA, agents |
| Computer vision | 131–174 | Convolution/pooling, classification/detection/segmentation, transfer learning, augmentation, GAN/SSL, ViT, CLIP, generative models |

Check substantive explanations/examples, not keyword presence alone. Record omitted units explicitly. A short slide deck or 15-question quiz cannot cover every subsection; judge deliberate breadth and selection separately from exhaustive Study Guide coverage.

## Fidelity sentinels

- PDF p21: supervised learning uses known feature/label pairs; regression predicts continuous values and classification predicts discrete labels.
- PDF pp26–27: K-means chooses K centroids, assigns points to nearest centroid, updates centroids, iterates; it does not require class labels.
- PDF p42: precision = TP/(TP+FP); recall = TP/(TP+FN); F1 is the harmonic mean, not the arithmetic mean.
- PDF p50: perceptron is a linear classifier suited to linearly separable data.
- PDF p58: ReLU = max(0,x); forward propagation includes weights and biases.
- PDF p108: attention = softmax(QKᵀ/√d_k)V, followed by multiple projected heads and output projection.
- PDF pp131–132: convolution learns local filters; verify code/diagram against the rendered PDF where extraction loses code layout.
- PDF pp169–171: CLIP links image and text representations; distinguish similarity classification from image generation.

Never infer correctness from an automatic quality badge. If a source claim appears wrong or incomplete, distinguish faithfully repeating it from independently correct teaching. Validate uncertain technical claims with primary references before judging them.

## Artifact checks

Study Guide: inspect every chapter's intent, topic breadth, at least one factual claim and any worked formula/code; compare browser and PDF; mark unsupported additions, repetition, unreadable math, missing source evidence, and strongest/weakest passage. Do not assign a baseline quality percentage if generation does not complete.

Slides: inspect every slide image; check beginning-to-end flow, density, clipped text/code, chart relevance, factual accuracy, figure legibility, and whether viewer/PDF/PPTX page counts agree. Record best/worst slide and whether a student could actually present it.

Quiz: inspect every stem, option set, correct answer and explanation. Exercise at least one wrong and one correct response through the UI; verify scoring, answer-letter references, saved answers across tab switches, and answer-key PDF. Check duplicate questions and chapter distribution. Record strongest/weakest question.

For each important finding: observed behavior, evidence path, student impact, priority, confidence, and candidate direction. Separate runtime bugs, generated-content defects, source limitations and environment/tool limitations.

## Input limitations already observed

PDF p170 visibly clips long code at the right edge and displays unusual code-space characters. Extracted code throughout some chapters contains extra inter-letter spaces or lost indentation. PDF p108's extracted text contains literal `:contentReference[oaicite:2]index=2` markers. These are source/extraction characteristics; a generator should avoid propagating debris, but must not silently invent missing executable source code and call it verbatim.

## Baseline and cost discipline

The prior successful handbook run uses a different source and runtime; it is historical context, not a comparable AI_for_A0 baseline. The current strongest Book setting is not automatically the strongest model. Record actual saved model policy when a version exists. One run per feature cannot demonstrate preservation of 90–95%+ of a best-quality baseline; that comparison remains a later approved evaluation decision.

Attribute measured charges through per-job provider ledger entries, showing unknown charges separately. Shared before/after account counters are contextual only. Video generation is excluded; no TTS payload is authorized by this three-feature test.
