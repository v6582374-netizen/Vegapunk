#!/usr/bin/env python3
"""InternAgent QA mode — direct one-shot question answering."""

import argparse
import asyncio
import os
import sys
import traceback
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv(override=True)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from internagent.mas.agents.dr_agent import DRAgent


def _load_qa_config(path: str) -> tuple[str, dict]:
    """Load the shared OpenAI Runtime policy and project it into DR QA."""
    with Path(path).open("r", encoding="utf-8") as file:
        config = yaml.safe_load(file)
    if not isinstance(config, dict):
        raise ValueError("InternAgent config must contain a mapping")
    models = config.get("models", {})
    if not isinstance(models, dict):
        raise ValueError("InternAgent models config must contain a mapping")
    openai_config = models.get("openai", {})
    if not isinstance(openai_config, dict):
        raise ValueError("InternAgent models.openai must contain a mapping")
    model_name = openai_config.get("model_name", "gpt-5.6-sol")
    if model_name != "gpt-5.6-sol":
        raise ValueError("Deep Research QA requires model='gpt-5.6-sol'")
    agents = config.get("agents", {})
    dr_config = dict(agents.get("dr", {})) if isinstance(agents, dict) else {}
    dr_config.update({"mode": "qa", "_global_config": config})
    return model_name, dr_config


# 问答模式是一条短路径：把问题交给调研工作流，拿到一次性回答后打印或写文件。
# 它不会创建多轮实验目录，也不会进入发现流程里的想法筛选和实验执行。
def main():
    parser = argparse.ArgumentParser(description='InternAgent QA — one-shot question answering')
    parser.add_argument('--question', '-q', required=True, help='Research question to answer')
    parser.add_argument('--file', '-f', default=None, help='Optional file attachment')
    parser.add_argument('--output', '-o', default=None, help='Write answer to this file path')
    parser.add_argument(
        '--config',
        default='config/default_config.yaml',
        help='InternAgent YAML config (default: config/default_config.yaml)',
    )
    args = parser.parse_args()

    # 这里使用调研适配器，是因为问答同样需要“查背景、组织证据、合成答案”的能力；
    # 只是输出直接回到终端，而不是进入后续实验阶段。
    model_name, dr_config = _load_qa_config(args.config)
    agent = DRAgent(model=model_name, config=dr_config)
    answer = str(asyncio.run(
        agent.execute({'task': args.question, 'file_path': args.file}, {})
    ))
    print(answer)
    if args.output:
        os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(answer)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nQA pipeline interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nFatal error: {str(e)}")
        traceback.print_exc()
