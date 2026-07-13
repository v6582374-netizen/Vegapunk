import sys
import os
import json
import re
from typing import Any, Dict, List, Optional, Union

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from agents.base_agent import BaseAgent
from models import get_model
from tools import get_tool_manager
from utils.reference_manager import ReferenceManager
from utils.logger import get_logger
from utils.prompt_loader import load_prompt
from internagent.mas.models.runtime import (
    FunctionCallOutput,
    FunctionTool,
    Message,
    ModelRunRequest,
    ModelRunResult,
    ReasoningConfig,
)


class ExecutionAgent(BaseAgent):
    """
    执行代理，负责调用工具并处理工具调用结果
    """
    
    def __init__(self, model: str = "deepseek-r1", tools: List[Dict[str, Any]] = None, tool_mode: str = "local", config=None, summarizer_model: str = None, reference_manager=None, **model_kwargs):
        """
        初始化执行代理
        
        Args:
            model: 使用的模型名称
            tools: 可用的工具列表
            tool_mode: 工具模式，'test'使用测试工具，其他值使用本地工具
            config: TaskWorkflowConfig配置对象
            summarizer_model: 用于总结的模型名称（如果为None则使用model）
            reference_manager: 参考文献管理器（如果为None则创建新的）
            **model_kwargs: 传递给模型的参数
        """
        super().__init__(model=model, tools=tools)
        self.model_instance = get_model(model, **model_kwargs)
        self.tool_mode = tool_mode
        # 使用基类的 _logger，可以通过 _set_logger 动态更改
        self._set_logger(get_logger("ExecutionAgent"))
        self.tool_manager = get_tool_manager(mode=tool_mode, config=config)
        self.tool_map = self._build_tool_map()
        self.model_kwargs = model_kwargs
        self.config = config or {}
        
        # 从配置加载execution prompt（如果配置中没有指定，使用默认值）
        execution_config = {
            "prompt_path": self.config.get("execution_prompt_path"),
            "prompt_name": self.config.get("execution_prompt_name")
        }
        self.execution_prompt = load_prompt(
            execution_config,
            default_name="EXECUTION_PROMPT"
        )
        
        # 从配置加载summary prompt（如果配置中没有指定，使用默认值）
        summary_config = {
            "prompt_path": self.config.get("summary_prompt_path"),
            "prompt_name": self.config.get("summary_prompt_name")
        }
        self.summary_prompt = load_prompt(
            summary_config,
            default_name="SUMMARY_PROMPT"
        )
        
        self.max_tool_calls = self.config.get('max_tool_calls', 15)
        self.node_id = None  # 节点ID
        self.subtask_id = None  # 子任务ID
        # 使用传入的reference_manager或创建新的
        self.reference_manager = reference_manager if reference_manager is not None else ReferenceManager()
        self.summarizer_model = summarizer_model or model  # 如果没有指定summarizer_model，使用默认model
    
    def _build_tool_map(self) -> Dict[str, Dict[str, Any]]:
        """
        构建工具映射表
        
        Returns:
            工具名称到工具配置的映射
        """
        tool_map = {}
        
        # 如果提供了显式的工具列表，使用它们
        if self.tools:
            for tool in self.tools:
                if isinstance(tool, dict) and 'name' in tool:
                    tool_map[tool['name']] = tool
        else:
            # 否则从工具管理器获取工具
            self._logger.info(f"没有提供显式的工具列表，从工具管理器获取工具")
            available_tools = self.tool_manager.list_tools()
            for tool_name in available_tools:
                tool_info = self.tool_manager.get_tool_info(tool_name)
                if tool_info:
                    # 为工具创建标准格式的配置
                    tool_config = {
                        "name": tool_name,
                        "type": "function",
                        "function_name": tool_name,
                        "description": tool_info.get("doc", f"Tool: {tool_name}"),
                        "required_parameters": tool_info.get("required_parameters", []),
                        "parameters": tool_info.get("parameters", {})
                    }
                    tool_map[tool_name] = tool_config
        
        self._logger.info(f"构建工具映射，共 {len(tool_map)} 个工具: {list(tool_map.keys())}")
        return tool_map
    
    def execute_one_step(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行子任务，让模型选择并调用工具. 如果模型返回tool_calls，则调用工具，并返回工具调用结果, 然后结束, 如果需要反复执行, 直到模型返回tool_calls为空为止. 则需要调用execute方法.
        
        Args:
            input_data: 包含以下键的字典：
                - messages: 历史消息
                
        Returns:
            执行结果字典
        """
        try:
            request = input_data.get("request")
            if not isinstance(request, ModelRunRequest):
                raise TypeError("execute_one_step requires a ModelRunRequest")
            response = self.model_instance.run(request)
            tool_results = []
            for index, tool_call in enumerate(response.tool_calls):
                self._logger.info(
                    f"执行工具调用 {index + 1}/{len(response.tool_calls)}: "
                    f"{tool_call.name}"
                )
                result = self._execute_single_tool_call(
                    {
                        "name": tool_call.name,
                        "arguments": dict(tool_call.arguments),
                    }
                )
                result["call_id"] = tool_call.call_id
                tool_results.append(result)
            return {
                "tool_calls": tool_results,
                "model_result": response,
            }
                
        except Exception as e:
            self._logger.error(f"Model execution failed: {e}")
            return {
                "error": str(e),
                "tool_calls": [],
                "summary": f"Execution failed: {str(e)}"
            }
    
    def execute(self, subtask: str, context: Dict[str, Any], use_planner: bool = True, query = None) -> Dict[str, Any]:
        """
        执行单个子任务，包含工具调用循环, 以及最后的总结
        
        Args:
            subtask: 子任务描述
            context: 上下文信息，包含：
                - task: 总体任务
                - history_subtasks: 历史子任务列表
                - knowledge_info: 知识信息
                - node_id: 节点ID（可选）
                - subtask_id: 子任务ID（可选）
                
        Returns:
            子任务执行结果
        """

        
        try:
            self._logger.info(f"开始执行子任务: {subtask}")
            
            # 从context中获取信息
            task = context.get("task", "")
            history_subtasks = context.get("history_subtasks", [])
            knowledge_info = context.get("knowledge_info", {})
            file_path = context.get("file_path", "")
            self.node_id = context.get("node_id", None)
            self.subtask_id = context.get("subtask_id", None)
            
            # 初始化消息历史，使用execution_prompt
            formatted_prompt = self.execution_prompt.format(
                task=task,
                query = query,
                history_subtasks=json.dumps(history_subtasks, ensure_ascii=False, indent=2) if history_subtasks else "[]",
                subtask=subtask,
                knowledge_info=json.dumps(knowledge_info, ensure_ascii=False, indent=2) if knowledge_info else "{}",
                file_path=file_path
            )
            tools = self._convert_tool_map_to_runtime_tools()
            request = ModelRunRequest(
                input=(Message.user(formatted_prompt),),
                tools=tools,
                reasoning=ReasoningConfig(context="all_turns"),
            )
            execution_trace = []
            tool_call_count = 0
            max_tool_calls = self.max_tool_calls  # 防止无限循环
            
            while tool_call_count < max_tool_calls:
                self._logger.info(f"执行工具调用循环 {tool_call_count + 1}/{max_tool_calls}")
                
                # 调用执行代理
                execution_input = {"request": request}
                
                result = self.execute_one_step(execution_input)
                
                
                response = result.get("model_result")
                if not isinstance(response, ModelRunResult):
                    break
                tool_results = result.get("tool_calls", [])
                execution_trace.append(
                    {
                        "response_id": response.response_id,
                        "content": response.text,
                        "tool_calls": [
                            {
                                "call_id": call.call_id,
                                "name": call.name,
                                "arguments": dict(call.arguments),
                            }
                            for call in response.tool_calls
                        ],
                        "tool_results": tool_results,
                    }
                )

                if tool_results:
                    tool_call_count += len(tool_results)
                    outputs = tuple(
                        FunctionCallOutput(
                            call_id=tool_result["call_id"],
                            output=(
                                tool_result.get("result")
                                if tool_result.get("success")
                                else {"error": tool_result.get("error", "Unknown error")}
                            ),
                        )
                        for tool_result in tool_results
                    )
                    request = ModelRunRequest(
                        input=outputs,
                        tools=tools,
                        previous_response_id=response.response_id,
                        reasoning=ReasoningConfig(context="all_turns"),
                    )
                    
                    # 如果工具调用成功，继续循环
                    if any(tc.get("success", False) for tc in tool_results):
                        # self._logger.info("工具调用成功，继续循环")    
                        continue
                    else:
                        # 所有工具调用都失败，停止循环
                        self._logger.warning("所有工具调用都失败，停止循环")
                        break
                        
                else:
                    # 没有工具调用，任务完成
                    self._logger.info("没有检测到工具调用，子任务完成")
                    break
            
            # 生成最终响应
            final_result = self._generate_subtask_response(
                subtask, execution_trace, context
            )
            try:
                # 尝试提取JSON（可能在文本中间或有额外内容）
                parsed_result = self._extract_and_parse_json(final_result)
                if parsed_result:
                    success = parsed_result.get("success", True)
                    summary = parsed_result.get("summary", "")
                else:
                    # 如果无法提取JSON，使用原始响应
                    summary = final_result
                    success = True
            except Exception as e:
                self._logger.warning(f"JSON解析失败，使用原始响应: {e}")
                # 如果JSON解析失败，使用原始响应作为summary
                summary = final_result
                success = True
            
            return {
                "subtask": subtask,
                "completed": True,
                "tool_calls": tool_call_count,
                "success": success,
                "execution_trace": execution_trace,
                "summary": summary
            }
            
        except Exception as e:
            self._logger.error(f"子任务执行失败: {e}")
            return {
                "subtask": subtask,
                "completed": False,
                "error": str(e),
                "tool_calls": 0,
                "summary": f"执行失败: {str(e)}",
                "success": False
            }
    
    def _extract_and_parse_json(self, text: str) -> Optional[Dict[str, Any]]:
        """
        从文本中提取并解析JSON，处理模型返回JSON后附加额外内容的情况
        
        Args:
            text: 可能包含JSON的文本
            
        Returns:
            解析后的字典，如果无法解析则返回None
        """
        try:
            # 首先尝试直接解析
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        
        # 尝试查找JSON对象的开始和结束
        try:
            # 查找第一个 { 和最后一个匹配的 }
            start_idx = text.find('{')
            if start_idx == -1:
                return None
            
            # 从第一个 { 开始，找到匹配的 }
            brace_count = 0
            end_idx = -1
            for i in range(start_idx, len(text)):
                if text[i] == '{':
                    brace_count += 1
                elif text[i] == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        end_idx = i + 1
                        break
            
            if end_idx == -1:
                return None
            
            # 提取并解析JSON
            json_str = text[start_idx:end_idx]
            return json.loads(json_str)
            
        except Exception as e:
            self._logger.debug(f"无法从文本中提取JSON: {e}")
            return None
    
    def _generate_subtask_response(self, subtask: str, messages: List[Dict[str, Any]], context: Dict[str, Any]) -> str:
        """
        生成子任务的最终响应
        
        Args:
            subtask: 子任务描述
            messages: 消息历史
            context: 上下文信息
            
        Returns:
            最终响应
        """
        try:
            self._logger.info(f"开始生成子任务阶段总结: {subtask}")
            
            summary_prompt = self.summary_prompt.format(
                subtask=subtask,
                messages=json.dumps(messages, ensure_ascii=False, indent=2) if messages else "[]",
                knowledge_info=json.dumps(context.get("knowledge_info", {}), ensure_ascii=False, indent=2) if context.get("knowledge_info", {}) else "{}",
            ) 

            self._logger.info(f"子任务阶段总结提示: {summary_prompt}")
            
            # 调用summarizer模型生成总结
            self._logger.info(f"使用模型 {self.summarizer_model} 生成子任务总结")
            summarizer_instance = get_model(self.summarizer_model, **self.model_kwargs)
            final_response = summarizer_instance.generate(summary_prompt)
            
            self._logger.info(f"子任务阶段总结内容: {final_response}")
            
            return final_response
            
        except Exception as e:
            self._logger.error(f"生成子任务阶段总结失败: {e}")
            return f"子任务'{subtask}'执行完成，但生成总结时出现错误: {str(e)}"
    
    def _execute_single_tool_call(self, tool_call: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行单个工具调用
        
        Args:
            tool_call: 工具调用信息
            
        Returns:
            工具调用结果
        """
        tool_name = tool_call.get("name")
        arguments = tool_call.get("arguments", {})
        
        if not tool_name:
            raise ValueError("Tool name is required")
        
        # 查找工具
        tool_config = self.tool_map.get(tool_name)
        if not tool_config:
            raise ValueError(f"Tool '{tool_name}' not found in available tools")
        
        # 验证参数
        self._validate_tool_arguments(tool_config, arguments)
        
        # 执行工具
        try:
            result = self._call_tool(tool_config, arguments)

            self._logger.info(f"工具 {tool_name} 执行结果: {result}, 类型: {type(result)}")
            
            # 如果是搜索工具，提取URL并添加到参考文献管理器，同时获取修改后的result
            if self._is_search_tool(tool_name):
                extracted_urls, modified_result = self._extract_urls_from_result(result, tool_name)
                if extracted_urls:
                    self._logger.info(f"从工具 {tool_name} 中提取到 {len(extracted_urls)} 个URL")
                    # 使用修改后的result（包含tag信息）
                    result = modified_result
            
            # 发送工具调用成功事件
            if self.node_id is not None and self.subtask_id is not None:
                self.send_redis_event("get_subtask_process", {
                    "node_id": self.node_id,
                    "subtask_id": self.subtask_id,
                    "process": {
                        "tool_name": tool_name,
                        "arguments": arguments,
                        "result": result,  # 限制结果长度，避免过大
                    }
                })
            
            return {
                "tool_name": tool_name,
                "success": True,
                "arguments": arguments,
                "result": result,
                "error": None
            }
        except Exception as e:
            return {
                "tool_name": tool_name,
                "success": False,
                "arguments": arguments,
                "result": None,
                "error": str(e)
            }
    
    def _validate_tool_arguments(self, tool_config: Dict[str, Any], arguments: Dict[str, Any]) -> None:
        """
        验证工具参数
        
        Args:
            tool_config: 工具配置
            arguments: 提供的参数
            
        Raises:
            ValueError: 参数验证失败
        """
        required_params = tool_config.get("required_parameters", [])
        for param in required_params:
            if param not in arguments:
                raise ValueError(f"Required parameter '{param}' is missing for tool '{tool_config['name']}'")
    
    def _call_tool(self, tool_config: Dict[str, Any], arguments: Dict[str, Any]) -> Any:
        """
        调用工具函数
        
        Args:
            tool_config: 工具配置
            arguments: 工具参数
            
        Returns:
            工具执行结果
        """
        # 目前只支持函数类型工具
        tool_type = tool_config.get("type", "function")
        
        if tool_type == "function":
            return self._call_function_tool(tool_config, arguments)
        else:
            raise ValueError(f"Unsupported tool type: {tool_type}")
    
    def _call_function_tool(self, tool_config: Dict[str, Any], arguments: Dict[str, Any]) -> Any:
        """
        调用函数类型工具
        
        Args:
            tool_config: 工具配置
            arguments: 工具参数
            
        Returns:
            工具执行结果
        """
        function_name = tool_config.get("name")
        
        try:
            # 使用工具管理器动态调用工具
            result = self.tool_manager.call_tool(function_name, **arguments)
            return result
        except Exception as e:
            self._logger.error(f"Tool execution failed for {function_name}: {e}")
            return f"Error executing {function_name}: {str(e)}"
    
    def _generate_summary(self, results: List[Dict[str, Any]]) -> str:
        """
        生成执行结果摘要
        
        Args:
            results: 执行结果列表
            
        Returns:
            摘要文本
        """
        successful_calls = sum(1 for result in results if result.get("success", False))
        total_calls = len(results)
        
        summary = f"Executed {total_calls} tool calls, {successful_calls} successful"
        
        if results:
            tool_names = [result.get("tool_name", "unknown") for result in results]
            summary += f". Tools used: {', '.join(tool_names)}"
        
        return summary
    
    def tool_call(self, tool_name: str, arguments: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        执行工具调用的便捷方法
        
        Args:
            tool_name: 工具名称
            arguments: 工具参数
            context: 上下文信息
            
        Returns:
            工具调用结果
        """
        tool_call = {
            "name": tool_name,
            "arguments": arguments
        }
        
        return self._execute_single_tool_call(tool_call, context or {})
    
    def add_tool(self, tool: Dict[str, Any]) -> None:
        """
        添加工具并更新工具映射
        
        Args:
            tool: 工具配置字典
        """
        super().add_tool(tool)
        self.tool_map = self._build_tool_map()
    
    def get_available_tools(self) -> List[str]:
        """
        获取可用工具名称列表
        
        Returns:
            工具名称列表
        """
        return list(self.tool_map.keys())
    
    def get_tool_info(self, tool_name: str) -> Optional[Dict[str, Any]]:
        """
        获取工具信息
        
        Args:
            tool_name: 工具名称
            
        Returns:
            工具配置信息，如果不存在则返回None
        """
        return self.tool_map.get(tool_name)
    
    def _convert_tool_map_to_runtime_tools(self) -> tuple[FunctionTool, ...]:
        """Convert DR tool metadata once at the Runtime boundary."""
        return tuple(
            FunctionTool(
                name=tool_config["name"],
                description=tool_config.get("description", ""),
                parameters={
                    "type": "object",
                    "properties": tool_config.get("parameters", {}),
                    "required": tool_config.get("required_parameters", []),
                },
            )
            for tool_config in self.tool_map.values()
        )
    
    def _is_search_tool(self, tool_name: str) -> bool:
        """
        判断工具是否是搜索工具
        
        Args:
            tool_name: 工具名称
            
        Returns:
            是否是搜索工具
        """
        # 搜索工具列表：提取reference的工具
        allowed_tools = ['search_wiki', 'search_and_summarize_papers', 'search_and_summarize_webpages',
                         'search_tavily', 'search_volc', 'search_google',
                         'search_arxiv', 'search_openalex', 'search_crossref']
        return tool_name in allowed_tools
    
    
    def _extract_urls_from_result(self, result: Any, tool_name: str) -> tuple[List[str], Any]:
        """
        从工具结果中提取URL、标题和类型，并将tag添加到原始result中

        根据不同工具的返回格式处理：
        - search_wiki: 返回 dict，包含 url 和 title
        - search_and_summarize_papers: 返回 list，每个元素是 dict，包含 url 和 title
        - search_and_summarize_webpages: 返回 list，每个元素是 dict，包含 url 和 title
        - search_volc: 返回 list，每个元素是 dict，包含 url 和 title
        - search_tavily: 返回 list，每个元素是 dict，包含 url 和 title

        Args:
            result: 工具执行结果
            tool_name: 工具名称

        Returns:
            (提取到的URL列表, 修改后的result)
        """
        urls = []
        modified_result = result  # 默认返回原始result

        try:
            # 根据工具名称确定引用类型和处理方式
            if tool_name == 'search_wiki':
                # search_wiki 返回字符串，需要解析为字典
                if isinstance(result, str):
                    try:
                        import ast
                        result_dict = ast.literal_eval(result)
                        if isinstance(result_dict, dict) and 'url' in result_dict:
                            url = result_dict['url']
                            title = result_dict.get('title', '')
                            if url and isinstance(url, str):
                                tag = self.reference_manager.add_url(url, title=title, ref_type='webpage')
                                urls.append(url)
                                # 将tag添加到result_dict中
                                result_dict['tag'] = tag
                                # 将修改后的字典作为新的result
                                modified_result = result_dict
                                self._logger.info(f"添加URL到参考文献: {tag} -> {url} (webpage)")
                    except Exception as e:
                        self._logger.warning(f"解析search_wiki结果失败: {e}")
                elif isinstance(result, dict) and 'url' in result:
                    # 如果已经是字典格式
                    url = result['url']
                    title = result.get('title', '')
                    if url and isinstance(url, str):
                        tag = self.reference_manager.add_url(url, title=title, ref_type='webpage')
                        urls.append(url)
                        # 将tag添加到result中（直接修改）
                        result['tag'] = tag
                        modified_result = result
                        self._logger.info(f"添加URL到参考文献: {tag} -> {url} (webpage)")

            elif tool_name == 'search_and_summarize_papers':
                # search_and_summarize_papers 返回 list
                if isinstance(result, list):
                    for item in result:
                        if isinstance(item, dict):
                            # 优先使用 pdf_url，如果没有则尝试 url
                            url = item.get('pdf_url') or item.get('url')
                            title = item.get('title', '')
                            if url and isinstance(url, str):
                                tag = self.reference_manager.add_url(url, title=title, ref_type='paper')
                                urls.append(url)
                                # 将tag添加到item中（直接修改list中的item）
                                item['tag'] = tag
                                self._logger.info(f"添加URL到参考文献: {tag} -> {url} (paper)")
                    modified_result = result  # list已经被直接修改

            elif tool_name in ('search_and_summarize_webpages', 'search_volc', 'search_tavily', 'search_google'):
                # 这些工具都返回 list，每个元素是 dict，包含 url 和 title
                if isinstance(result, list):
                    for item in result:
                        if isinstance(item, dict) and 'url' in item:
                            url = item['url']
                            title = item.get('title', '')
                            if url and isinstance(url, str) and url.strip():
                                tag = self.reference_manager.add_url(url, title=title, ref_type='webpage')
                                urls.append(url)
                                # 将tag添加到item中（直接修改list中的item）
                                item['tag'] = tag
                                self._logger.info(f"添加URL到参考文献: {tag} -> {url} (webpage)")
                    modified_result = result  # list已经被直接修改

            elif tool_name in ('search_arxiv', 'search_openalex', 'search_crossref'):
                # 论文搜索工具：返回 list，每个元素包含 url/pdf_url 和 title
                if isinstance(result, list):
                    for item in result:
                        if isinstance(item, dict):
                            url = item.get('pdf_url') or item.get('url')
                            title = item.get('title', '')
                            if url and isinstance(url, str) and url.strip():
                                tag = self.reference_manager.add_url(url, title=title, ref_type='paper')
                                urls.append(url)
                                item['tag'] = tag
                                self._logger.info(f"添加URL到参考文献: {tag} -> {url} (paper)")
                    modified_result = result
        
        except Exception as e:
            self._logger.warning(f"从工具结果中提取URL时出错: {e}")
        
        return urls, modified_result
    
    def _append_references_to_text(self, text: str) -> str:
        """
        在文本末尾附加参考文献列表（包含标题和类型）
        
        Args:
            text: 原始文本
            
        Returns:
            附加了参考文献的文本
        """
        # 提取文本中使用的引用标签
        used_tags = set(re.findall(r'\[R(\d+)\]', text))
        
        if not used_tags:
            # 如果没有使用引用标签，不添加参考文献
            return text
        
        # 获取所有参考文献
        all_refs = self.reference_manager.get_reference_list()
        
        # 只包含被使用的参考文献
        used_refs = []
        for ref in all_refs:
            tag_num = ref['tag'][1:]  # 去掉'R'前缀
            if tag_num in used_tags:
                used_refs.append(ref)
        
        if not used_refs:
            return text
        
        # 构建参考文献部分
        ref_lines = ["\n\n## References"]
        for ref in used_refs:
            # 添加类型标记
            type_label = "📄" if ref['type'] == "paper" else "🌐"
            title = ref.get('title', '')
            url = ref['url']
            
            # 格式: [R1] 📄 Title - URL
            if title and title != url:
                ref_lines.append(f"[{ref['tag']}] {type_label} {title} - {url}")
            else:
                ref_lines.append(f"[{ref['tag']}] {type_label} {url}")
        
        return text + "\n".join(ref_lines)
    
    def get_reference_manager(self) -> ReferenceManager:
        """
        获取参考文献管理器
        
        Returns:
            参考文献管理器实例
        """
        return self.reference_manager
