import { useCallback, useEffect, useState } from "react";
import { Alert, Card, Col, Row, Select, Tree } from "antd";
import type { DataNode } from "antd/es/tree";
import ArtifactViewer from "./ArtifactViewer";
import {
  fetchArtifactTree,
  fetchLaunches,
  type ArtifactNode,
  type LaunchSummary,
} from "./api";

function toTreeData(nodes: ArtifactNode[]): DataNode[] {
  return nodes.map((node) => ({
    key: node.path,
    title: node.name,
    isLeaf: node.kind === "file",
    children: node.children === undefined ? undefined : toTreeData(node.children),
  }));
}

export default function ArtifactExplorer() {
  const [launches, setLaunches] = useState<LaunchSummary[]>([]);
  const [launchId, setLaunchId] = useState<string | null>(null);
  const [tree, setTree] = useState<DataNode[]>([]);
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchLaunches().then(setLaunches).catch((cause: Error) => setError(cause.message));
  }, []);

  const loadTree = useCallback((launch: string) => {
    fetchArtifactTree(launch)
      .then((nodes) => setTree(toTreeData(nodes)))
      .catch((cause: Error) => setError(cause.message));
  }, []);

  const onSelectLaunch = (launch: string) => {
    setLaunchId(launch);
    setSelectedPath(null);
    loadTree(launch);
  };

  return (
    <Card
      title="Artifact Explorer"
      extra={
        <Select
          style={{ width: 420 }}
          placeholder="选择 Launch"
          options={launches.map((launch) => ({ value: launch.id, label: launch.id }))}
          value={launchId}
          onChange={onSelectLaunch}
          showSearch
        />
      }
    >
      {error !== null && <Alert type="error" message={error} style={{ marginBottom: 16 }} />}
      <Row gutter={16}>
        <Col span={8} style={{ maxHeight: "75vh", overflow: "auto" }}>
          <Tree
            treeData={tree}
            onSelect={(keys) => {
              const key = keys[0];
              if (typeof key === "string") setSelectedPath(key);
            }}
          />
        </Col>
        <Col span={16}>
          {launchId !== null && <ArtifactViewer launchId={launchId} path={selectedPath} />}
        </Col>
      </Row>
    </Card>
  );
}
