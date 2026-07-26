export const PAPER_DOMAINS = [
  "全部领域",
  "AI Scientist",
  "海水淡化",
  "燃气轮机",
  "反渗透",
  "具身智能",
] as const;

export type PaperDomain = (typeof PAPER_DOMAINS)[number];
export type CuratedPaperDomain = Exclude<PaperDomain, "全部领域">;

export type PaperRecord = {
  domain: CuratedPaperDomain;
  title: string;
  authors: string;
  venue: string;
  year: number;
  doi: string;
  url: string;
  abstract: string;
  tags: readonly string[];
};

const VERIFIED_PAPERS = [
  {
    "domain": "AI Scientist",
    "title": "Self-Driving Laboratories for Chemistry and Materials Science",
    "authors": "Gary Tom et al.",
    "venue": "Chemical Reviews (peer-reviewed journal)",
    "year": 2024,
    "doi": "10.1021/acs.chemrev.4c00055",
    "url": "https://doi.org/10.1021/acs.chemrev.4c00055",
    "abstract": "Reviews self-driving laboratories that join automated workflows with autonomous experiment planning, covering enabling hardware, software, integration, applications, and limitations across chemistry and materials discovery.",
    "tags": [
      "self-driving laboratory",
      "chemistry",
      "materials discovery"
    ]
  },
  {
    "domain": "AI Scientist",
    "title": "Next-Generation Experimentation with Self-Driving Laboratories",
    "authors": "Florian Häse et al.",
    "venue": "Trends in Chemistry (peer-reviewed journal)",
    "year": 2019,
    "doi": "10.1016/j.trechm.2019.02.007",
    "url": "https://doi.org/10.1016/j.trechm.2019.02.007",
    "abstract": "Describes self-driving laboratories as closed experimentation loops that combine automation, characterization, machine learning, and experiment design to accelerate discovery.",
    "tags": [
      "self-driving laboratory",
      "experimental design",
      "automation"
    ]
  },
  {
    "domain": "AI Scientist",
    "title": "Self-driving laboratories to autonomously navigate the protein fitness landscape",
    "authors": "Jacob Rapp et al.",
    "venue": "Nature Chemical Engineering (peer-reviewed journal)",
    "year": 2024,
    "doi": "10.1038/s44286-023-00002-4",
    "url": "https://doi.org/10.1038/s44286-023-00002-4",
    "abstract": "Presents SAMPLE, a fully autonomous protein-engineering platform in which an agent learns sequence-function relations, designs proteins, and receives robotic experimental feedback; it identifies thermostable glycoside hydrolases.",
    "tags": [
      "protein engineering",
      "active learning",
      "robotic laboratory"
    ]
  },
  {
    "domain": "AI Scientist",
    "title": "An autonomous laboratory for the accelerated synthesis of inorganic materials",
    "authors": "Nathan J. Szymanski et al.",
    "venue": "Nature (peer-reviewed journal)",
    "year": 2023,
    "doi": "10.1038/s41586-023-06734-w",
    "url": "https://doi.org/10.1038/s41586-023-06734-w",
    "abstract": "Introduces A-Lab, which couples computation, literature data, machine learning, active learning, and robotics for inorganic powder synthesis; the system realized 41 novel compounds from 58 targets over 17 days.",
    "tags": [
      "autonomous lab",
      "inorganic synthesis",
      "active learning"
    ]
  },
  {
    "domain": "AI Scientist",
    "title": "Autonomous Chemical Experiments: Challenges and Perspectives on Establishing a Self-Driving Lab",
    "authors": "Martin Seifrid et al.",
    "venue": "Accounts of Chemical Research (peer-reviewed journal)",
    "year": 2022,
    "doi": "10.1021/acs.accounts.2c00220",
    "url": "https://doi.org/10.1021/acs.accounts.2c00220",
    "abstract": "Examines how data-driven automated laboratories can shorten discovery cycles, using self-driving labs for organic semiconductor lasers and thin-film materials to discuss cognitive, software, and physical-handling challenges.",
    "tags": [
      "autonomous chemistry",
      "open data",
      "laboratory automation"
    ]
  },
  {
    "domain": "AI Scientist",
    "title": "The rise of self-driving labs in chemical and materials sciences",
    "authors": "Milad Abolhasani et al.",
    "venue": "Nature Synthesis (peer-reviewed journal)",
    "year": 2023,
    "doi": "10.1038/s44160-022-00231-0",
    "url": "https://doi.org/10.1038/s44160-022-00231-0",
    "abstract": "Surveys the emergence of self-driving laboratories in chemical and materials research and frames the integration of automation and data-driven decision-making as a route to faster discovery.",
    "tags": [
      "self-driving laboratory",
      "materials science",
      "chemical synthesis"
    ]
  },
  {
    "domain": "AI Scientist",
    "title": "Autonomous chemical research with large language models",
    "authors": "Daniil A. Boiko et al.",
    "venue": "Nature (peer-reviewed journal)",
    "year": 2023,
    "doi": "10.1038/s41586-023-06792-0",
    "url": "https://doi.org/10.1038/s41586-023-06792-0",
    "abstract": "Reports Coscientist, a GPT-4-driven system that uses search, code execution, and laboratory automation to design, plan, and perform experiments, including palladium-catalysed cross-coupling optimization.",
    "tags": [
      "large language models",
      "autonomous chemistry",
      "tool use"
    ]
  },
  {
    "domain": "AI Scientist",
    "title": "A dynamic knowledge graph approach to distributed self-driving laboratories",
    "authors": "Jiaru Bai et al.",
    "venue": "Nature Communications (peer-reviewed journal)",
    "year": 2024,
    "doi": "10.1038/s41467-023-44599-9",
    "url": "https://doi.org/10.1038/s41467-023-44599-9",
    "abstract": "Develops a dynamic-knowledge-graph architecture for distributed self-driving labs and demonstrates a real-time, cross-site closed-loop aldol-condensation optimization with robots in Cambridge and Singapore.",
    "tags": [
      "knowledge graph",
      "distributed laboratory",
      "provenance"
    ]
  },
  {
    "domain": "AI Scientist",
    "title": "ChemOS: An orchestration software to democratize autonomous discovery",
    "authors": "Loic M. Roch et al.",
    "venue": "PLOS ONE (peer-reviewed journal)",
    "year": 2020,
    "doi": "10.1371/journal.pone.0229862",
    "url": "https://doi.org/10.1371/journal.pone.0229862",
    "abstract": "Introduces ChemOS, a modular software layer for deploying and remotely operating self-driving laboratories at different autonomy levels, demonstrated across five automated-equipment applications.",
    "tags": [
      "orchestration",
      "lab software",
      "autonomous discovery"
    ]
  },
  {
    "domain": "AI Scientist",
    "title": "Universal self-driving laboratory for accelerated discovery of materials and molecules",
    "authors": "Robert W. Epps et al.",
    "venue": "Chem (peer-reviewed journal)",
    "year": 2021,
    "doi": "10.1016/j.chempr.2021.09.004",
    "url": "https://doi.org/10.1016/j.chempr.2021.09.004",
    "abstract": "Presents a universal self-driving-laboratory approach for coordinating autonomous experimental design and laboratory execution across materials and molecular discovery workflows.",
    "tags": [
      "universal laboratory",
      "materials",
      "molecular discovery"
    ]
  },
  {
    "domain": "AI Scientist",
    "title": "AlphaFlow: autonomous discovery and optimization of multi-step chemistry using a self-driven fluidic lab guided by reinforcement learning",
    "authors": "Amanda A. Volk et al.",
    "venue": "Nature Communications (peer-reviewed journal)",
    "year": 2023,
    "doi": "10.1038/s41467-023-37139-y",
    "url": "https://doi.org/10.1038/s41467-023-37139-y",
    "abstract": "Introduces a reinforcement-learning-guided microdroplet laboratory for multi-step chemistry; it discovers and optimizes core-shell nanoparticle synthesis routes with up to 40 parameters using in-house data.",
    "tags": [
      "reinforcement learning",
      "microfluidics",
      "nanoparticles"
    ]
  },
  {
    "domain": "AI Scientist",
    "title": "On-the-fly closed-loop materials discovery via Bayesian active learning",
    "authors": "A. Gilad Kusne et al.",
    "venue": "Nature Communications (peer-reviewed journal)",
    "year": 2020,
    "doi": "10.1038/s41467-020-19597-w",
    "url": "https://doi.org/10.1038/s41467-020-19597-w",
    "abstract": "Demonstrates CAMEO, an active-learning-driven autonomous system at a synchrotron beamline for phase mapping and property optimization, including discovery of a novel epitaxial nanocomposite phase-change material.",
    "tags": [
      "Bayesian active learning",
      "materials discovery",
      "synchrotron"
    ]
  },
  {
    "domain": "AI Scientist",
    "title": "Autonomous discovery of optically active chiral inorganic perovskite nanocrystals through an intelligent cloud lab",
    "authors": "Jiagen Li et al.",
    "venue": "Nature Communications (peer-reviewed journal)",
    "year": 2020,
    "doi": "10.1038/s41467-020-15728-5",
    "url": "https://doi.org/10.1038/s41467-020-15728-5",
    "abstract": "Builds an intelligent cloud laboratory that combines automation, cloud services, and AI to autonomously synthesize, characterize, and optimize chiral inorganic perovskite nanocrystals.",
    "tags": [
      "cloud laboratory",
      "perovskites",
      "autonomous synthesis"
    ]
  },
  {
    "domain": "AI Scientist",
    "title": "Progress and prospects for accelerating materials science with automated and autonomous workflows",
    "authors": "Helge S. Stein et al.",
    "venue": "Chemical Science (peer-reviewed journal)",
    "year": 2019,
    "doi": "10.1039/c9sc03766g",
    "url": "https://doi.org/10.1039/c9sc03766g",
    "abstract": "Provides a framework and ontology for materials experiment lifecycles, mapping automation levels and the expert decisions needed to extend autonomous loops across materials workflows.",
    "tags": [
      "materials acceleration",
      "workflow ontology",
      "automation"
    ]
  },
  {
    "domain": "AI Scientist",
    "title": "Toward autonomous laboratories: Convergence of artificial intelligence and experimental automation",
    "authors": "Yunchao Xie et al.",
    "venue": "Progress in Materials Science (peer-reviewed journal)",
    "year": 2022,
    "doi": "10.1016/j.pmatsci.2022.101043",
    "url": "https://doi.org/10.1016/j.pmatsci.2022.101043",
    "abstract": "Reviews the convergence of artificial intelligence, experimental automation, and materials science required to build autonomous laboratories and identifies practical integration challenges.",
    "tags": [
      "autonomous laboratory",
      "AI",
      "experimental automation"
    ]
  },
  {
    "domain": "AI Scientist",
    "title": "ChemOS 2.0: An orchestration architecture for chemical self-driving laboratories",
    "authors": "Malcolm Sim et al.",
    "venue": "Matter (peer-reviewed journal)",
    "year": 2024,
    "doi": "10.1016/j.matt.2024.04.022",
    "url": "https://doi.org/10.1016/j.matt.2024.04.022",
    "abstract": "Describes ChemOS 2.0, an orchestration architecture for integrating and coordinating chemical self-driving-laboratory instruments and decision loops.",
    "tags": [
      "ChemOS",
      "orchestration",
      "chemical laboratory"
    ]
  },
  {
    "domain": "AI Scientist",
    "title": "Toward autonomous design and synthesis of novel inorganic materials",
    "authors": "Nathan J. Szymanski et al.",
    "venue": "Materials Horizons (peer-reviewed journal)",
    "year": 2021,
    "doi": "10.1039/d1mh00495f",
    "url": "https://doi.org/10.1039/d1mh00495f",
    "abstract": "Reviews autonomous inorganic-materials synthesis, including robotic synthesis and characterization, deep-learning-assisted phase identification, and active-learning optimization for closed-loop design.",
    "tags": [
      "inorganic materials",
      "robotics",
      "closed-loop optimization"
    ]
  },
  {
    "domain": "AI Scientist",
    "title": "A mobile robotic chemist",
    "authors": "Benjamin Burger et al.",
    "venue": "Nature (peer-reviewed journal)",
    "year": 2020,
    "doi": "10.1038/s41586-020-2442-2",
    "url": "https://doi.org/10.1038/s41586-020-2442-2",
    "abstract": "Demonstrates a mobile robot that works in a standard laboratory, plans experiments from prior knowledge, operates instruments, and searches photocatalyst conditions for hydrogen production.",
    "tags": [
      "mobile robot",
      "photocatalysis",
      "laboratory automation"
    ]
  },
  {
    "domain": "AI Scientist",
    "title": "Autonomous mobile robots for exploratory synthetic chemistry",
    "authors": "Tianwei Dai et al.",
    "venue": "Nature (peer-reviewed journal)",
    "year": 2024,
    "doi": "10.1038/s41586-024-08173-7",
    "url": "https://doi.org/10.1038/s41586-024-08173-7",
    "abstract": "Uses mobile robots, automated synthesis, liquid chromatography-mass spectrometry, and benchtop NMR in a modular autonomous workflow for exploratory synthetic chemistry and reproducibility checking.",
    "tags": [
      "mobile robots",
      "synthetic chemistry",
      "closed-loop experimentation"
    ]
  },
  {
    "domain": "AI Scientist",
    "title": "Data-science driven autonomous process optimization",
    "authors": "Melodie Christensen et al.",
    "venue": "Communications Chemistry (peer-reviewed journal)",
    "year": 2021,
    "doi": "10.1038/s42004-021-00550-x",
    "url": "https://doi.org/10.1038/s42004-021-00550-x",
    "abstract": "Presents a closed-loop batch system for autonomous process optimization and applies it to a stereoselective Suzuki-Miyaura coupling, including a computed-feature strategy for selecting diverse phosphine ligands.",
    "tags": [
      "process optimization",
      "Suzuki-Miyaura",
      "closed-loop chemistry"
    ]
  },
  {
    "domain": "具身智能",
    "title": "Foundation models in robotics: Applications, challenges, and the future",
    "authors": "Roya Firoozi et al.",
    "venue": "The International Journal of Robotics Research (peer-reviewed journal)",
    "year": 2024,
    "doi": "10.1177/02783649241281508",
    "url": "https://doi.org/10.1177/02783649241281508",
    "abstract": "Surveys how pretrained foundation models can contribute to robot perception, decision-making, and control, while identifying data, safety, uncertainty, and real-time-execution challenges.",
    "tags": [
      "foundation models",
      "robot autonomy",
      "survey"
    ]
  },
  {
    "domain": "具身智能",
    "title": "Habitat: A Platform for Embodied AI Research",
    "authors": "Manolis Savva et al.",
    "venue": "ICCV 2019 (archival conference proceedings)",
    "year": 2019,
    "doi": "10.1109/ICCV.2019.00943",
    "url": "https://doi.org/10.1109/ICCV.2019.00943",
    "abstract": "Introduces Habitat-Sim and Habitat-API for efficient photorealistic embodied-AI training and benchmarking, and reports point-goal navigation scaling and cross-dataset generalization experiments.",
    "tags": [
      "simulation",
      "navigation",
      "benchmark"
    ]
  },
  {
    "domain": "具身智能",
    "title": "Vision-and-Language Navigation: Interpreting Visually-Grounded Navigation Instructions in Real Environments",
    "authors": "Peter Anderson et al.",
    "venue": "CVPR 2018 (archival conference proceedings)",
    "year": 2018,
    "doi": "10.1109/CVPR.2018.00387",
    "url": "https://doi.org/10.1109/CVPR.2018.00387",
    "abstract": "Introduces the Matterport3D Simulator and Room-to-Room benchmark for agents that follow visually grounded natural-language navigation instructions in real buildings.",
    "tags": [
      "vision-language navigation",
      "Matterport3D",
      "benchmark"
    ]
  },
  {
    "domain": "具身智能",
    "title": "Embodied Question Answering",
    "authors": "Abhishek Das et al.",
    "venue": "CVPR 2018 (archival conference proceedings)",
    "year": 2018,
    "doi": "10.1109/CVPR.2018.00008",
    "url": "https://doi.org/10.1109/CVPR.2018.00008",
    "abstract": "Defines EmbodiedQA, where an agent must navigate a 3D environment using egocentric vision to gather evidence before answering a question, and supplies a dataset, metrics, and hierarchical model.",
    "tags": [
      "embodied question answering",
      "active perception",
      "navigation"
    ]
  },
  {
    "domain": "具身智能",
    "title": "ALFRED: A Benchmark for Interpreting Grounded Instructions for Everyday Tasks",
    "authors": "Mohit Shridhar et al.",
    "venue": "CVPR 2020 (archival conference proceedings)",
    "year": 2020,
    "doi": "10.1109/CVPR42600.2020.01075",
    "url": "https://doi.org/10.1109/CVPR42600.2020.01075",
    "abstract": "Introduces ALFRED, a benchmark mapping natural-language instructions and egocentric vision to action sequences for household tasks with long, compositional instructions and non-reversible state changes.",
    "tags": [
      "household tasks",
      "language grounding",
      "benchmark"
    ]
  },
  {
    "domain": "具身智能",
    "title": "TEACh: Task-Driven Embodied Agents That Chat",
    "authors": "Aishwarya Padmakumar et al.",
    "venue": "AAAI 2022 (archival conference proceedings)",
    "year": 2022,
    "doi": "10.1609/AAAI.V36I2.20097",
    "url": "https://doi.org/10.1609/AAAI.V36I2.20097",
    "abstract": "Provides a dataset of more than 3,000 interactive human-human dialogues for simulated household tasks and benchmarks dialogue understanding, language grounding, and task execution by embodied agents.",
    "tags": [
      "dialogue",
      "household agents",
      "language grounding"
    ]
  },
  {
    "domain": "具身智能",
    "title": "RT-1: Robotics Transformer for Real-World Control at Scale",
    "authors": "Anthony Brohan et al.",
    "venue": "Robotics: Science and Systems 2023 (archival conference proceedings)",
    "year": 2023,
    "doi": "10.15607/RSS.2023.XIX.025",
    "url": "https://doi.org/10.15607/RSS.2023.XIX.025",
    "abstract": "Introduces Robotics Transformer, a scalable model class trained on diverse real-robot data, and studies how data size, model size, and data diversity affect generalization for real-world control.",
    "tags": [
      "robot transformer",
      "real-world control",
      "generalization"
    ]
  },
  {
    "domain": "具身智能",
    "title": "RT-2: Vision-Language-Action Models Transfer Web Knowledge to Robotic Control",
    "authors": "Anthony Brohan et al.",
    "venue": "Conference on Robot Learning 2023 (archival conference proceedings)",
    "year": 2023,
    "doi": "10.48550/arXiv.2307.15818",
    "url": "https://doi.org/10.48550/arXiv.2307.15818",
    "abstract": "Proposes vision-language-action models that co-fine-tune vision-language models on robotic trajectories and web tasks by representing actions as text tokens; evaluations report improved novel-object generalization and semantic reasoning.",
    "tags": [
      "vision-language-action",
      "robot control",
      "foundation models"
    ]
  },
  {
    "domain": "具身智能",
    "title": "PaLM-E: An Embodied Multimodal Language Model",
    "authors": "Danny Driess et al.",
    "venue": "ICML 2023 (archival conference proceedings)",
    "year": 2023,
    "doi": "10.48550/arXiv.2303.03378",
    "url": "https://doi.org/10.48550/arXiv.2303.03378",
    "abstract": "Introduces embodied language models that interleave visual, continuous state, and text inputs for robotic planning and other embodied tasks, reporting transfer from joint training with language and vision data.",
    "tags": [
      "multimodal language model",
      "robot planning",
      "grounding"
    ]
  },
  {
    "domain": "具身智能",
    "title": "Do As I Can, Not As I Say: Grounding Language in Robotic Affordances",
    "authors": "Michael Ahn et al.",
    "venue": "Conference on Robot Learning 2022 (archival conference proceedings)",
    "year": 2022,
    "doi": "10.48550/arXiv.2204.01691",
    "url": "https://doi.org/10.48550/arXiv.2204.01691",
    "abstract": "Combines large-language-model task proposals with pretrained robot skills and value functions so high-level language is constrained by what a mobile manipulator can actually do in its environment.",
    "tags": [
      "SayCan",
      "affordances",
      "language-grounded robotics"
    ]
  },
  {
    "domain": "具身智能",
    "title": "PerAct: Multi-Task 6D Robotic Manipulation with Perceiver-Actor",
    "authors": "Mohit Shridhar et al.",
    "venue": "Conference on Robot Learning 2022 (archival conference proceedings)",
    "year": 2022,
    "doi": "10.48550/arXiv.2209.05451",
    "url": "https://doi.org/10.48550/arXiv.2209.05451",
    "abstract": "Introduces Perceiver-Actor, a language-conditioned multi-task policy for 6D manipulation that learns from voxelized RGB-D observations and is evaluated in simulated and real robot settings.",
    "tags": [
      "6D manipulation",
      "multitask learning",
      "Perceiver"
    ]
  },
  {
    "domain": "具身智能",
    "title": "CLIPort: What and Where Pathways for Robotic Manipulation",
    "authors": "Mohit Shridhar et al.",
    "venue": "Conference on Robot Learning 2021 (archival conference proceedings)",
    "year": 2021,
    "doi": "10.48550/arXiv.2109.12098",
    "url": "https://doi.org/10.48550/arXiv.2109.12098",
    "abstract": "Combines CLIP semantic representations with spatial Transporter-style pathways for language-conditioned tabletop manipulation, reporting few-shot efficiency and generalization across simulated and real tasks.",
    "tags": [
      "CLIP",
      "manipulation",
      "language conditioning"
    ]
  },
  {
    "domain": "具身智能",
    "title": "R3M: A Universal Visual Representation for Robot Manipulation",
    "authors": "Suraj Nair et al.",
    "venue": "Conference on Robot Learning 2022 (archival conference proceedings)",
    "year": 2022,
    "doi": "10.48550/arXiv.2203.12601",
    "url": "https://doi.org/10.48550/arXiv.2203.12601",
    "abstract": "Pretrains a visual representation on Ego4D human video with time-contrastive learning and video-language alignment, then uses it as frozen perception for data-efficient simulated and real robot manipulation.",
    "tags": [
      "visual representation",
      "Ego4D",
      "manipulation"
    ]
  },
  {
    "domain": "具身智能",
    "title": "MimicPlay: Long-Horizon Imitation Learning by Watching Human Play",
    "authors": "Chen Wang et al.",
    "venue": "Conference on Robot Learning 2023 (archival conference proceedings)",
    "year": 2023,
    "doi": "10.48550/arXiv.2302.12422",
    "url": "https://doi.org/10.48550/arXiv.2302.12422",
    "abstract": "Uses human play videos to learn latent plans that guide low-level visuomotor control trained from a small number of teleoperated demonstrations, evaluated on 14 real-world long-horizon manipulation tasks.",
    "tags": [
      "imitation learning",
      "human play",
      "long-horizon manipulation"
    ]
  },
  {
    "domain": "具身智能",
    "title": "RVT: Robotic View Transformer for 3D Object Manipulation",
    "authors": "Ankit Goyal et al.",
    "venue": "Conference on Robot Learning 2023 (archival conference proceedings)",
    "year": 2023,
    "doi": "10.48550/arXiv.2306.14896",
    "url": "https://doi.org/10.48550/arXiv.2306.14896",
    "abstract": "Introduces a multi-view transformer for 3D manipulation that aggregates virtual camera views without an expensive voxel representation, and evaluates it across RLBench tasks and real-world demonstrations.",
    "tags": [
      "3D manipulation",
      "multi-view transformer",
      "RLBench"
    ]
  },
  {
    "domain": "具身智能",
    "title": "Diffusion policy: Visuomotor policy learning via action diffusion",
    "authors": "Cheng Chi et al.",
    "venue": "The International Journal of Robotics Research (peer-reviewed journal)",
    "year": 2024,
    "doi": "10.1177/02783649241273668",
    "url": "https://doi.org/10.1177/02783649241273668",
    "abstract": "Formulates visuomotor policy learning as conditional denoising diffusion over robot actions and reports results on manipulation tasks requiring multimodal action distributions and high-dimensional control.",
    "tags": [
      "diffusion policy",
      "visuomotor control",
      "imitation learning"
    ]
  },
  {
    "domain": "具身智能",
    "title": "Language-Driven Representation Learning for Robotics",
    "authors": "Siddharth Karamcheti et al.",
    "venue": "Robotics: Science and Systems 2023 (archival conference proceedings)",
    "year": 2023,
    "doi": "10.15607/RSS.2023.XIX.032",
    "url": "https://doi.org/10.15607/RSS.2023.XIX.032",
    "abstract": "Introduces Voltron, a language-driven representation-learning framework using video and captions, and evaluates visual representations over five robot-learning problems including control and affordance prediction.",
    "tags": [
      "representation learning",
      "language",
      "robot learning"
    ]
  },
  {
    "domain": "具身智能",
    "title": "Scaling Robot Learning with Semantically Imagined Experience",
    "authors": "Tianhe Yu et al.",
    "venue": "Robotics: Science and Systems 2023 (archival conference proceedings)",
    "year": 2023,
    "doi": "10.15607/RSS.2023.XIX.027",
    "url": "https://doi.org/10.15607/RSS.2023.XIX.027",
    "abstract": "Uses text-to-image diffusion models to augment existing robot-manipulation datasets with imagined objects, backgrounds, and distractors, reporting improved robustness and generalization in real-world experiments.",
    "tags": [
      "data augmentation",
      "diffusion models",
      "robot generalization"
    ]
  },
  {
    "domain": "具身智能",
    "title": "Octo: An Open-Source Generalist Robot Policy",
    "authors": "Dibya Ghosh et al.",
    "venue": "Robotics: Science and Systems 2024 (archival conference proceedings)",
    "year": 2024,
    "doi": "10.15607/RSS.2024.XX.090",
    "url": "https://doi.org/10.15607/RSS.2024.XX.090",
    "abstract": "Releases Octo, an open-source generalist robot policy pretrained on the Open X-Embodiment data, together with evaluations of adaptation to new robot-learning tasks.",
    "tags": [
      "generalist policy",
      "open source",
      "Open X-Embodiment"
    ]
  },
  {
    "domain": "具身智能",
    "title": "Open X-Embodiment: Robotic Learning Datasets and RT-X Models",
    "authors": "A. O'Neill et al.",
    "venue": "ICRA 2024 (archival conference proceedings)",
    "year": 2024,
    "doi": "10.1109/ICRA57147.2024.10611477",
    "url": "https://doi.org/10.1109/ICRA57147.2024.10611477",
    "abstract": "Standardizes data from 22 robot embodiments and 21 institutions into Open X-Embodiment and presents RT-X models, reporting positive transfer of robot experience across platforms, tasks, and environments.",
    "tags": [
      "robot datasets",
      "cross-embodiment transfer",
      "RT-X"
    ]
  },
  {
    "domain": "海水淡化",
    "title": "The Future of Seawater Desalination: Energy, Technology, and the Environment",
    "authors": "Menachem Elimelech; William A. Phillip",
    "venue": "Science",
    "year": 2011,
    "doi": "10.1126/science.1200488",
    "url": "https://doi.org/10.1126/science.1200488",
    "abstract": "Abstract excerpt: In recent years, numerous large-scale seawater desalination plants have been built in water-stressed countries to augment available water resources.",
    "tags": [
      "seawater",
      "energy",
      "environment"
    ]
  },
  {
    "domain": "海水淡化",
    "title": "Materials for next-generation desalination and water purification membranes",
    "authors": "Jay R. Werber; Chinedum O. Osuji; Menachem Elimelech",
    "venue": "Nature Reviews Materials",
    "year": 2016,
    "doi": "10.1038/natrevmats.2016.18",
    "url": "https://doi.org/10.1038/natrevmats.2016.18",
    "abstract": "Title-scope excerpt: Materials for next-generation desalination and water purification membranes.",
    "tags": [
      "membranes",
      "water purification",
      "materials"
    ]
  },
  {
    "domain": "海水淡化",
    "title": "Water Desalination across Nanoporous Graphene",
    "authors": "David Cohen-Tanugi; Jeffrey C. Grossman",
    "venue": "Nano Letters",
    "year": 2012,
    "doi": "10.1021/nl3012853",
    "url": "https://doi.org/10.1021/nl3012853",
    "abstract": "Abstract excerpt: Nanometer-scale pores in single-layer freestanding graphene can effectively filter NaCl salt from water.",
    "tags": [
      "graphene",
      "nanopores",
      "salt rejection"
    ]
  },
  {
    "domain": "海水淡化",
    "title": "Water desalination using nanoporous single-layer graphene",
    "authors": "Sumedh P. Surwade et al.",
    "venue": "Nature Nanotechnology",
    "year": 2015,
    "doi": "10.1038/nnano.2015.37",
    "url": "https://doi.org/10.1038/nnano.2015.37",
    "abstract": "Title-scope excerpt: Water desalination using nanoporous single-layer graphene.",
    "tags": [
      "graphene",
      "nanopores",
      "membranes"
    ]
  },
  {
    "domain": "海水淡化",
    "title": "Tunable sieving of ions using graphene oxide membranes",
    "authors": "Jijo Abraham et al.",
    "venue": "Nature Nanotechnology",
    "year": 2017,
    "doi": "10.1038/nnano.2017.21",
    "url": "https://doi.org/10.1038/nnano.2017.21",
    "abstract": "Title-scope excerpt: Tunable sieving of ions using graphene oxide membranes.",
    "tags": [
      "graphene oxide",
      "ion sieving",
      "membranes"
    ]
  },
  {
    "domain": "海水淡化",
    "title": "Emerging desalination technologies for water treatment: A critical review",
    "authors": "Arun Subramani; Joseph G. Jacangelo",
    "venue": "Water Research",
    "year": 2015,
    "doi": "10.1016/j.watres.2015.02.032",
    "url": "https://doi.org/10.1016/j.watres.2015.02.032",
    "abstract": "Title-scope excerpt: Emerging desalination technologies for water treatment: A critical review.",
    "tags": [
      "water treatment",
      "technology review",
      "desalination"
    ]
  },
  {
    "domain": "海水淡化",
    "title": "Renewable energy-driven innovative energy-efficient desalination technologies",
    "authors": "Noreddine Ghaffour et al.",
    "venue": "Applied Energy",
    "year": 2014,
    "doi": "10.1016/j.apenergy.2014.03.033",
    "url": "https://doi.org/10.1016/j.apenergy.2014.03.033",
    "abstract": "Title-scope excerpt: Renewable energy-driven innovative energy-efficient desalination technologies.",
    "tags": [
      "renewable energy",
      "energy efficiency",
      "desalination"
    ]
  },
  {
    "domain": "海水淡化",
    "title": "The state of desalination and brine production: A global outlook",
    "authors": "Edward Jones et al.",
    "venue": "Science of The Total Environment",
    "year": 2019,
    "doi": "10.1016/j.scitotenv.2018.12.076",
    "url": "https://doi.org/10.1016/j.scitotenv.2018.12.076",
    "abstract": "Abstract excerpt: Unconventional water resources, such as desalinated water, are expected to play a key role in narrowing the water demand-supply gap.",
    "tags": [
      "brine",
      "global outlook",
      "water scarcity"
    ]
  },
  {
    "domain": "海水淡化",
    "title": "Energy consumption and water production cost of conventional and renewable-energy-powered desalination processes",
    "authors": "Ali Al-Karaghouli; Lawrence L. Kazmerski",
    "venue": "Renewable and Sustainable Energy Reviews",
    "year": 2013,
    "doi": "10.1016/j.rser.2012.12.064",
    "url": "https://doi.org/10.1016/j.rser.2012.12.064",
    "abstract": "Title-scope excerpt: Energy consumption and water production cost of conventional and renewable-energy-powered desalination processes.",
    "tags": [
      "energy",
      "cost",
      "renewable energy"
    ]
  },
  {
    "domain": "海水淡化",
    "title": "Review on the science and technology of water desalination by capacitive deionization",
    "authors": "S. Porada et al.",
    "venue": "Progress in Materials Science",
    "year": 2013,
    "doi": "10.1016/j.pmatsci.2013.03.005",
    "url": "https://doi.org/10.1016/j.pmatsci.2013.03.005",
    "abstract": "Abstract excerpt: Porous carbon electrodes have significant potential for energy-efficient water desalination using capacitive deionization.",
    "tags": [
      "capacitive deionization",
      "porous carbon",
      "electrodes"
    ]
  },
  {
    "domain": "海水淡化",
    "title": "Water desalination via capacitive deionization: what is it and what can we expect from it?",
    "authors": "M. E. Suss et al.",
    "venue": "Energy & Environmental Science",
    "year": 2015,
    "doi": "10.1039/c5ee00519a",
    "url": "https://doi.org/10.1039/c5ee00519a",
    "abstract": "Abstract excerpt: Capacitive deionization is a promising technology for water desalination that has seen tremendous advances over the past five years.",
    "tags": [
      "capacitive deionization",
      "electrochemistry",
      "energy"
    ]
  },
  {
    "domain": "海水淡化",
    "title": "Solar steam generation by heat localization",
    "authors": "Hadi Ghasemi et al.",
    "venue": "Nature Communications",
    "year": 2014,
    "doi": "10.1038/ncomms5449",
    "url": "https://doi.org/10.1038/ncomms5449",
    "abstract": "Title-scope excerpt: Solar steam generation by heat localization.",
    "tags": [
      "solar steam",
      "heat localization",
      "photothermal"
    ]
  },
  {
    "domain": "海水淡化",
    "title": "A salt-rejecting floating solar still for low-cost desalination",
    "authors": "George Ni et al.",
    "venue": "Energy & Environmental Science",
    "year": 2018,
    "doi": "10.1039/c8ee00220g",
    "url": "https://doi.org/10.1039/c8ee00220g",
    "abstract": "Abstract excerpt: A floating, low-cost solar desalination system was constructed, capable of simultaneous salt rejection and heat localization for continuous operation.",
    "tags": [
      "solar still",
      "salt rejection",
      "low cost"
    ]
  },
  {
    "domain": "海水淡化",
    "title": "3D self-assembly of aluminium nanoparticles for plasmon-enhanced solar desalination",
    "authors": "Lin Zhou et al.",
    "venue": "Nature Photonics",
    "year": 2016,
    "doi": "10.1038/nphoton.2016.75",
    "url": "https://doi.org/10.1038/nphoton.2016.75",
    "abstract": "Title-scope excerpt: 3D self-assembly of aluminium nanoparticles for plasmon-enhanced solar desalination.",
    "tags": [
      "plasmonics",
      "nanoparticles",
      "solar desalination"
    ]
  },
  {
    "domain": "海水淡化",
    "title": "Graphene oxide-based efficient and scalable solar desalination under one sun with a confined 2D water path",
    "authors": "Xiuqiang Li et al.",
    "venue": "Proceedings of the National Academy of Sciences",
    "year": 2016,
    "doi": "10.1073/pnas.1613031113",
    "url": "https://doi.org/10.1073/pnas.1613031113",
    "abstract": "Abstract excerpt: Because it is able to produce desalinated water directly using solar energy with minimum carbon footprint, solar steam generation and desalination is considered a promising technology.",
    "tags": [
      "graphene oxide",
      "solar desalination",
      "2D water path"
    ]
  },
  {
    "domain": "海水淡化",
    "title": "A High-Performance Self-Regenerating Solar Evaporator for Continuous Water Desalination",
    "authors": "Yudi Kuang et al.",
    "venue": "Advanced Materials",
    "year": 2019,
    "doi": "10.1002/adma.201900498",
    "url": "https://doi.org/10.1002/adma.201900498",
    "abstract": "Abstract excerpt: Solar desalination by interfacial evaporation has high solar-to-vapor efficiency, low environmental impact, and off-grid capability.",
    "tags": [
      "solar evaporator",
      "self-regeneration",
      "interfacial evaporation"
    ]
  },
  {
    "domain": "海水淡化",
    "title": "A hydrogel-based antifouling solar evaporator for highly efficient water desalination",
    "authors": "Xingyi Zhou et al.",
    "venue": "Energy & Environmental Science",
    "year": 2018,
    "doi": "10.1039/c8ee00567b",
    "url": "https://doi.org/10.1039/c8ee00567b",
    "abstract": "Abstract excerpt: Efficient solar water evaporation was achieved by antifouling hybrid hydrogels with capillarity facilitated water transport and heat concentration in a polymeric network.",
    "tags": [
      "hydrogel",
      "antifouling",
      "solar evaporation"
    ]
  },
  {
    "domain": "海水淡化",
    "title": "Water desalination with a single-layer MoS2 nanopore",
    "authors": "Mohammad Heiranian; Amir Barati Farimani; Narayana R. Aluru",
    "venue": "Nature Communications",
    "year": 2015,
    "doi": "10.1038/ncomms9616",
    "url": "https://doi.org/10.1038/ncomms9616",
    "abstract": "Abstract excerpt: Nanotechnology has led to a variety of nanoporous membranes for water purification.",
    "tags": [
      "MoS2",
      "nanopores",
      "molecular dynamics"
    ]
  },
  {
    "domain": "海水淡化",
    "title": "Direct seawater desalination by ion concentration polarization",
    "authors": "Sung Jae Kim et al.",
    "venue": "Nature Nanotechnology",
    "year": 2010,
    "doi": "10.1038/nnano.2010.34",
    "url": "https://doi.org/10.1038/nnano.2010.34",
    "abstract": "Title-scope excerpt: Direct seawater desalination by ion concentration polarization.",
    "tags": [
      "ion concentration polarization",
      "seawater",
      "microfluidics"
    ]
  },
  {
    "domain": "海水淡化",
    "title": "Unimpeded Permeation of Water Through Helium-Leak-Tight Graphene-Based Membranes",
    "authors": "R. R. Nair et al.",
    "venue": "Science",
    "year": 2012,
    "doi": "10.1126/science.1211694",
    "url": "https://doi.org/10.1126/science.1211694",
    "abstract": "Abstract excerpt: Thin semi-permeable membranes are commonly used as chemical barriers or for filtration purposes.",
    "tags": [
      "graphene",
      "water permeation",
      "membranes"
    ]
  },
  {
    "domain": "反渗透",
    "title": "Reverse osmosis desalination: Water sources, technology, and today's challenges",
    "authors": "Lauren F. Greenlee et al.",
    "venue": "Water Research",
    "year": 2009,
    "doi": "10.1016/j.watres.2009.03.010",
    "url": "https://doi.org/10.1016/j.watres.2009.03.010",
    "abstract": "Title-scope excerpt: Reverse osmosis desalination: Water sources, technology, and today's challenges.",
    "tags": [
      "desalination",
      "water sources",
      "technology review"
    ]
  },
  {
    "domain": "反渗透",
    "title": "A review of reverse osmosis membrane materials for desalination: Development to date and future potential",
    "authors": "Kah Peng Lee; Tom C. Arnot; Davide Mattia",
    "venue": "Journal of Membrane Science",
    "year": 2011,
    "doi": "10.1016/j.memsci.2010.12.036",
    "url": "https://doi.org/10.1016/j.memsci.2010.12.036",
    "abstract": "Abstract excerpt: Reverse osmosis (RO) is currently the most important desalination technology and it is experiencing significant growth.",
    "tags": [
      "membrane materials",
      "desalination",
      "review"
    ]
  },
  {
    "domain": "反渗透",
    "title": "State-of-the-art of reverse osmosis desalination",
    "authors": "C. Fritzmann et al.",
    "venue": "Desalination",
    "year": 2007,
    "doi": "10.1016/j.desal.2006.12.009",
    "url": "https://doi.org/10.1016/j.desal.2006.12.009",
    "abstract": "Title-scope excerpt: State-of-the-art of reverse osmosis desalination.",
    "tags": [
      "desalination",
      "state of the art",
      "processes"
    ]
  },
  {
    "domain": "反渗透",
    "title": "Composite reverse osmosis and nanofiltration membranes",
    "authors": "Robert J. Petersen",
    "venue": "Journal of Membrane Science",
    "year": 1993,
    "doi": "10.1016/0376-7388(93)80014-O",
    "url": "https://doi.org/10.1016/0376-7388(93)80014-O",
    "abstract": "Title-scope excerpt: Composite reverse osmosis and nanofiltration membranes.",
    "tags": [
      "composite membranes",
      "nanofiltration",
      "membrane history"
    ]
  },
  {
    "domain": "反渗透",
    "title": "Nanoscale Heterogeneity of Polyamide Membranes Formed by Interfacial Polymerization",
    "authors": "Viatcheslav Freger",
    "venue": "Langmuir",
    "year": 2003,
    "doi": "10.1021/la020920q",
    "url": "https://doi.org/10.1021/la020920q",
    "abstract": "Title-scope excerpt: Nanoscale heterogeneity of polyamide membranes formed by interfacial polymerization.",
    "tags": [
      "polyamide",
      "interfacial polymerization",
      "nanoscale structure"
    ]
  },
  {
    "domain": "反渗透",
    "title": "Interfacial polymerization of thin film nanocomposites: A new concept for reverse osmosis membranes",
    "authors": "Byeong-Heon Jeong et al.",
    "venue": "Journal of Membrane Science",
    "year": 2007,
    "doi": "10.1016/j.memsci.2007.02.025",
    "url": "https://doi.org/10.1016/j.memsci.2007.02.025",
    "abstract": "Title-scope excerpt: Interfacial polymerization of thin film nanocomposites: A new concept for reverse osmosis membranes.",
    "tags": [
      "thin-film nanocomposite",
      "interfacial polymerization",
      "membranes"
    ]
  },
  {
    "domain": "反渗透",
    "title": "Impacts of reaction and curing conditions on polyamide composite reverse osmosis membrane properties",
    "authors": "Asim K. Ghosh et al.",
    "venue": "Journal of Membrane Science",
    "year": 2008,
    "doi": "10.1016/j.memsci.2007.11.038",
    "url": "https://doi.org/10.1016/j.memsci.2007.11.038",
    "abstract": "Title-scope excerpt: Impacts of reaction and curing conditions on polyamide composite reverse osmosis membrane properties.",
    "tags": [
      "polyamide",
      "curing",
      "membrane fabrication"
    ]
  },
  {
    "domain": "反渗透",
    "title": "Influence of membrane surface properties on initial rate of colloidal fouling of reverse osmosis and nanofiltration membranes",
    "authors": "Eric M. Vrijenhoek; Seungkwan Hong; Menachem Elimelech",
    "venue": "Journal of Membrane Science",
    "year": 2001,
    "doi": "10.1016/S0376-7388(01)00376-3",
    "url": "https://doi.org/10.1016/S0376-7388(01)00376-3",
    "abstract": "Title-scope excerpt: Influence of membrane surface properties on initial rate of colloidal fouling of reverse osmosis and nanofiltration membranes.",
    "tags": [
      "colloidal fouling",
      "surface properties",
      "nanofiltration"
    ]
  },
  {
    "domain": "反渗透",
    "title": "Reverse osmosis desalination: A state-of-the-art review",
    "authors": "Muhammad Qasim et al.",
    "venue": "Desalination",
    "year": 2019,
    "doi": "10.1016/j.desal.2019.02.008",
    "url": "https://doi.org/10.1016/j.desal.2019.02.008",
    "abstract": "Title-scope excerpt: Reverse osmosis desalination: A state-of-the-art review.",
    "tags": [
      "desalination",
      "state of the art",
      "review"
    ]
  },
  {
    "domain": "反渗透",
    "title": "Seawater desalination by reverse osmosis: Current development and future challenges in membrane fabrication - A review",
    "authors": "Yu Jie Lim et al.",
    "venue": "Journal of Membrane Science",
    "year": 2021,
    "doi": "10.1016/j.memsci.2021.119292",
    "url": "https://doi.org/10.1016/j.memsci.2021.119292",
    "abstract": "Title-scope excerpt: Seawater desalination by reverse osmosis: Current development and future challenges in membrane fabrication.",
    "tags": [
      "seawater",
      "membrane fabrication",
      "review"
    ]
  },
  {
    "domain": "反渗透",
    "title": "Recent developments in reverse osmosis desalination membranes",
    "authors": "Dan Li; Huanting Wang",
    "venue": "Journal of Materials Chemistry",
    "year": 2010,
    "doi": "10.1039/B924553G",
    "url": "https://doi.org/10.1039/B924553G",
    "abstract": "Title-scope excerpt: Recent developments in reverse osmosis desalination membranes.",
    "tags": [
      "membrane materials",
      "desalination",
      "review"
    ]
  },
  {
    "domain": "反渗透",
    "title": "A review of reverse osmosis membrane fouling and control strategies",
    "authors": "Shanxue Jiang; Yuening Li; Bradley P. Ladewig",
    "venue": "Science of The Total Environment",
    "year": 2017,
    "doi": "10.1016/j.scitotenv.2017.03.235",
    "url": "https://doi.org/10.1016/j.scitotenv.2017.03.235",
    "abstract": "Title-scope excerpt: A review of reverse osmosis membrane fouling and control strategies.",
    "tags": [
      "fouling",
      "control strategies",
      "review"
    ]
  },
  {
    "domain": "反渗透",
    "title": "Biofouling of reverse osmosis membranes: Role of biofilm-enhanced osmotic pressure",
    "authors": "Moshe Herzberg; Menachem Elimelech",
    "venue": "Journal of Membrane Science",
    "year": 2007,
    "doi": "10.1016/j.memsci.2007.02.024",
    "url": "https://doi.org/10.1016/j.memsci.2007.02.024",
    "abstract": "Title-scope excerpt: Biofouling of reverse osmosis membranes: Role of biofilm-enhanced osmotic pressure.",
    "tags": [
      "biofouling",
      "biofilm",
      "osmotic pressure"
    ]
  },
  {
    "domain": "反渗透",
    "title": "Biofouling in reverse osmosis membranes for seawater desalination: Phenomena and prevention",
    "authors": "Asif Matin et al.",
    "venue": "Desalination",
    "year": 2011,
    "doi": "10.1016/j.desal.2011.06.063",
    "url": "https://doi.org/10.1016/j.desal.2011.06.063",
    "abstract": "Title-scope excerpt: Biofouling in reverse osmosis membranes for seawater desalination: Phenomena and prevention.",
    "tags": [
      "biofouling",
      "seawater",
      "prevention"
    ]
  },
  {
    "domain": "反渗透",
    "title": "Development of antifouling reverse osmosis membranes for water treatment: A review",
    "authors": "Guo-dong Kang; Yi-ming Cao",
    "venue": "Water Research",
    "year": 2012,
    "doi": "10.1016/j.watres.2011.11.041",
    "url": "https://doi.org/10.1016/j.watres.2011.11.041",
    "abstract": "Title-scope excerpt: Development of antifouling reverse osmosis membranes for water treatment: A review.",
    "tags": [
      "antifouling",
      "water treatment",
      "review"
    ]
  },
  {
    "domain": "反渗透",
    "title": "Graphene oxide-embedded thin-film composite reverse osmosis membrane with high flux, anti-biofouling, and chlorine resistance",
    "authors": "Hee-Ro Chae et al.",
    "venue": "Journal of Membrane Science",
    "year": 2015,
    "doi": "10.1016/j.memsci.2015.02.045",
    "url": "https://doi.org/10.1016/j.memsci.2015.02.045",
    "abstract": "Title-scope excerpt: Graphene oxide-embedded thin-film composite reverse osmosis membrane with high flux, anti-biofouling, and chlorine resistance.",
    "tags": [
      "graphene oxide",
      "thin-film composite",
      "chlorine resistance"
    ]
  },
  {
    "domain": "反渗透",
    "title": "Thin film nanocomposite reverse osmosis membrane modified by reduced graphene oxide/TiO2 with improved desalination performance",
    "authors": "Mahdie Safarpour; Alireza Khataee; Vahid Vatanpour",
    "venue": "Journal of Membrane Science",
    "year": 2015,
    "doi": "10.1016/j.memsci.2015.04.010",
    "url": "https://doi.org/10.1016/j.memsci.2015.04.010",
    "abstract": "Title-scope excerpt: Thin film nanocomposite reverse osmosis membrane modified by reduced graphene oxide/TiO2 with improved desalination performance.",
    "tags": [
      "nanocomposite",
      "reduced graphene oxide",
      "TiO2"
    ]
  },
  {
    "domain": "反渗透",
    "title": "Hybrid Organic/Inorganic Reverse Osmosis Membrane for Bactericidal Anti-Fouling. 1. Preparation and Characterization of TiO2 Nanoparticle Self-Assembled Aromatic Polyamide Thin-Film-Composite Membrane",
    "authors": "Seung-Yeop Kwak et al.",
    "venue": "Environmental Science & Technology",
    "year": 2001,
    "doi": "10.1021/es0017099",
    "url": "https://doi.org/10.1021/es0017099",
    "abstract": "Title-scope excerpt: Hybrid organic/inorganic reverse osmosis membrane for bactericidal anti-fouling.",
    "tags": [
      "TiO2",
      "antifouling",
      "thin-film composite"
    ]
  },
  {
    "domain": "反渗透",
    "title": "Probing the nano- and micro-scales of reverse osmosis membranes: A comprehensive characterization of physiochemical properties of uncoated and coated membranes by XPS, TEM, ATR-FTIR, and streaming potential measurements",
    "authors": "C. Tang; Y. Kwon; J. Leckie",
    "venue": "Journal of Membrane Science",
    "year": 2007,
    "doi": "10.1016/j.memsci.2006.10.038",
    "url": "https://doi.org/10.1016/j.memsci.2006.10.038",
    "abstract": "Title-scope excerpt: Comprehensive nano- and micro-scale characterization of uncoated and coated reverse osmosis membranes.",
    "tags": [
      "characterization",
      "XPS",
      "TEM"
    ]
  },
  {
    "domain": "反渗透",
    "title": "Role of membrane surface morphology in colloidal fouling of cellulose acetate and composite aromatic polyamide reverse osmosis membranes",
    "authors": "Menachem Elimelech et al.",
    "venue": "Journal of Membrane Science",
    "year": 1997,
    "doi": "10.1016/S0376-7388(96)00351-1",
    "url": "https://doi.org/10.1016/S0376-7388(96)00351-1",
    "abstract": "Title-scope excerpt: Role of membrane surface morphology in colloidal fouling of cellulose acetate and composite aromatic polyamide reverse osmosis membranes.",
    "tags": [
      "surface morphology",
      "colloidal fouling",
      "polyamide"
    ]
  },
  {
    "domain": "燃气轮机",
    "title": "Ammonia–methane combustion in tangential swirl burners for gas turbine power generation",
    "authors": "Agustín Valera-Medina et al.",
    "venue": "Applied Energy",
    "year": 2017,
    "doi": "10.1016/j.apenergy.2016.02.073",
    "url": "https://doi.org/10.1016/j.apenergy.2016.02.073",
    "abstract": "Ammonia has been proposed as a potential energy storage medium in the transition towards a low-carbon economy.",
    "tags": [
      "ammonia combustion",
      "swirl burner",
      "emissions"
    ]
  },
  {
    "domain": "燃气轮机",
    "title": "Silicate Deposit Degradation of Engineered Coatings in Gas Turbines: Progress Toward Models and Materials Solutions",
    "authors": "David L. Poerschke, Richard W. Jackson, and Carlos G. Levi",
    "venue": "Annual Review of Materials Research",
    "year": 2017,
    "doi": "10.1146/annurev-matsci-010917-105000",
    "url": "https://doi.org/10.1146/annurev-matsci-010917-105000",
    "abstract": "Modern gas turbines rely on ceramic coatings to protect structural components along the hot gas path.",
    "tags": [
      "thermal barrier coating",
      "CMAS",
      "hot section"
    ]
  },
  {
    "domain": "燃气轮机",
    "title": "Sensor Fault Detection, Isolation, and Identification Using Multiple-Model-Based Hybrid Kalman Filter for Gas Turbine Engines",
    "authors": "Bahareh Pourbabaee et al.",
    "venue": "IEEE Transactions on Control Systems Technology",
    "year": 2016,
    "doi": "10.1109/tcst.2015.2480003",
    "url": "https://doi.org/10.1109/tcst.2015.2480003",
    "abstract": "In this paper, a novel sensor fault detection, isolation, and identification (FDII) strategy is proposed using the multiple-model (MM) approach.",
    "tags": [
      "sensor fault detection",
      "Kalman filter",
      "engine health"
    ]
  },
  {
    "domain": "燃气轮机",
    "title": "Exploring the competitiveness of hydrogen-fueled gas turbines in future energy systems",
    "authors": "Simon Öberg et al.",
    "venue": "International Journal of Hydrogen Energy",
    "year": 2022,
    "doi": "10.1016/j.ijhydene.2021.10.035",
    "url": "https://doi.org/10.1016/j.ijhydene.2021.10.035",
    "abstract": "Hydrogen is currently receiving attention as a possible cross-sectoral energy carrier with the potential to enable emission reductions in several sectors, including hard-to-abate sectors.",
    "tags": [
      "hydrogen",
      "power systems",
      "techno-economics"
    ]
  },
  {
    "domain": "燃气轮机",
    "title": "Flameless combustion and its potential towards gas turbines",
    "authors": "A. A. V. Augusto Viviani Perpignan, Arvind Gangoli Rao, and Dirk Roekaerts",
    "venue": "Progress in Energy and Combustion Science",
    "year": 2018,
    "doi": "10.1016/j.pecs.2018.06.002",
    "url": "https://doi.org/10.1016/j.pecs.2018.06.002",
    "abstract": "Since its discovery, the Flameless Combustion (FC) regime has been seen as a promising alternative combustion technique to reduce pollutant emissions of gas turbine engines.",
    "tags": [
      "flameless combustion",
      "NOx",
      "aero-engine"
    ]
  },
  {
    "domain": "燃气轮机",
    "title": "Modeling Combustion of Ammonia/Hydrogen Fuel Blends under Gas Turbine Conditions",
    "authors": "Hua Xiao, Agustín Valera-Medina, and Philip J. Bowen",
    "venue": "Energy & Fuels",
    "year": 2017,
    "doi": "10.1021/acs.energyfuels.7b00709",
    "url": "https://doi.org/10.1021/acs.energyfuels.7b00709",
    "abstract": "To utilize ammonia as an alternative fuel for future power generation, it is essential to develop combustion chemical kinetic mechanisms which can describe in some detail the reaction characteristics and combustion properties.",
    "tags": [
      "ammonia-hydrogen",
      "kinetics",
      "combustion modelling"
    ]
  },
  {
    "domain": "燃气轮机",
    "title": "Environmental degradation of high-temperature protective coatings for ceramic-matrix composites in gas-turbine engines",
    "authors": "Nitin P. Padture",
    "venue": "npj Materials Degradation",
    "year": 2019,
    "doi": "10.1038/s41529-019-0075-4",
    "url": "https://doi.org/10.1038/s41529-019-0075-4",
    "abstract": "The need for higher efficiencies and performance in gas-turbine engines that propel aircraft in the air, and generate electricity on land, is pushing the operating temperatures of the engines to unprecedented levels.",
    "tags": [
      "ceramic-matrix composites",
      "environmental barrier coating",
      "materials"
    ]
  },
  {
    "domain": "燃气轮机",
    "title": "Advanced Cooling in Gas Turbines 2016 Max Jakob Memorial Award Paper",
    "authors": "Je-Chin Han",
    "venue": "Journal of Heat Transfer",
    "year": 2018,
    "doi": "10.1115/1.4039644",
    "url": "https://doi.org/10.1115/1.4039644",
    "abstract": "Gas turbines have been extensively used for aircraft engine propulsion, land-based power generation, and industrial applications.",
    "tags": [
      "blade cooling",
      "heat transfer",
      "turbine inlet temperature"
    ]
  },
  {
    "domain": "燃气轮机",
    "title": "Performance-Based Gas Turbine Health Monitoring, Diagnostics, and Prognostics: A Survey",
    "authors": "Houman Hanachi et al.",
    "venue": "IEEE Transactions on Reliability",
    "year": 2018,
    "doi": "10.1109/tr.2018.2822702",
    "url": "https://doi.org/10.1109/tr.2018.2822702",
    "abstract": "Health monitoring is an essential part of condition-based maintenance and prognostics and health management for gas turbines.",
    "tags": [
      "health monitoring",
      "gas path",
      "prognostics"
    ]
  },
  {
    "domain": "燃气轮机",
    "title": "Comprehensive organic emission profiles for gasoline, diesel, and gas-turbine engines including intermediate and semi-volatile organic compound emissions",
    "authors": "Quanyang Lu et al.",
    "venue": "Atmospheric Chemistry and Physics",
    "year": 2018,
    "doi": "10.5194/acp-18-17637-2018",
    "url": "https://doi.org/10.5194/acp-18-17637-2018",
    "abstract": "Emissions from mobile sources are important contributors to both primary and secondary organic aerosols (POA and SOA) in urban environments.",
    "tags": [
      "organic emissions",
      "particulate emissions",
      "aviation"
    ]
  },
  {
    "domain": "燃气轮机",
    "title": "A review of cooling technologies for high temperature rotating components in gas turbine",
    "authors": "Umesh Unnikrishnan and Vigor Yang",
    "venue": "Propulsion and Power Research",
    "year": 2022,
    "doi": "10.1016/j.jppr.2022.07.001",
    "url": "https://doi.org/10.1016/j.jppr.2022.07.001",
    "abstract": "Modern gas turbines work under demanding high temperatures, high pressures, and high rotational speeds.",
    "tags": [
      "blade cooling",
      "rotating components",
      "thermal management"
    ]
  },
  {
    "domain": "燃气轮机",
    "title": "Combustion and Emission Characteristics of Ammonia under Conditions Relevant to Modern Gas Turbines",
    "authors": "Rodolfo C. Rocha et al.",
    "venue": "Combustion Science and Technology",
    "year": 2020,
    "doi": "10.1080/00102202.2020.1748018",
    "url": "https://doi.org/10.1080/00102202.2020.1748018",
    "abstract": "Ammonia (NH3) is considered a promising alternative fuel, capable of producing energy with zero CO2 emissions.",
    "tags": [
      "ammonia combustion",
      "NOx",
      "stationary gas turbines"
    ]
  },
  {
    "domain": "燃气轮机",
    "title": "Flameless combustion with liquid fuel: A review focusing on fundamentals and gas turbine application",
    "authors": "Fei Xing et al.",
    "venue": "Applied Energy",
    "year": 2017,
    "doi": "10.1016/j.apenergy.2017.02.010",
    "url": "https://doi.org/10.1016/j.apenergy.2017.02.010",
    "abstract": "Flameless combustion has been developed to reduce emissions whilst retaining thermal efficiencies in combustion systems.",
    "tags": [
      "flameless combustion",
      "liquid fuel",
      "clean combustion"
    ]
  },
  {
    "domain": "燃气轮机",
    "title": "Effects of Fuel Aromatic Content on Nonvolatile Particulate Emissions of an In-Production Aircraft Gas Turbine",
    "authors": "Benjamin T. Brem et al.",
    "venue": "Environmental Science & Technology",
    "year": 2015,
    "doi": "10.1021/acs.est.5b04167",
    "url": "https://doi.org/10.1021/acs.est.5b04167",
    "abstract": "Aircraft engines emit particulate matter (PM) that affects the air quality in the vicinity of airports and contributes to climate change.",
    "tags": [
      "aviation emissions",
      "fuel aromatics",
      "particulates"
    ]
  },
  {
    "domain": "燃气轮机",
    "title": "Toward Decarbonized Power Generation With Gas Turbines by Using Sequential Combustion for Burning Hydrogen",
    "authors": "Mirko R. Bothien et al.",
    "venue": "Journal of Engineering for Gas Turbines and Power",
    "year": 2019,
    "doi": "10.1115/1.4045256",
    "url": "https://doi.org/10.1115/1.4045256",
    "abstract": "Excess energy generation from renewables can be conveniently stored as hydrogen for later use as a gas turbine fuel.",
    "tags": [
      "hydrogen",
      "sequential combustion",
      "decarbonization"
    ]
  },
  {
    "domain": "燃气轮机",
    "title": "Heat transfer in the trailing region of gas turbines – A state-of-the-art review",
    "authors": "Wei Du et al.",
    "venue": "Applied Thermal Engineering",
    "year": 2021,
    "doi": "10.1016/j.applthermaleng.2021.117614",
    "url": "https://doi.org/10.1016/j.applthermaleng.2021.117614",
    "abstract": "Highly efficient gas turbines are beneficial for improving the energy structure, reducing carbon dioxide emissions and protecting the Earth's environment.",
    "tags": [
      "trailing edge cooling",
      "heat transfer",
      "turbine blade"
    ]
  },
  {
    "domain": "燃气轮机",
    "title": "Materials challenges in hydrogen-fuelled gas turbines",
    "authors": "Elena Stefan et al.",
    "venue": "International Materials Reviews",
    "year": 2021,
    "doi": "10.1080/09506608.2021.1981706",
    "url": "https://doi.org/10.1080/09506608.2021.1981706",
    "abstract": "With the increased pressure to decarbonise the power generation sector several gas turbine manufacturers are working towards increasing the hydrogen-firing capabilities of their engines towards 100%.",
    "tags": [
      "hydrogen combustion",
      "superalloys",
      "oxidation"
    ]
  },
  {
    "domain": "燃气轮机",
    "title": "Study on Reduced Chemical Mechanisms of Ammonia/Methane Combustion under Gas Turbine Conditions",
    "authors": "Hua Xiao et al.",
    "venue": "Energy & Fuels",
    "year": 2016,
    "doi": "10.1021/acs.energyfuels.6b01556",
    "url": "https://doi.org/10.1021/acs.energyfuels.6b01556",
    "abstract": "As an alternative fuel and hydrogen carrier, ammonia is believed to have good potential for future power generation.",
    "tags": [
      "ammonia-methane",
      "chemical kinetics",
      "combustor simulation"
    ]
  },
  {
    "domain": "燃气轮机",
    "title": "A review of recent studies on rotating internal cooling for gas turbine blades",
    "authors": "Kirttayoth Yeranee and Yu Rao",
    "venue": "Chinese Journal of Aeronautics",
    "year": 2021,
    "doi": "10.1016/j.cja.2020.12.035",
    "url": "https://doi.org/10.1016/j.cja.2020.12.035",
    "abstract": "Gas turbines have been used extensively for aircraft and marine propulsions as well as land-based power generation because of their high thermal efficiency and large power to weight ratios.",
    "tags": [
      "internal cooling",
      "rotation",
      "turbine blade"
    ]
  },
  {
    "domain": "燃气轮机",
    "title": "Review of Novel Combustion Techniques for Clean Power Production in Gas Turbines",
    "authors": "Medhat A. Nemitallah et al.",
    "venue": "Energy & Fuels",
    "year": 2018,
    "doi": "10.1021/acs.energyfuels.7b03607",
    "url": "https://doi.org/10.1021/acs.energyfuels.7b03607",
    "abstract": "The tremendous increase in energy demand due to increased population and rapid economics results in an increased level of atmospheric pollutants and global warming.",
    "tags": [
      "low-emissions combustion",
      "gas turbines",
      "clean power"
    ]
  }
] satisfies readonly PaperRecord[];

export const PAPERS_PER_PAGE = 5;

export function getPapersForDomain(domain: PaperDomain): readonly PaperRecord[] {
  if (domain === "全部领域") {
    return VERIFIED_PAPERS;
  }

  return VERIFIED_PAPERS.filter((paper) => paper.domain === domain);
}

export function getPaperCount(domain: PaperDomain): number {
  return getPapersForDomain(domain).length;
}
