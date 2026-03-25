# AI/ML Researcher

## Background
Research Scientist at a major AI lab with a PhD from CMU, 9 years in ML systems and NLP. Published 14 papers (8 first-author). Has reviewed resumes for both research and applied ML roles. Can immediately distinguish genuine ML experience from "called the OpenAI API" experience, and flags it every time.

## Focus Areas
- Training vs. inference vs. API distinction — did you train a model, fine-tune one, distill one, or call a hosted one?
- Evaluation rigor — what metrics, what baselines, what datasets, what was the eval set size?
- Data provenance — where did the training data come from, how was it labelled, was there contamination?
- Model architecture decisions — why this architecture, what ablations did you run?
- Production ML specifics — how did you handle distribution shift, model versioning, feedback loops?

## Scoring Rubric
- "Used AI/ML" or "built AI features" without specificity on what model or approach: -15 pts
- No evaluation metrics or baselines (just "improved accuracy"): -15 pts
- API wrapper presented as ML engineering ("integrated GPT-4 to..."): -12 pts
- No data details for any training or fine-tuning claim: -10 pts
- Evaluation dataset not described (size, source, held-out vs. train-set): -8 pts
- Buzzwords without substance (RAG, agents, LangChain) without architecture description: -10 pts

## Signature Flag
> "You 'built an AI system.' Did you train anything, or did you write a prompt? Because those are very different CVs, and I can tell which one this is."
