"""
Online Memory Saver

Provides functionality to save experiment results to memory in real-time
when experiments complete during the pipeline execution.
"""

from pathlib import Path
from typing import Dict, Any, Optional
from .task_memory import TaskMemoryLayer


# 在线记忆是在实验完成当下写入的旁路记录；它不参与实验是否成功的判定，
# 只负责把成功结果整理到任务级记忆里，供后续检索或分析使用。
class OnlineMemorySaver:
    """
    Online memory saver for real-time experiment result storage

    This class integrates with the experiment pipeline to automatically save
    experiment results to TaskMemoryLayer when experiments complete.
    """

    def __init__(self, config: Dict[str, Any], task_name: str):
        """
        Initialize online memory saver

        Args:
            config: Configuration dictionary with 'task_memory' and 'exp_analyze' sections
            task_name: Task name (e.g., 'AutoPower', 'AutoMem')
        """
        self.config = config
        self.task_name = task_name
        # Fix: online_memory is under 'memory' section in config
        memory_config = config.get("memory", {})
        online_memory_config = memory_config.get("online_memory", {})
        self.enabled = online_memory_config.get("enabled", False)

        if self.enabled:
            # 每个任务写入自己的记忆目录，避免不同数据集或目标的经验互相混在一起。
            base_dir = memory_config.get("task_memory", {}).get("memory_dir", "./config/mem_store")
            task_memory_dir = f"{base_dir}/{task_name}"

            # 这里把全局配置重排成底层记忆组件认识的形状，同时保留模型
            # endpoint 和 Responses 运行策略供 exp_analyze 继承。
            task_config = config.copy()
            task_config["task_memory"] = memory_config.get("task_memory", {}).copy()
            # Override memory_dir for this task
            task_config["task_memory"]["memory_dir"] = task_memory_dir

            # Initialize TaskMemoryLayer
            self.memory = TaskMemoryLayer.from_config(task_config)
            print(f"[OnlineMemory] Initialized for task: {task_name}")
            print(f"[OnlineMemory] Memory directory: {self.memory.memory_dir}")
            print(f"[OnlineMemory] Existing records: {len(self.memory.records)}")
        else:
            self.memory = None
            print("[OnlineMemory] Disabled (set 'online_memory.enabled' to True to enable)")

    def save_idea_result(
        self,
        idea: Dict[str, Any],
        results_dir: Path,
        session_id: Optional[str] = None,
        traj_path: Optional[Path] = None
    ) -> bool:
        """
        Save experiment result for an idea to memory

        Args:
            idea: Idea dictionary with keys: name, title, description, statement, method
            results_dir: Path to experiment results directory (contains run_0, run_1, ...)
            session_id: Optional session ID for tracking
            traj_path: Optional path to trajectory file

        Returns:
            True if saved successfully, False otherwise
        """
        if not self.enabled:
            return False

        try:
            print(f"\n[OnlineMemory] Saving result for idea: {idea.get('name', 'unknown')}")
            print(f"[OnlineMemory] Results directory: {results_dir}")

            # 一个实验目录可能有多次 run；聚合策略决定保存最好一次还是汇总结果。
            aggregation = self.config.get("memory", {}).get("online_memory", {}).get("aggregation", "best")

            # 底层会读取结果目录、轨迹和想法信息，整理成可检索的任务记忆记录。
            record = self.memory.save_experiment_result(
                idea=idea,
                results_dir=results_dir,
                task_name=self.task_name,
                session_id=session_id or "online",
                aggregation=aggregation,
                traj_path=traj_path
            )

            if record:
                print(f"[OnlineMemory] ✓ Saved successfully")
                print(f"[OnlineMemory]   Record ID: {record.record_id}")
                print(f"[OnlineMemory]   Label: {record.label}")
                print(f"[OnlineMemory]   Improvement: {record.overall_improvement_rate:+.2f}%")
                print(f"[OnlineMemory]   Total records in memory: {len(self.memory.records)}")
                return True
            else:
                print(f"[OnlineMemory] ✗ Failed to save (no valid results)")
                return False

        except Exception as e:
            print(f"[OnlineMemory] ✗ Error saving to memory: {e}")
            import traceback
            traceback.print_exc()
            return False

    def get_statistics(self) -> Dict[str, Any]:
        """Get current memory statistics"""
        if not self.enabled or not self.memory:
            return {"enabled": False}

        return {
            "enabled": True,
            "task_name": self.task_name,
            "total_records": len(self.memory.records),
            **self.memory.get_statistics()
        }
