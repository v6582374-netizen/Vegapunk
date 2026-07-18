import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Collapse,
  Flex,
  Input,
  List,
  Typography,
  message,
} from "antd";
import { fetchPrompts, savePrompt, type PromptRecord } from "./api";

export default function PromptsPanel() {
  const [prompts, setPrompts] = useState<PromptRecord[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const load = useCallback(() => {
    fetchPrompts()
      .then((items) => {
        setPrompts(items);
        setError(null);
        if (selectedId === null && items.length > 0) {
          setSelectedId(items[0].id);
          setDraft(items[0].text);
        }
      })
      .catch((cause: Error) => setError(cause.message));
  }, [selectedId]);

  useEffect(load, [load]);

  const selected = useMemo(
    () => prompts.find((prompt) => prompt.id === selectedId) ?? null,
    [prompts, selectedId],
  );

  const byStage = useMemo(() => {
    const groups = new Map<string, PromptRecord[]>();
    for (const prompt of prompts) {
      const list = groups.get(prompt.stage) ?? [];
      list.push(prompt);
      groups.set(prompt.stage, list);
    }
    return [...groups.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [prompts]);

  const onSelect = (prompt: PromptRecord) => {
    setSelectedId(prompt.id);
    setDraft(prompt.text);
  };

  const onSave = () => {
    if (selectedId === null) return;
    setSaving(true);
    savePrompt(selectedId, draft)
      .then((saved) => {
        setPrompts((current) =>
          current.map((prompt) => (prompt.id === saved.id ? saved : prompt)),
        );
        message.success("已保存；改动将对下一个入队的 Launch 生效");
      })
      .catch((cause: Error) => setError(cause.message))
      .finally(() => setSaving(false));
  };

  return (
    <Card title="Prompt Library（全量可编辑；改动对下一个 Launch 生效）">
      {error !== null && <Alert type="error" message={error} style={{ marginBottom: 16 }} />}
      <Flex gap={16} style={{ minHeight: "70vh" }}>
        <div style={{ width: 340, overflow: "auto" }}>
          <Collapse
            defaultActiveKey={byStage.map(([stage]) => stage)}
            items={byStage.map(([stage, items]) => ({
              key: stage,
              label: `${stage} (${items.length})`,
              children: (
                <List
                  size="small"
                  dataSource={items}
                  renderItem={(prompt) => (
                    <List.Item
                      style={{
                        cursor: "pointer",
                        background: prompt.id === selectedId ? "#e6f4ff" : undefined,
                      }}
                      onClick={() => onSelect(prompt)}
                    >
                      <List.Item.Meta
                        title={prompt.name}
                        description={
                          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                            {prompt.id}
                          </Typography.Text>
                        }
                      />
                    </List.Item>
                  )}
                />
              ),
            }))}
          />
        </div>
        <Flex vertical gap={12} style={{ flex: 1 }}>
          {selected !== null && (
            <>
              <Typography.Title level={5} style={{ margin: 0 }}>
                {selected.name}
              </Typography.Title>
              <Typography.Paragraph type="secondary" style={{ margin: 0 }}>
                {selected.description}
              </Typography.Paragraph>
              <Typography.Text code>{selected.id}</Typography.Text>
              <Input.TextArea
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                autoSize={{ minRows: 18, maxRows: 32 }}
                style={{ fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace" }}
              />
              <Flex gap={8}>
                <Button
                  onClick={() => selected !== null && setDraft(selected.text)}
                  disabled={selected !== null && draft === selected.text}
                >
                  重置
                </Button>
                <Button
                  type="primary"
                  loading={saving}
                  onClick={onSave}
                  disabled={selected !== null && draft === selected.text}
                >
                  保存
                </Button>
              </Flex>
            </>
          )}
        </Flex>
      </Flex>
    </Card>
  );
}
