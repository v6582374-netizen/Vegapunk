#!/usr/bin/env python3
"""InternAgent — master launcher."""

import argparse
import sys
import traceback

from dotenv import load_dotenv

load_dotenv(override=True)


# 这是给人使用的总入口：先判断用户要的是直接问答，还是完整的发现实验流程。
# 真正重的初始化会留给下游脚本，避免每次启动都加载全部依赖。
def main():
    parser = argparse.ArgumentParser(
        description='InternAgent',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "QA mode:        python launch.py --mode qa --question '...' [--output out.md]\n"
            "Discovery mode: python launch.py --mode discovery --task AutoSeg "
            "--exp_backend claudecode [--mode experiment|report]"
        )
    )
    parser.add_argument(
        '--mode', choices=['qa', 'discovery'], required=True,
        help='Task type: qa for one-shot answers, discovery for idea generation + experiments'
    )
    args, remaining = parser.parse_known_args()

    # 下游脚本各自有一套命令行参数；这里先拿掉总入口消费过的选择项，
    # 让后续解析只看到自己认识的参数。
    sys.argv = [sys.argv[0]] + remaining  # strip --mode before handing off

    if args.mode == 'qa':
        # 延迟导入让轻量问答路径保持简单，也避免发现实验依赖影响问答启动。
        from launch_qa import main as qa_main
        qa_main()
    elif args.mode == 'discovery':
        # 发现流程会继续负责生成想法、准备实验目录、调用实验后端和汇总结果。
        from launch_discovery import main as discovery_main
        discovery_main()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nPipeline interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nFatal error: {str(e)}")
        traceback.print_exc()
