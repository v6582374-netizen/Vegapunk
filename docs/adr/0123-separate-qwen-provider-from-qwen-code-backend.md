# Separate the Qwen Provider from the Qwen Code Backend

InternAgent will integrate Qwen as a first-class Model Provider and Qwen Code as a separate first-class Experiment Backend alongside Claude Code and iFlow.
Qwen Code will not be hidden behind the Claude Code Backend because model inference routing and coding-agent workspace execution are independently selectable responsibilities that must be able to evolve without coupling.
