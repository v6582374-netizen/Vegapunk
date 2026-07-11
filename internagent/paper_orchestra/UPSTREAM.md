# PaperOrchestra upstream

- Repository: https://github.com/declare-lab/paper-orchestra
- Imported commit: `ca1b3fa01c2970fc7cda32d16245db38d57b3f56`
- License: Apache License 2.0; see `LICENSE`

This package is an InternAgent-native asynchronous adaptation of PaperOrchestra's outline, literature writing, section writing, content reflection, agent review, layout review, and PDF utility architecture.

The adaptation removes provider-specific Gemini/OpenAI clients, online paper search, Plotting Agent, frontend, batch, and benchmark paths. Model calls use InternAgent's shared `BaseModel`; literature inputs come only from the selected Idea's approved citation map; figures come only from existing experiment artifacts.
