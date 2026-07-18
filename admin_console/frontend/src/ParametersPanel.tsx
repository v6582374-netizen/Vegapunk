import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Collapse,
  Flex,
  Input,
  InputNumber,
  Select,
  Switch,
  Tooltip,
  Typography,
  message,
} from "antd";
import { fetchParameters, saveParameters, type ParameterField } from "./api";

type Values = Record<string, unknown>;

function literalOptions(type: string): string[] | null {
  const match = type.match(/Literal\[(.+?)\]/);
  if (match === null) return null;
  return match[1].split(",").map((part) => part.trim().replace(/^'|'$/g, ""));
}

function setDeep(values: Values, path: string[], value: unknown): Values {
  if (path.length === 0) return values;
  const [head, ...rest] = path;
  const child = values[head];
  return {
    ...values,
    [head]:
      rest.length === 0
        ? value
        : setDeep((child ?? {}) as Values, rest, value),
  };
}

function FieldControl({
  value,
  field,
  onChange,
}: {
  value: unknown;
  field: ParameterField | undefined;
  onChange: (next: unknown) => void;
}) {
  const options = field === undefined ? null : literalOptions(field.type);
  if (options !== null) {
    return (
      <Select
        style={{ width: 240 }}
        value={value as string}
        options={options.map((option) => ({ value: option, label: option }))}
        onChange={onChange}
      />
    );
  }
  if (typeof value === "boolean") {
    return <Switch checked={value} onChange={onChange} />;
  }
  if (typeof value === "number") {
    return (
      <InputNumber
        style={{ width: 240 }}
        value={value}
        min={field?.ge ?? field?.gt}
        max={field?.le ?? field?.lt}
        onChange={(next) => onChange(next)}
      />
    );
  }
  if (typeof value === "string") {
    return (
      <Input
        style={{ width: 360 }}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
    );
  }
  // Lists, free-form dicts, and null: edit as JSON.
  return (
    <Input.TextArea
      style={{ width: 480 }}
      autoSize={{ minRows: 1, maxRows: 8 }}
      defaultValue={JSON.stringify(value)}
      onBlur={(event) => {
        try {
          onChange(JSON.parse(event.target.value));
        } catch {
          message.error("JSON 格式不合法，未应用该修改");
        }
      }}
    />
  );
}

function SectionForm({
  values,
  prefix,
  catalog,
  onChange,
}: {
  values: Values;
  prefix: string;
  catalog: Map<string, ParameterField>;
  onChange: (path: string[], value: unknown) => void;
}) {
  const scalarKeys: string[] = [];
  const sectionKeys: string[] = [];
  for (const key of Object.keys(values)) {
    const child = values[key];
    const isSection =
      child !== null &&
      typeof child === "object" &&
      !Array.isArray(child) &&
      !catalog.has(`${prefix}${key}`);
    (isSection ? sectionKeys : scalarKeys).push(key);
  }

  return (
    <Flex vertical gap={12}>
      {scalarKeys.map((key) => {
        const path = `${prefix}${key}`;
        const field = catalog.get(path);
        return (
          <Flex key={path} align="center" gap={12}>
            <Tooltip title={field?.description}>
              <Typography.Text style={{ width: 280 }} code>
                {key}
              </Typography.Text>
            </Tooltip>
            <FieldControl
              value={values[key]}
              field={field}
              onChange={(next) => onChange(path.split("."), next)}
            />
            <Typography.Text type="secondary" style={{ maxWidth: 380 }}>
              {field?.description}
            </Typography.Text>
          </Flex>
        );
      })}
      {sectionKeys.length > 0 && (
        <Collapse
          size="small"
          items={sectionKeys.map((key) => ({
            key,
            label: key,
            children: (
              <SectionForm
                values={values[key] as Values}
                prefix={`${prefix}${key}.`}
                catalog={catalog}
                onChange={onChange}
              />
            ),
          }))}
        />
      )}
    </Flex>
  );
}

export default function ParametersPanel() {
  const [values, setValues] = useState<Values | null>(null);
  const [catalogEntries, setCatalogEntries] = useState<ParameterField[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);

  const catalog = useMemo(
    () => new Map(catalogEntries.map((entry) => [entry.path, entry])),
    [catalogEntries],
  );

  const load = useCallback(() => {
    fetchParameters()
      .then((body) => {
        setValues(body.values);
        setCatalogEntries(body.catalog);
        setDirty(false);
        setError(null);
      })
      .catch((cause: Error) => setError(cause.message));
  }, []);

  useEffect(load, [load]);

  const onChange = (path: string[], value: unknown) => {
    setValues((current) => (current === null ? current : setDeep(current, path, value)));
    setDirty(true);
  };

  const onSave = () => {
    if (values === null) return;
    setSaving(true);
    saveParameters(values)
      .then((saved) => {
        setValues(saved);
        setDirty(false);
        setError(null);
        message.success("已保存；改动将对下一个入队的 Launch 生效");
      })
      .catch((cause: Error) => setError(cause.message))
      .finally(() => setSaving(false));
  };

  return (
    <Card
      title="Run Parameter Registry（改动对下一个 Launch 生效，运行中的不受影响）"
      extra={
        <Flex gap={8}>
          <Button onClick={load}>重置</Button>
          <Button type="primary" onClick={onSave} loading={saving} disabled={!dirty}>
            保存
          </Button>
        </Flex>
      }
    >
      {error !== null && <Alert type="error" message={error} style={{ marginBottom: 16 }} />}
      {values !== null && (
        <SectionForm values={values} prefix="" catalog={catalog} onChange={onChange} />
      )}
    </Card>
  );
}
