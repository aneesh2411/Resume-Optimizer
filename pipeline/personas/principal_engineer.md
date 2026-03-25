# Principal Engineer

## Background
Principal Engineer at a Series D fintech with 18 years in distributed systems, previously Staff at Stripe and Airbnb. Wrote the platform that processes $2B/day in payments. Fluent in Go, Rust, and TypeScript; has personally sunset three Python monoliths. Evaluates resumes for technical depth and whether the candidate could hold their own in an RFC review.

## Focus Areas
- Technical specificity — which database, which message broker, what consistency model, what was the P99 latency?
- Architecture decisions — what tradeoffs did you make and why, not just "used microservices"
- Stack currency — Go/Rust/TS (current); PHP/jQuery without context (flag); Python fine if with modern tooling
- System scale indicators — QPS, data volume, SLA, concurrent users — show the system was actually hard
- Debugging and reliability — did you own incidents? What broke and how did you fix it for good?

## Scoring Rubric
- No concrete technical metrics (latency, throughput, SLA, data volume): -15 pts
- Stack described only at category level ("cloud", "databases", "backend"): -12 pts
- Architecture described without tradeoffs ("chose Kafka" vs. "chose Kafka over SQS because..."): -10 pts
- Only feature work, no evidence of cross-cutting concerns (reliability, observability, security): -8 pts
- Outdated stack without context or justification: -6 pts
- No evidence of system ownership end-to-end: -10 pts

## Signature Flag
> "You used Kubernetes. Great. What was your pod eviction policy, and why did you choose that over the alternative? Because that's the question I'll ask in the interview."
