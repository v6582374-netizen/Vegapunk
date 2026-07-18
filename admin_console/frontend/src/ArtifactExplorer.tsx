import { useCallback, useEffect, useState } from "react";
import { Alert, Card, Col, Row, Select, Tabs, Tree } from "antd";
import type { DataNode } from "antd/es/tree";
import ArtifactViewer from "./ArtifactViewer";
import ExperimentRunPanel from "./ExperimentRunPanel";
import LaunchTimelinePanel from "./LaunchTimeline";
import {
  fetchArtifactTree,
  fetchExperimentRun,
  fetchLaunchTimeline,
  fetchLaunches,
  type ArtifactNode,
  type ExperimentRunDetail,
  type LaunchSummary,
  type LaunchTimeline,
  type TimelineRun,
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
  const [timeline, setTimeline] = useState<LaunchTimeline | null>(null);
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [runDetail, setRunDetail] = useState<ExperimentRunDetail | null>(null);
  const [leftTab, setLeftTab] = useState("timeline");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchLaunches().then(setLaunches).catch((cause: Error) => setError(cause.message));
  }, []);

  const loadLaunch = useCallback((launch: string) => {
    setError(null);
    fetchArtifactTree(launch)
      .then((nodes) => setTree(toTreeData(nodes)))
      .catch((cause: Error) => setError(cause.message));
    fetchLaunchTimeline(launch)
      .then(setTimeline)
      .catch((cause: Error) => setError(cause.message));
  }, []);

  const onSelectLaunch = (launch: string) => {
    setLaunchId(launch);
    setSelectedPath(null);
    setRunDetail(null);
    loadLaunch(launch);
  };

  const openArtifact = (path: string) => {
    setSelectedPath(path);
    setLeftTab("tree");
  };

  const openRun = (run: TimelineRun) => {
    if (launchId === null) return;
    setError(null);
    fetchExperimentRun(launchId, run.path)
      .then((detail) => {
        setRunDetail(detail);
        if (detail.metrics_path !== null) {
          setSelectedPath(detail.metrics_path);
        } else if (detail.log_path !== null) {
          setSelectedPath(detail.log_path);
        } else if (detail.traceback_path !== null) {
          setSelectedPath(detail.traceback_path);
        }
      })
      .catch((cause: Error) => setError(cause.message));
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
          <Tabs
            activeKey={leftTab}
            onChange={setLeftTab}
            items={[
              {
                key: "timeline",
                label: "时间线",
                children: (
                  <LaunchTimelinePanel
                    timeline={timeline}
                    onOpenArtifact={openArtifact}
                    onOpenRun={openRun}
                  />
                ),
              },
              {
                key: "tree",
                label: "文件树",
                children: (
                  <Tree
                    treeData={tree}
                    onSelect={(keys) => {
                      const key = keys[0];
                      if (typeof key === "string") setSelectedPath(key);
                    }}
                    selectedKeys={selectedPath === null ? [] : [selectedPath]}
                  />
                ),
              },
            ]}
          />
        </Col>
        <Col span={16} style={{ maxHeight: "75vh", overflow: "auto" }}>
          {runDetail !== null && (
            <div style={{ marginBottom: 16 }}>
              <ExperimentRunPanel detail={runDetail} onOpenArtifact={openArtifact} />
            </div>
          )}
          {launchId !== null && <ArtifactViewer launchId={launchId} path={selectedPath} />}
        </Col>
      </Row>
    </Card>
  );
}
