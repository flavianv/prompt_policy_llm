# Research Questions

## Central Question

Can a small learned policy discover better ways to prompt a frozen frontier model than static prompt engineering?

## Experiment Questions

- How much lift comes from the controller versus extra prompt tokens?
- Does controller scale from 270M to 600M to 1.7B improve reward, or does the back end dominate?
- Are learned instructions benchmark-specific or reusable across task families?
- Does the controller learn interpretable strategies, or opaque benchmark hacks?
- How sensitive are gains to the 30-token instruction budget?
- What is the latency and cost frontier for each controller size?

## Risk Questions

- Does the controller overfit benchmark verifiers?
- Does it learn brittle formatting tricks instead of task-solving strategy?
- Does it increase back-end hallucination or invalid output rate?
- Does inference cost erase the value of any accuracy lift?
- Does short-instruction optimization transfer to noisier domains?

