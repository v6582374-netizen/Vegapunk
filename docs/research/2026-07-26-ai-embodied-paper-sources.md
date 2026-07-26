# AI Scientist 与具身智能高热论文来源

调研日期：2026-07-26

## 使用边界

本文件是高热论文模块可导入的真实论文来源清单，不是产品中直接展示的文案。
两个领域各有 20 篇记录。
自主科学部分优先选取同行评审期刊论文。
具身智能部分保留该领域公认的重要 RSS、CoRL、CVPR、ICCV、ICML、AAAI 与 ICRA 论文，并在 `venue` 中明确标注为会议论文。
个别会议论文没有独立出版 DOI 时，`doi` 使用 Crossref 登记的 arXiv DOI，并且 `venue` 不将其描述为期刊。

## 核验方法

- 书目信息和摘要依据 OpenAlex Works 元数据核验，并以 DOI 解析链接指向出版商或会议的正式记录。
- 对可由 Crossref Works 直接返回的 DOI，额外比对题名、首作者、载体与年份。
- `abstract` 是原始摘要的简短、忠实事实摘述，未补写论文没有报告的结果。
- `url` 均为 DOI 解析链接，可作为前端后续按需拉取或人工复核的稳定入口。

主要元数据入口：[OpenAlex Works API](https://docs.openalex.org/api-entities/works/work-object) 和 [Crossref REST API](https://api.crossref.org/swagger-ui/index.html)。

## 可机读记录

```json
[
  {
    "domain": "AI Scientist / autonomous scientific discovery",
    "title": "Self-Driving Laboratories for Chemistry and Materials Science",
    "authors": "Gary Tom et al.",
    "venue": "Chemical Reviews (peer-reviewed journal)",
    "year": 2024,
    "doi": "10.1021/acs.chemrev.4c00055",
    "url": "https://doi.org/10.1021/acs.chemrev.4c00055",
    "abstract": "Reviews self-driving laboratories that join automated workflows with autonomous experiment planning, covering enabling hardware, software, integration, applications, and limitations across chemistry and materials discovery.",
    "tags": ["self-driving laboratory", "chemistry", "materials discovery"]
  },
  {
    "domain": "AI Scientist / autonomous scientific discovery",
    "title": "Next-Generation Experimentation with Self-Driving Laboratories",
    "authors": "Florian Häse et al.",
    "venue": "Trends in Chemistry (peer-reviewed journal)",
    "year": 2019,
    "doi": "10.1016/j.trechm.2019.02.007",
    "url": "https://doi.org/10.1016/j.trechm.2019.02.007",
    "abstract": "Describes self-driving laboratories as closed experimentation loops that combine automation, characterization, machine learning, and experiment design to accelerate discovery.",
    "tags": ["self-driving laboratory", "experimental design", "automation"]
  },
  {
    "domain": "AI Scientist / autonomous scientific discovery",
    "title": "Self-driving laboratories to autonomously navigate the protein fitness landscape",
    "authors": "Jacob Rapp et al.",
    "venue": "Nature Chemical Engineering (peer-reviewed journal)",
    "year": 2024,
    "doi": "10.1038/s44286-023-00002-4",
    "url": "https://doi.org/10.1038/s44286-023-00002-4",
    "abstract": "Presents SAMPLE, a fully autonomous protein-engineering platform in which an agent learns sequence-function relations, designs proteins, and receives robotic experimental feedback; it identifies thermostable glycoside hydrolases.",
    "tags": ["protein engineering", "active learning", "robotic laboratory"]
  },
  {
    "domain": "AI Scientist / autonomous scientific discovery",
    "title": "An autonomous laboratory for the accelerated synthesis of inorganic materials",
    "authors": "Nathan J. Szymanski et al.",
    "venue": "Nature (peer-reviewed journal)",
    "year": 2023,
    "doi": "10.1038/s41586-023-06734-w",
    "url": "https://doi.org/10.1038/s41586-023-06734-w",
    "abstract": "Introduces A-Lab, which couples computation, literature data, machine learning, active learning, and robotics for inorganic powder synthesis; the system realized 41 novel compounds from 58 targets over 17 days.",
    "tags": ["autonomous lab", "inorganic synthesis", "active learning"]
  },
  {
    "domain": "AI Scientist / autonomous scientific discovery",
    "title": "Autonomous Chemical Experiments: Challenges and Perspectives on Establishing a Self-Driving Lab",
    "authors": "Martin Seifrid et al.",
    "venue": "Accounts of Chemical Research (peer-reviewed journal)",
    "year": 2022,
    "doi": "10.1021/acs.accounts.2c00220",
    "url": "https://doi.org/10.1021/acs.accounts.2c00220",
    "abstract": "Examines how data-driven automated laboratories can shorten discovery cycles, using self-driving labs for organic semiconductor lasers and thin-film materials to discuss cognitive, software, and physical-handling challenges.",
    "tags": ["autonomous chemistry", "open data", "laboratory automation"]
  },
  {
    "domain": "AI Scientist / autonomous scientific discovery",
    "title": "The rise of self-driving labs in chemical and materials sciences",
    "authors": "Milad Abolhasani et al.",
    "venue": "Nature Synthesis (peer-reviewed journal)",
    "year": 2023,
    "doi": "10.1038/s44160-022-00231-0",
    "url": "https://doi.org/10.1038/s44160-022-00231-0",
    "abstract": "Surveys the emergence of self-driving laboratories in chemical and materials research and frames the integration of automation and data-driven decision-making as a route to faster discovery.",
    "tags": ["self-driving laboratory", "materials science", "chemical synthesis"]
  },
  {
    "domain": "AI Scientist / autonomous scientific discovery",
    "title": "Autonomous chemical research with large language models",
    "authors": "Daniil A. Boiko et al.",
    "venue": "Nature (peer-reviewed journal)",
    "year": 2023,
    "doi": "10.1038/s41586-023-06792-0",
    "url": "https://doi.org/10.1038/s41586-023-06792-0",
    "abstract": "Reports Coscientist, a GPT-4-driven system that uses search, code execution, and laboratory automation to design, plan, and perform experiments, including palladium-catalysed cross-coupling optimization.",
    "tags": ["large language models", "autonomous chemistry", "tool use"]
  },
  {
    "domain": "AI Scientist / autonomous scientific discovery",
    "title": "A dynamic knowledge graph approach to distributed self-driving laboratories",
    "authors": "Jiaru Bai et al.",
    "venue": "Nature Communications (peer-reviewed journal)",
    "year": 2024,
    "doi": "10.1038/s41467-023-44599-9",
    "url": "https://doi.org/10.1038/s41467-023-44599-9",
    "abstract": "Develops a dynamic-knowledge-graph architecture for distributed self-driving labs and demonstrates a real-time, cross-site closed-loop aldol-condensation optimization with robots in Cambridge and Singapore.",
    "tags": ["knowledge graph", "distributed laboratory", "provenance"]
  },
  {
    "domain": "AI Scientist / autonomous scientific discovery",
    "title": "ChemOS: An orchestration software to democratize autonomous discovery",
    "authors": "Loic M. Roch et al.",
    "venue": "PLOS ONE (peer-reviewed journal)",
    "year": 2020,
    "doi": "10.1371/journal.pone.0229862",
    "url": "https://doi.org/10.1371/journal.pone.0229862",
    "abstract": "Introduces ChemOS, a modular software layer for deploying and remotely operating self-driving laboratories at different autonomy levels, demonstrated across five automated-equipment applications.",
    "tags": ["orchestration", "lab software", "autonomous discovery"]
  },
  {
    "domain": "AI Scientist / autonomous scientific discovery",
    "title": "Universal self-driving laboratory for accelerated discovery of materials and molecules",
    "authors": "Robert W. Epps et al.",
    "venue": "Chem (peer-reviewed journal)",
    "year": 2021,
    "doi": "10.1016/j.chempr.2021.09.004",
    "url": "https://doi.org/10.1016/j.chempr.2021.09.004",
    "abstract": "Presents a universal self-driving-laboratory approach for coordinating autonomous experimental design and laboratory execution across materials and molecular discovery workflows.",
    "tags": ["universal laboratory", "materials", "molecular discovery"]
  },
  {
    "domain": "AI Scientist / autonomous scientific discovery",
    "title": "AlphaFlow: autonomous discovery and optimization of multi-step chemistry using a self-driven fluidic lab guided by reinforcement learning",
    "authors": "Amanda A. Volk et al.",
    "venue": "Nature Communications (peer-reviewed journal)",
    "year": 2023,
    "doi": "10.1038/s41467-023-37139-y",
    "url": "https://doi.org/10.1038/s41467-023-37139-y",
    "abstract": "Introduces a reinforcement-learning-guided microdroplet laboratory for multi-step chemistry; it discovers and optimizes core-shell nanoparticle synthesis routes with up to 40 parameters using in-house data.",
    "tags": ["reinforcement learning", "microfluidics", "nanoparticles"]
  },
  {
    "domain": "AI Scientist / autonomous scientific discovery",
    "title": "On-the-fly closed-loop materials discovery via Bayesian active learning",
    "authors": "A. Gilad Kusne et al.",
    "venue": "Nature Communications (peer-reviewed journal)",
    "year": 2020,
    "doi": "10.1038/s41467-020-19597-w",
    "url": "https://doi.org/10.1038/s41467-020-19597-w",
    "abstract": "Demonstrates CAMEO, an active-learning-driven autonomous system at a synchrotron beamline for phase mapping and property optimization, including discovery of a novel epitaxial nanocomposite phase-change material.",
    "tags": ["Bayesian active learning", "materials discovery", "synchrotron"]
  },
  {
    "domain": "AI Scientist / autonomous scientific discovery",
    "title": "Autonomous discovery of optically active chiral inorganic perovskite nanocrystals through an intelligent cloud lab",
    "authors": "Jiagen Li et al.",
    "venue": "Nature Communications (peer-reviewed journal)",
    "year": 2020,
    "doi": "10.1038/s41467-020-15728-5",
    "url": "https://doi.org/10.1038/s41467-020-15728-5",
    "abstract": "Builds an intelligent cloud laboratory that combines automation, cloud services, and AI to autonomously synthesize, characterize, and optimize chiral inorganic perovskite nanocrystals.",
    "tags": ["cloud laboratory", "perovskites", "autonomous synthesis"]
  },
  {
    "domain": "AI Scientist / autonomous scientific discovery",
    "title": "Progress and prospects for accelerating materials science with automated and autonomous workflows",
    "authors": "Helge S. Stein et al.",
    "venue": "Chemical Science (peer-reviewed journal)",
    "year": 2019,
    "doi": "10.1039/c9sc03766g",
    "url": "https://doi.org/10.1039/c9sc03766g",
    "abstract": "Provides a framework and ontology for materials experiment lifecycles, mapping automation levels and the expert decisions needed to extend autonomous loops across materials workflows.",
    "tags": ["materials acceleration", "workflow ontology", "automation"]
  },
  {
    "domain": "AI Scientist / autonomous scientific discovery",
    "title": "Toward autonomous laboratories: Convergence of artificial intelligence and experimental automation",
    "authors": "Yunchao Xie et al.",
    "venue": "Progress in Materials Science (peer-reviewed journal)",
    "year": 2022,
    "doi": "10.1016/j.pmatsci.2022.101043",
    "url": "https://doi.org/10.1016/j.pmatsci.2022.101043",
    "abstract": "Reviews the convergence of artificial intelligence, experimental automation, and materials science required to build autonomous laboratories and identifies practical integration challenges.",
    "tags": ["autonomous laboratory", "AI", "experimental automation"]
  },
  {
    "domain": "AI Scientist / autonomous scientific discovery",
    "title": "ChemOS 2.0: An orchestration architecture for chemical self-driving laboratories",
    "authors": "Malcolm Sim et al.",
    "venue": "Matter (peer-reviewed journal)",
    "year": 2024,
    "doi": "10.1016/j.matt.2024.04.022",
    "url": "https://doi.org/10.1016/j.matt.2024.04.022",
    "abstract": "Describes ChemOS 2.0, an orchestration architecture for integrating and coordinating chemical self-driving-laboratory instruments and decision loops.",
    "tags": ["ChemOS", "orchestration", "chemical laboratory"]
  },
  {
    "domain": "AI Scientist / autonomous scientific discovery",
    "title": "Toward autonomous design and synthesis of novel inorganic materials",
    "authors": "Nathan J. Szymanski et al.",
    "venue": "Materials Horizons (peer-reviewed journal)",
    "year": 2021,
    "doi": "10.1039/d1mh00495f",
    "url": "https://doi.org/10.1039/d1mh00495f",
    "abstract": "Reviews autonomous inorganic-materials synthesis, including robotic synthesis and characterization, deep-learning-assisted phase identification, and active-learning optimization for closed-loop design.",
    "tags": ["inorganic materials", "robotics", "closed-loop optimization"]
  },
  {
    "domain": "AI Scientist / autonomous scientific discovery",
    "title": "A mobile robotic chemist",
    "authors": "Benjamin Burger et al.",
    "venue": "Nature (peer-reviewed journal)",
    "year": 2020,
    "doi": "10.1038/s41586-020-2442-2",
    "url": "https://doi.org/10.1038/s41586-020-2442-2",
    "abstract": "Demonstrates a mobile robot that works in a standard laboratory, plans experiments from prior knowledge, operates instruments, and searches photocatalyst conditions for hydrogen production.",
    "tags": ["mobile robot", "photocatalysis", "laboratory automation"]
  },
  {
    "domain": "AI Scientist / autonomous scientific discovery",
    "title": "Autonomous mobile robots for exploratory synthetic chemistry",
    "authors": "Tianwei Dai et al.",
    "venue": "Nature (peer-reviewed journal)",
    "year": 2024,
    "doi": "10.1038/s41586-024-08173-7",
    "url": "https://doi.org/10.1038/s41586-024-08173-7",
    "abstract": "Uses mobile robots, automated synthesis, liquid chromatography-mass spectrometry, and benchtop NMR in a modular autonomous workflow for exploratory synthetic chemistry and reproducibility checking.",
    "tags": ["mobile robots", "synthetic chemistry", "closed-loop experimentation"]
  },
  {
    "domain": "AI Scientist / autonomous scientific discovery",
    "title": "Data-science driven autonomous process optimization",
    "authors": "Melodie Christensen et al.",
    "venue": "Communications Chemistry (peer-reviewed journal)",
    "year": 2021,
    "doi": "10.1038/s42004-021-00550-x",
    "url": "https://doi.org/10.1038/s42004-021-00550-x",
    "abstract": "Presents a closed-loop batch system for autonomous process optimization and applies it to a stereoselective Suzuki-Miyaura coupling, including a computed-feature strategy for selecting diverse phosphine ligands.",
    "tags": ["process optimization", "Suzuki-Miyaura", "closed-loop chemistry"]
  },
  {
    "domain": "Embodied intelligence / embodied AI",
    "title": "Foundation models in robotics: Applications, challenges, and the future",
    "authors": "Roya Firoozi et al.",
    "venue": "The International Journal of Robotics Research (peer-reviewed journal)",
    "year": 2024,
    "doi": "10.1177/02783649241281508",
    "url": "https://doi.org/10.1177/02783649241281508",
    "abstract": "Surveys how pretrained foundation models can contribute to robot perception, decision-making, and control, while identifying data, safety, uncertainty, and real-time-execution challenges.",
    "tags": ["foundation models", "robot autonomy", "survey"]
  },
  {
    "domain": "Embodied intelligence / embodied AI",
    "title": "Habitat: A Platform for Embodied AI Research",
    "authors": "Manolis Savva et al.",
    "venue": "ICCV 2019 (archival conference proceedings)",
    "year": 2019,
    "doi": "10.1109/ICCV.2019.00943",
    "url": "https://doi.org/10.1109/ICCV.2019.00943",
    "abstract": "Introduces Habitat-Sim and Habitat-API for efficient photorealistic embodied-AI training and benchmarking, and reports point-goal navigation scaling and cross-dataset generalization experiments.",
    "tags": ["simulation", "navigation", "benchmark"]
  },
  {
    "domain": "Embodied intelligence / embodied AI",
    "title": "Vision-and-Language Navigation: Interpreting Visually-Grounded Navigation Instructions in Real Environments",
    "authors": "Peter Anderson et al.",
    "venue": "CVPR 2018 (archival conference proceedings)",
    "year": 2018,
    "doi": "10.1109/CVPR.2018.00387",
    "url": "https://doi.org/10.1109/CVPR.2018.00387",
    "abstract": "Introduces the Matterport3D Simulator and Room-to-Room benchmark for agents that follow visually grounded natural-language navigation instructions in real buildings.",
    "tags": ["vision-language navigation", "Matterport3D", "benchmark"]
  },
  {
    "domain": "Embodied intelligence / embodied AI",
    "title": "Embodied Question Answering",
    "authors": "Abhishek Das et al.",
    "venue": "CVPR 2018 (archival conference proceedings)",
    "year": 2018,
    "doi": "10.1109/CVPR.2018.00008",
    "url": "https://doi.org/10.1109/CVPR.2018.00008",
    "abstract": "Defines EmbodiedQA, where an agent must navigate a 3D environment using egocentric vision to gather evidence before answering a question, and supplies a dataset, metrics, and hierarchical model.",
    "tags": ["embodied question answering", "active perception", "navigation"]
  },
  {
    "domain": "Embodied intelligence / embodied AI",
    "title": "ALFRED: A Benchmark for Interpreting Grounded Instructions for Everyday Tasks",
    "authors": "Mohit Shridhar et al.",
    "venue": "CVPR 2020 (archival conference proceedings)",
    "year": 2020,
    "doi": "10.1109/CVPR42600.2020.01075",
    "url": "https://doi.org/10.1109/CVPR42600.2020.01075",
    "abstract": "Introduces ALFRED, a benchmark mapping natural-language instructions and egocentric vision to action sequences for household tasks with long, compositional instructions and non-reversible state changes.",
    "tags": ["household tasks", "language grounding", "benchmark"]
  },
  {
    "domain": "Embodied intelligence / embodied AI",
    "title": "TEACh: Task-Driven Embodied Agents That Chat",
    "authors": "Aishwarya Padmakumar et al.",
    "venue": "AAAI 2022 (archival conference proceedings)",
    "year": 2022,
    "doi": "10.1609/AAAI.V36I2.20097",
    "url": "https://doi.org/10.1609/AAAI.V36I2.20097",
    "abstract": "Provides a dataset of more than 3,000 interactive human-human dialogues for simulated household tasks and benchmarks dialogue understanding, language grounding, and task execution by embodied agents.",
    "tags": ["dialogue", "household agents", "language grounding"]
  },
  {
    "domain": "Embodied intelligence / embodied AI",
    "title": "RT-1: Robotics Transformer for Real-World Control at Scale",
    "authors": "Anthony Brohan et al.",
    "venue": "Robotics: Science and Systems 2023 (archival conference proceedings)",
    "year": 2023,
    "doi": "10.15607/RSS.2023.XIX.025",
    "url": "https://doi.org/10.15607/RSS.2023.XIX.025",
    "abstract": "Introduces Robotics Transformer, a scalable model class trained on diverse real-robot data, and studies how data size, model size, and data diversity affect generalization for real-world control.",
    "tags": ["robot transformer", "real-world control", "generalization"]
  },
  {
    "domain": "Embodied intelligence / embodied AI",
    "title": "RT-2: Vision-Language-Action Models Transfer Web Knowledge to Robotic Control",
    "authors": "Anthony Brohan et al.",
    "venue": "Conference on Robot Learning 2023 (archival conference proceedings)",
    "year": 2023,
    "doi": "10.48550/arXiv.2307.15818",
    "url": "https://doi.org/10.48550/arXiv.2307.15818",
    "abstract": "Proposes vision-language-action models that co-fine-tune vision-language models on robotic trajectories and web tasks by representing actions as text tokens; evaluations report improved novel-object generalization and semantic reasoning.",
    "tags": ["vision-language-action", "robot control", "foundation models"]
  },
  {
    "domain": "Embodied intelligence / embodied AI",
    "title": "PaLM-E: An Embodied Multimodal Language Model",
    "authors": "Danny Driess et al.",
    "venue": "ICML 2023 (archival conference proceedings)",
    "year": 2023,
    "doi": "10.48550/arXiv.2303.03378",
    "url": "https://doi.org/10.48550/arXiv.2303.03378",
    "abstract": "Introduces embodied language models that interleave visual, continuous state, and text inputs for robotic planning and other embodied tasks, reporting transfer from joint training with language and vision data.",
    "tags": ["multimodal language model", "robot planning", "grounding"]
  },
  {
    "domain": "Embodied intelligence / embodied AI",
    "title": "Do As I Can, Not As I Say: Grounding Language in Robotic Affordances",
    "authors": "Michael Ahn et al.",
    "venue": "Conference on Robot Learning 2022 (archival conference proceedings)",
    "year": 2022,
    "doi": "10.48550/arXiv.2204.01691",
    "url": "https://doi.org/10.48550/arXiv.2204.01691",
    "abstract": "Combines large-language-model task proposals with pretrained robot skills and value functions so high-level language is constrained by what a mobile manipulator can actually do in its environment.",
    "tags": ["SayCan", "affordances", "language-grounded robotics"]
  },
  {
    "domain": "Embodied intelligence / embodied AI",
    "title": "PerAct: Multi-Task 6D Robotic Manipulation with Perceiver-Actor",
    "authors": "Mohit Shridhar et al.",
    "venue": "Conference on Robot Learning 2022 (archival conference proceedings)",
    "year": 2022,
    "doi": "10.48550/arXiv.2209.05451",
    "url": "https://doi.org/10.48550/arXiv.2209.05451",
    "abstract": "Introduces Perceiver-Actor, a language-conditioned multi-task policy for 6D manipulation that learns from voxelized RGB-D observations and is evaluated in simulated and real robot settings.",
    "tags": ["6D manipulation", "multitask learning", "Perceiver"]
  },
  {
    "domain": "Embodied intelligence / embodied AI",
    "title": "CLIPort: What and Where Pathways for Robotic Manipulation",
    "authors": "Mohit Shridhar et al.",
    "venue": "Conference on Robot Learning 2021 (archival conference proceedings)",
    "year": 2021,
    "doi": "10.48550/arXiv.2109.12098",
    "url": "https://doi.org/10.48550/arXiv.2109.12098",
    "abstract": "Combines CLIP semantic representations with spatial Transporter-style pathways for language-conditioned tabletop manipulation, reporting few-shot efficiency and generalization across simulated and real tasks.",
    "tags": ["CLIP", "manipulation", "language conditioning"]
  },
  {
    "domain": "Embodied intelligence / embodied AI",
    "title": "R3M: A Universal Visual Representation for Robot Manipulation",
    "authors": "Suraj Nair et al.",
    "venue": "Conference on Robot Learning 2022 (archival conference proceedings)",
    "year": 2022,
    "doi": "10.48550/arXiv.2203.12601",
    "url": "https://doi.org/10.48550/arXiv.2203.12601",
    "abstract": "Pretrains a visual representation on Ego4D human video with time-contrastive learning and video-language alignment, then uses it as frozen perception for data-efficient simulated and real robot manipulation.",
    "tags": ["visual representation", "Ego4D", "manipulation"]
  },
  {
    "domain": "Embodied intelligence / embodied AI",
    "title": "MimicPlay: Long-Horizon Imitation Learning by Watching Human Play",
    "authors": "Chen Wang et al.",
    "venue": "Conference on Robot Learning 2023 (archival conference proceedings)",
    "year": 2023,
    "doi": "10.48550/arXiv.2302.12422",
    "url": "https://doi.org/10.48550/arXiv.2302.12422",
    "abstract": "Uses human play videos to learn latent plans that guide low-level visuomotor control trained from a small number of teleoperated demonstrations, evaluated on 14 real-world long-horizon manipulation tasks.",
    "tags": ["imitation learning", "human play", "long-horizon manipulation"]
  },
  {
    "domain": "Embodied intelligence / embodied AI",
    "title": "RVT: Robotic View Transformer for 3D Object Manipulation",
    "authors": "Ankit Goyal et al.",
    "venue": "Conference on Robot Learning 2023 (archival conference proceedings)",
    "year": 2023,
    "doi": "10.48550/arXiv.2306.14896",
    "url": "https://doi.org/10.48550/arXiv.2306.14896",
    "abstract": "Introduces a multi-view transformer for 3D manipulation that aggregates virtual camera views without an expensive voxel representation, and evaluates it across RLBench tasks and real-world demonstrations.",
    "tags": ["3D manipulation", "multi-view transformer", "RLBench"]
  },
  {
    "domain": "Embodied intelligence / embodied AI",
    "title": "Diffusion policy: Visuomotor policy learning via action diffusion",
    "authors": "Cheng Chi et al.",
    "venue": "The International Journal of Robotics Research (peer-reviewed journal)",
    "year": 2024,
    "doi": "10.1177/02783649241273668",
    "url": "https://doi.org/10.1177/02783649241273668",
    "abstract": "Formulates visuomotor policy learning as conditional denoising diffusion over robot actions and reports results on manipulation tasks requiring multimodal action distributions and high-dimensional control.",
    "tags": ["diffusion policy", "visuomotor control", "imitation learning"]
  },
  {
    "domain": "Embodied intelligence / embodied AI",
    "title": "Language-Driven Representation Learning for Robotics",
    "authors": "Siddharth Karamcheti et al.",
    "venue": "Robotics: Science and Systems 2023 (archival conference proceedings)",
    "year": 2023,
    "doi": "10.15607/RSS.2023.XIX.032",
    "url": "https://doi.org/10.15607/RSS.2023.XIX.032",
    "abstract": "Introduces Voltron, a language-driven representation-learning framework using video and captions, and evaluates visual representations over five robot-learning problems including control and affordance prediction.",
    "tags": ["representation learning", "language", "robot learning"]
  },
  {
    "domain": "Embodied intelligence / embodied AI",
    "title": "Scaling Robot Learning with Semantically Imagined Experience",
    "authors": "Tianhe Yu et al.",
    "venue": "Robotics: Science and Systems 2023 (archival conference proceedings)",
    "year": 2023,
    "doi": "10.15607/RSS.2023.XIX.027",
    "url": "https://doi.org/10.15607/RSS.2023.XIX.027",
    "abstract": "Uses text-to-image diffusion models to augment existing robot-manipulation datasets with imagined objects, backgrounds, and distractors, reporting improved robustness and generalization in real-world experiments.",
    "tags": ["data augmentation", "diffusion models", "robot generalization"]
  },
  {
    "domain": "Embodied intelligence / embodied AI",
    "title": "Octo: An Open-Source Generalist Robot Policy",
    "authors": "Dibya Ghosh et al.",
    "venue": "Robotics: Science and Systems 2024 (archival conference proceedings)",
    "year": 2024,
    "doi": "10.15607/RSS.2024.XX.090",
    "url": "https://doi.org/10.15607/RSS.2024.XX.090",
    "abstract": "Releases Octo, an open-source generalist robot policy pretrained on the Open X-Embodiment data, together with evaluations of adaptation to new robot-learning tasks.",
    "tags": ["generalist policy", "open source", "Open X-Embodiment"]
  },
  {
    "domain": "Embodied intelligence / embodied AI",
    "title": "Open X-Embodiment: Robotic Learning Datasets and RT-X Models",
    "authors": "A. O'Neill et al.",
    "venue": "ICRA 2024 (archival conference proceedings)",
    "year": 2024,
    "doi": "10.1109/ICRA57147.2024.10611477",
    "url": "https://doi.org/10.1109/ICRA57147.2024.10611477",
    "abstract": "Standardizes data from 22 robot embodiments and 21 institutions into Open X-Embodiment and presents RT-X models, reporting positive transfer of robot experience across platforms, tasks, and environments.",
    "tags": ["robot datasets", "cross-embodiment transfer", "RT-X"]
  }
]
```

## 导入前复核建议

在产品服务端首次入库时，对每个 `doi` 重新请求 Crossref 或 OpenAlex，并将返回的 title、authors、venue、year 与这份冻结来源清单逐字段比对。
不要把本文件中的摘要替代为模型生成的摘要，也不要将带 arXiv DOI 的会议论文显示为期刊论文。
