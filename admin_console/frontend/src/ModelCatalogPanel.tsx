import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Checkbox,
  Collapse,
  Flex,
  Input,
  InputNumber,
  Select,
  Typography,
  message,
} from "antd";
import {
  fetchModelCatalog,
  saveModelCatalog,
  type ModelCatalog,
} from "./api";

const ALL_CAPABILITIES = [
  "text",
  "json",
  "tools",
  "vision",
  "reasoning",
  "continuation",
  "image_generation",
  "embedding",
];

export default function ModelCatalogPanel() {
  const [catalog, setCatalog] = useState<ModelCatalog | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);

  const load = useCallback(() => {
    fetchModelCatalog()
      .then((body) => {
        setCatalog(body);
        setDirty(false);
        setError(null);
      })
      .catch((cause: Error) => setError(cause.message));
  }, []);

  useEffect(load, [load]);

  const modelIds = useMemo(
    () => (catalog === null ? [] : Object.keys(catalog.models).sort()),
    [catalog],
  );

  const update = (mutator: (current: ModelCatalog) => ModelCatalog) => {
    setCatalog((current) => (current === null ? current : mutator(current)));
    setDirty(true);
  };

  const onSave = () => {
    if (catalog === null) return;
    setSaving(true);
    saveModelCatalog(catalog)
      .then((saved) => {
        setCatalog(saved);
        setDirty(false);
        message.success("已保存；改动将对下一个入队的 Launch 生效");
      })
      .catch((cause: Error) => setError(cause.message))
      .finally(() => setSaving(false));
  };

  if (catalog === null) {
    return error !== null ? <Alert type="error" message={error} /> : null;
  }

  return (
    <Card
      title="Unified Model Catalog（文本与图像绑定须同 Provider，ADR-0129）"
      extra={
        <Flex gap={8}>
          <Button onClick={load}>重置</Button>
          <Button type="primary" loading={saving} disabled={!dirty} onClick={onSave}>
            保存
          </Button>
        </Flex>
      }
    >
      {error !== null && <Alert type="error" message={error} style={{ marginBottom: 16 }} />}

      <Typography.Title level={5}>Capability Model Bindings</Typography.Title>
      <Flex vertical gap={12} style={{ marginBottom: 24 }}>
        <Flex align="center" gap={12}>
          <Typography.Text style={{ width: 200 }}>active_text_model</Typography.Text>
          <Select
            style={{ width: 360 }}
            value={catalog.active_text_model}
            options={modelIds.map((id) => ({ value: id, label: id }))}
            onChange={(value) => update((c) => ({ ...c, active_text_model: value }))}
          />
        </Flex>
        {Object.entries(catalog.capability_models).map(([role, identity]) => (
          <Flex key={role} align="center" gap={12}>
            <Typography.Text style={{ width: 200 }}>{role}</Typography.Text>
            <Select
              style={{ width: 360 }}
              value={identity}
              options={modelIds.map((id) => ({ value: id, label: id }))}
              onChange={(value) =>
                update((c) => ({
                  ...c,
                  capability_models: { ...c.capability_models, [role]: value },
                }))
              }
            />
          </Flex>
        ))}
      </Flex>

      <Collapse
        items={[
          {
            key: "providers",
            label: `Providers (${Object.keys(catalog.providers).length})`,
            children: (
              <Flex vertical gap={16}>
                {Object.entries(catalog.providers).map(([name, settings]) => (
                  <Card key={name} size="small" title={name}>
                    {Object.entries(settings).map(([key, value]) => (
                      <Flex key={key} align="center" gap={12} style={{ marginBottom: 8 }}>
                        <Typography.Text code style={{ width: 160 }}>
                          {key}
                        </Typography.Text>
                        {typeof value === "number" ? (
                          <InputNumber
                            value={value}
                            onChange={(next) =>
                              update((c) => ({
                                ...c,
                                providers: {
                                  ...c.providers,
                                  [name]: { ...c.providers[name], [key]: next },
                                },
                              }))
                            }
                          />
                        ) : typeof value === "string" || value === null ? (
                          <Input
                            style={{ width: 420 }}
                            value={value ?? ""}
                            onChange={(event) =>
                              update((c) => ({
                                ...c,
                                providers: {
                                  ...c.providers,
                                  [name]: {
                                    ...c.providers[name],
                                    [key]: event.target.value,
                                  },
                                },
                              }))
                            }
                          />
                        ) : (
                          <Input.TextArea
                            style={{ width: 420 }}
                            defaultValue={JSON.stringify(value)}
                            onBlur={(event) => {
                              try {
                                const parsed = JSON.parse(event.target.value) as unknown;
                                update((c) => ({
                                  ...c,
                                  providers: {
                                    ...c.providers,
                                    [name]: { ...c.providers[name], [key]: parsed },
                                  },
                                }));
                              } catch {
                                message.error(`${name}.${key} JSON 不合法`);
                              }
                            }}
                          />
                        )}
                      </Flex>
                    ))}
                  </Card>
                ))}
              </Flex>
            ),
          },
          {
            key: "models",
            label: `Models (${modelIds.length})`,
            children: (
              <Flex vertical gap={16}>
                {modelIds.map((id) => {
                  const model = catalog.models[id];
                  return (
                    <Card key={id} size="small" title={id}>
                      <Flex vertical gap={8}>
                        <Flex gap={12}>
                          <Typography.Text>provider</Typography.Text>
                          <Typography.Text code>{model.provider}</Typography.Text>
                          <Typography.Text>model</Typography.Text>
                          <Typography.Text code>{model.model}</Typography.Text>
                        </Flex>
                        <Checkbox.Group
                          options={ALL_CAPABILITIES}
                          value={model.capabilities}
                          onChange={(next) =>
                            update((c) => ({
                              ...c,
                              models: {
                                ...c.models,
                                [id]: {
                                  ...c.models[id],
                                  capabilities: next as string[],
                                },
                              },
                            }))
                          }
                        />
                      </Flex>
                    </Card>
                  );
                })}
              </Flex>
            ),
          },
        ]}
      />
    </Card>
  );
}
