import {
  Bot,
  Camera,
  Focus,
  ScanLine,
  ShieldCheck,
  Waypoints,
  WifiOff,
  type LucideIcon,
} from "lucide-react";
import { useState } from "react";

import "./EmbodiedIntelligence.css";

type CameraId = "main" | "overhead" | "close" | "wide";

type CameraFeed = {
  id: CameraId;
  code: string;
  label: string;
  caption: string;
  source: string;
};

const CAMERA_FEEDS: CameraFeed[] = [
  { id: "main", code: "C-01", label: "主机位", caption: "样本制备站", source: "/embodied/lab-main.gif" },
  { id: "overhead", code: "C-02", label: "高位总览", caption: "样品转移台", source: "/embodied/lab-overhead.gif" },
  { id: "close", code: "C-03", label: "操作近景", caption: "精密处理单元", source: "/embodied/lab-close.gif" },
  { id: "wide", code: "C-04", label: "环境广角", caption: "工程测试场", source: "/embodied/lab-wide.gif" },
];

const SIMULATION_STATES: Array<{
  label: string;
  value: string;
  icon: LucideIcon;
}> = [
  { label: "影像素材", value: "授权实拍", icon: ScanLine },
  { label: "工作台任务", value: "样品制备", icon: Waypoints },
  { label: "机器人连接", value: "未接入", icon: WifiOff },
];

function CameraScene({ camera, compact = false }: { camera: CameraFeed; compact?: boolean }) {
  return (
    <div
      className={`camera-scene camera-scene--${camera.id} ${compact ? "camera-scene--compact" : ""}`}
      aria-hidden="true"
    >
      <img
        className="camera-scene-media"
        src={camera.source}
        alt=""
        decoding="async"
        loading={compact ? "lazy" : "eager"}
      />
      <span className="camera-scene-vignette" />
    </div>
  );
}

function CameraTile({
  camera,
  isSelected,
  onSelect,
}: {
  camera: CameraFeed;
  isSelected: boolean;
  onSelect: (camera: CameraId) => void;
}) {
  return (
    <button
      type="button"
      className={`embodied-camera-tile ${isSelected ? "is-selected" : ""}`}
      onClick={() => onSelect(camera.id)}
      aria-pressed={isSelected}
      aria-label={`查看${camera.label}：${camera.caption}`}
    >
      <div className="embodied-camera-thumbnail">
        <CameraScene camera={camera} compact />
        <span className="embodied-camera-code">{camera.code}</span>
      </div>
      <span className="embodied-camera-copy">
        <strong>{camera.label}</strong>
        <small>{camera.caption}</small>
      </span>
    </button>
  );
}

export function EmbodiedIntelligence() {
  const [selectedCameraId, setSelectedCameraId] = useState<CameraId>("main");
  const selectedCamera = CAMERA_FEEDS.find((camera) => camera.id === selectedCameraId) ?? CAMERA_FEEDS[0];

  return (
    <section className="embodied-intelligence" aria-labelledby="embodied-title">
      <header className="embodied-intro">
        <div>
          <p className="section-label">EMBODIED INTELLIGENCE / DEMO STATION</p>
          <h1 id="embodied-title">让机器的感知，<br />进入同一块工作台。</h1>
          <p>
            这里以经授权的真实实验室影像预演具身智能的多机位观察界面。
            画面只按演示模式循环播放，不代表当前摄像头或机器人连接。
          </p>
        </div>
        <div className="embodied-demo-badge" aria-label="演示模式，经授权的动态素材">
          <span><i aria-hidden="true" />演示模式</span>
          <small>CURATED FOOTAGE</small>
        </div>
      </header>

      <section className="embodied-monitor" aria-labelledby="monitor-title">
        <header className="embodied-monitor-heading">
          <div>
            <p>实验台 E-01 / 多机位观察</p>
            <h2 id="monitor-title">{selectedCamera.label}</h2>
          </div>
          <span><Focus aria-hidden="true" />动态演示素材</span>
        </header>

        <div className="embodied-main-feed">
          <CameraScene camera={selectedCamera} />
          <div className="embodied-feed-overlay embodied-feed-overlay--top">
            <span>PRESENTATION CLIP</span>
            <span>{selectedCamera.code} / {selectedCamera.caption}</span>
          </div>
          <div className="embodied-feed-overlay embodied-feed-overlay--bottom">
            <span>真实实验室机械臂影像</span>
            <span>非实时摄像头输入</span>
          </div>
          <span className="embodied-focus-mark embodied-focus-mark--top-left" aria-hidden="true" />
          <span className="embodied-focus-mark embodied-focus-mark--bottom-right" aria-hidden="true" />
        </div>

        <dl className="embodied-state-strip" aria-label="演示场景说明">
          {SIMULATION_STATES.map((state) => {
            const StateIcon = state.icon;
            return (
              <div key={state.label}>
                <dt><StateIcon aria-hidden="true" />{state.label}</dt>
                <dd>{state.value}</dd>
              </div>
            );
          })}
        </dl>
      </section>

      <section className="embodied-camera-deck" aria-labelledby="camera-deck-title">
        <header className="embodied-section-heading">
          <div>
            <p className="section-label">CAMERA ARRAY / BROWSE ONLY</p>
            <h2 id="camera-deck-title">从真实的工作单元，<br />看到机器如何行动。</h2>
          </div>
          <span><Camera aria-hidden="true" />四路动态素材</span>
        </header>
        <div className="embodied-camera-grid">
          {CAMERA_FEEDS.map((camera) => (
            <CameraTile
              key={camera.id}
              camera={camera}
              isSelected={camera.id === selectedCameraId}
              onSelect={setSelectedCameraId}
            />
          ))}
        </div>
      </section>

      <section className="embodied-briefing" aria-labelledby="briefing-title">
        <div className="embodied-briefing-copy">
          <p className="section-label">LAB SCENE / PRESENTATION ONLY</p>
          <h2 id="briefing-title">从材料制备到<br />工程测试的真实片段。</h2>
          <p>
            当前素材来自自主材料实验室与工程测试场的真实机械臂操作记录。
            后续可以在不改变工作台结构的前提下，替换为来自现场摄像头的实时画面。
          </p>
        </div>
        <ol className="embodied-task-path">
          <li>
            <span>01</span>
            <div><strong>工位总览</strong><small>高位机位呈现实验设备与机械臂</small></div>
          </li>
          <li className="is-active">
            <span>02</span>
            <div><strong>样品处理</strong><small>近景呈现机械臂在样品台的操作</small></div>
          </li>
          <li>
            <span>03</span>
            <div><strong>工程测试</strong><small>环境广角保留测试场的尺度感</small></div>
          </li>
        </ol>
      </section>

      <aside className="embodied-disclosure">
        <ShieldCheck aria-hidden="true" />
        <div>
          <strong>展示边界已明确</strong>
          <p>本模块不会连接机器人、摄像头、任务控制或任何实验数据。</p>
          <p>影像：Nathan J. Szymanski 等，CC BY 4.0，经裁切与循环处理；NASA/JPL 素材仅用于演示。</p>
        </div>
        <Bot aria-hidden="true" />
      </aside>
    </section>
  );
}
