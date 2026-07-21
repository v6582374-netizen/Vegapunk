#!/usr/bin/env python3
"""Vegapunk QA mode — direct one-shot question answering."""

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

from vegapunk.mas.agents.dr_agent import DRAgent
from vegapunk.mas.models.unified_runtime import UnifiedModelRuntime


def _load_qa_config(path: str) -> tuple[UnifiedModelRuntime, dict]:
    """Load the Catalog Runtime and project it into Deep Research QA."""
    with Path(path).open("r", encoding="utf-8") as file:
        config = yaml.safe_load(file)
    if not isinstance(config, dict):
        raise ValueError("Vegapunk config must contain a mapping")
    catalog_path = config.get("model_catalog_path")
    repository_root = Path(__file__).resolve().parent
    if catalog_path is None:
        catalog_path = repository_root / "config" / "model_catalog.yaml"
    else:
        catalog_path = Path(str(catalog_path)).expanduser()
        if not catalog_path.is_absolute():
            catalog_path = repository_root / catalog_path
    runtime = UnifiedModelRuntime.from_catalog_path(catalog_path)
    agents = config.get("agents", {})
    dr_config = dict(agents.get("dr", {})) if isinstance(agents, dict) else {}
    config["_runtime"] = runtime
    dr_config.update({"mode": "qa", "_global_config": config, "_runtime": runtime})
    return runtime, dr_config


# 问答模式是一条短路径：把问题交给调研工作流，拿到一次性回答后打印或写文件。
# 它不会创建多轮实验目录，也不会进入发现流程里的想法筛选和实验执行。
def main():
    parser = argparse.ArgumentParser(description='Vegapunk QA — one-shot question answering')
    parser.add_argument('--question', '-q', required=True, help='Research question to answer')
    parser.add_argument('--file', '-f', default=None, help='Optional file attachment')
    parser.add_argument('--output', '-o', default=None, help='Write answer to this file path')
    parser.add_argument(
        '--config',
        default='config/default_config.yaml',
        help='Vegapunk YAML config (default: config/default_config.yaml)',
    )
    args = parser.parse_args()

    # 这里使用调研适配器，是因为问答同样需要“查背景、组织证据、合成答案”的能力；
    # 只是输出直接回到终端，而不是进入后续实验阶段。
    runtime, dr_config = _load_qa_config(args.config)
    agent = DRAgent(model=runtime.model_for(capability="text"), config=dr_config)
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
