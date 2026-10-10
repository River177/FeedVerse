import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import {
  ArrowDown,
  ArrowUp,
  ArrowUpRight,
  Check,
  ChevronDown,
  ChevronRight,
  Code2,
  Terminal,
  Expand,
  Focus,
  Minus,
  Plus,
  Info,
  X,
} from "lucide-react";
import {
  TOPICS,
  type Creator,
  type Frame,
  type Goal,
  type Metrics,
  type Simulation,
  type World,
} from "./engine";

export function Brand({ small = false }: { small?: boolean }) {
  return (
    <svg
      width={small ? 30 : 38}
      height={small ? 30 : 38}
      viewBox="0 0 40 40"
      aria-hidden="true"
    >
      <rect width="40" height="40" rx="6" fill="#25332f" />
      <path d="M12 29V11h17v4H17v4h10v4H17v6Z" fill="#f7f8f6" />
    </svg>
  );
}
export function Num({
  value,
  suffix = "",
  digits = 1,
}: {
  value: number;
  suffix?: string;
  digits?: number;
}) {
  return (
    <>
      {value.toLocaleString("en-US", {
        minimumFractionDigits: digits,
        maximumFractionDigits: digits,
      })}
      <span className="unit">{suffix}</span>
    </>
  );
}
export function Avatar({
  creator,
  size = 42,
}: {
  creator: Creator;
  size?: number;
}) {
  const topic = TOPICS[creator.topic];
  return (
    <span
      className="avatar"
      style={{
        width: size,
        height: size,
        background: topic.soft,
        color: topic.color,
        fontSize: size * 0.35,
      }}
    >
      <span>{creator.name.slice(0, 1)}</span>
      {creator.isNew && <i />}
    </span>
  );
}
export const METRICS: {
  key: keyof Metrics;
  name: string;
  hint: string;
  unit: string;
  lower?: boolean;
}[] = [
  {
    key: "satisfaction",
    name: "模拟反馈得分",
    hint: "由合成兴趣、内容质量与重复疲劳计算的反馈分数，范围 0–100；不是实测用户满意度。",
    unit: "",
  },
  {
    key: "newcomerShare",
    name: "新作者曝光",
    hint: "本轮实验中，新创作者获得的累计曝光占比。",
    unit: "%",
  },
  {
    key: "diversity",
    name: "内容多样性",
    hint: "用户已看内容的平均归一化类别熵，范围 0–100；越大说明接触的类别越丰富。",
    unit: "",
  },
  {
    key: "concentration",
    name: "曝光集中度",
    hint: "曝光最多的前 10% 创作者占据的曝光份额；越低分配越分散。",
    unit: "%",
    lower: true,
  },
];
export function Sparkline({
  values,
  color = "#8b94b8",
  height = 32,
  fill = false,
  range,
  label = "趋势",
}: {
  values: number[];
  color?: string;
  height?: number;
  fill?: boolean;
  range?: [number, number];
  label?: string;
}) {
  const id = useId().replaceAll(":", "");
  const min = range?.[0] ?? Math.min(...values),
    max = range?.[1] ?? Math.max(...values);
  const path = values
    .map(
      (v, i) =>
        `${i ? "L" : "M"}${((i / Math.max(1, values.length - 1)) * 200).toFixed(2)},${(height - 3 - ((v - min) / (max - min || 1)) * (height - 6)).toFixed(2)}`,
    )
    .join(" ");
  return (
    <svg
      className="sparkline"
      viewBox={`0 0 200 ${height}`}
      preserveAspectRatio="none"
      role="img"
      aria-label={label}
    >
      <defs>
        <linearGradient id={id} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity=".16" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      {fill && values.length > 0 && (
        <path d={`${path} L200,${height} L0,${height}Z`} fill={`url(#${id})`} />
      )}
      <path
        d={path}
        fill="none"
        stroke={color}
        strokeWidth="1.7"
        vectorEffect="non-scaling-stroke"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
export function Delta({
  value,
  lower = false,
  compact = false,
  unit = "pp",
}: {
  value: number;
  lower?: boolean;
  compact?: boolean;
  unit?: string;
}) {
  const good = lower ? value < 0 : value > 0;
  return (
    <span
      className={`delta ${Math.abs(value) < 0.05 ? "neutral" : good ? "positive" : "negative"}`}
    >
      {value >= 0 ? <ArrowUp size={11} /> : <ArrowDown size={11} />}
      {Math.abs(value).toFixed(1)}
      {!compact && <span>{unit}</span>}
    </span>
  );
}

export function WorldMap({
  world,
  frame,
  maxExposure,
  selected,
  onSelect,
  onlyNew,
  playing,
  zoom = 1,
}: {
  world: World;
  frame: Frame;
  maxExposure: number;
  selected: number | null;
  onSelect: (id: number) => void;
  onlyNew: boolean;
  playing: boolean;
  zoom?: number;
}) {
  const [hovered, setHovered] = useState<number | null>(null);
  const focused = hovered === null ? null : world.creators[hovered];
  return (
    <div className={`world-map ${playing ? "is-playing" : ""}`}>
      <svg
        viewBox="0 0 540 355"
        role="group"
        aria-label="创作者曝光分布，点击圆点可比较基线与实验分支"
      >
        <rect width="540" height="355" fill="#fbfcfb" />
        <g
          transform={`translate(${270 * (1 - zoom)} ${177 * (1 - zoom)}) scale(${zoom})`}
        >
          {TOPICS.map((t, i) => (
            <g key={t.name} className="topic-zone">
              <ellipse
                cx={t.x}
                cy={t.y}
                rx="76"
                ry="52"
                fill="none"
                stroke="#e3e7e4"
                strokeDasharray="2 4"
              />
              <text
                x={t.x}
                y={t.y + (i > 2 ? 62 : -53)}
                textAnchor="middle"
                fill="#737e77"
                fontSize="11"
                letterSpacing="1"
              >
                {t.name}
              </text>
            </g>
          ))}
          {[...world.creators]
            .sort((a, b) => frame.exposure[a.id] - frame.exposure[b.id])
            .map((c) => {
              const r =
                3.8 +
                Math.sqrt(frame.exposure[c.id] / Math.max(1, maxExposure)) * 21;
              const topic = TOPICS[c.topic];
              const active = selected === c.id || hovered === c.id;
              const opacity = onlyNew && !c.isNew ? 0.15 : 1;
              return (
                <g
                  key={c.id}
                  className={`creator-node ${active ? "node-active" : ""}`}
                  role="button"
                  tabIndex={0}
                  aria-label={`${c.name}，${c.isNew ? "新创作者，" : ""}${frame.exposure[c.id]} 次曝光`}
                  onClick={() => onSelect(c.id)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      onSelect(c.id);
                    }
                  }}
                  onMouseEnter={() => setHovered(c.id)}
                  onMouseLeave={() => setHovered(null)}
                  onFocus={() => setHovered(c.id)}
                  onBlur={() => setHovered(null)}
                >
                  {active && (
                    <circle
                      cx={c.x}
                      cy={c.y}
                      r={r + 10}
                      fill={topic.color}
                      opacity=".08"
                    />
                  )}
                  {active && (
                    <circle
                      cx={c.x}
                      cy={c.y}
                      r={r + 7}
                      fill="none"
                      stroke={topic.color}
                      opacity=".55"
                      strokeWidth="1"
                      className="selection-outline"
                    />
                  )}
                  {c.isNew && (
                    <circle
                      className="node-ring"
                      cx={c.x}
                      cy={c.y}
                      r={r + 3}
                      fill="none"
                      stroke={topic.color}
                      strokeWidth=".8"
                      opacity={opacity * 0.65}
                    />
                  )}
                  <circle
                    className="node-body"
                    cx={c.x}
                    cy={c.y}
                    r={r}
                    fill={topic.color}
                    opacity={opacity * 0.85}
                    stroke="white"
                    strokeWidth="1.4"
                  />
                  {r > 12 && (
                    <text
                      x={c.x}
                      y={c.y + 3}
                      fontSize={Math.min(12, r * 0.65)}
                      textAnchor="middle"
                      fill="white"
                      pointerEvents="none"
                      opacity={opacity}
                    >
                      {c.name.slice(0, 1)}
                    </text>
                  )}
                  <circle
                    cx={c.x}
                    cy={c.y}
                    r={Math.max(r + 4, 10)}
                    fill="transparent"
                  />
                  {(active || r > 21) && (
                    <text
                      className="creator-label"
                      x={c.x}
                      y={c.y + r + 15}
                      textAnchor="middle"
                      fontSize="10"
                      fill={active ? "#50516b" : "#848899"}
                    >
                      {c.name}
                    </text>
                  )}
                </g>
              );
            })}
        </g>
      </svg>
      {focused && (
        <div className="map-tooltip" role="status">
          <span
            className="color-dot"
            style={{ background: TOPICS[focused.topic].color }}
          />
          <strong>{focused.name}</strong>
          <span>{frame.exposure[focused.id].toLocaleString()} 次曝光</span>
          <span className="tooltip-arrow">
            查看明细 <ArrowUpRight size={12} />
          </span>
        </div>
      )}
    </div>
  );
}

export function WorldPanel({
  world,
  simulation,
  other,
  frame,
  selected,
  onSelect,
  onlyNew,
  playing,
  branch,
  onPolicy,
  onMetric,
  onExpand,
}: {
  world: World;
  simulation: Simulation;
  other: Simulation;
  frame: number;
  selected: number | null;
  onSelect: (id: number) => void;
  onlyNew: boolean;
  playing: boolean;
  branch?: boolean;
  onPolicy: () => void;
  onMetric: (key: keyof Metrics) => void;
  onExpand: () => void;
}) {
  const [zoom, setZoom] = useState(1);
  const current = simulation.frames[frame];
  const max = Math.max(...current.exposure, ...other.frames[frame].exposure, 1);
  return (
    <section
      className={`world-panel ${branch ? "branch-panel" : "baseline-panel"}`}
    >
      <div className="world-panel-heading">
        <div className="world-heading-name">
          <span className={`world-dot ${branch ? "orange" : "blue"}`} />
          <h3>{branch ? "实验 B" : "基线 A"}</h3>
          <span className="world-code">
            {branch ? "rule + rerank" : "rule-baseline"}
          </span>
        </div>
        <button
          className="icon-button subtle"
          title={`展开${branch ? "实验 B" : "基线 A"}`}
          aria-label={`展开${branch ? "实验 B" : "基线 A"}`}
          onClick={onExpand}
        >
          <Expand size={15} />
        </button>
      </div>
      <div className="world-policy-line">
        <span>
          {branch
            ? `探索 ${Math.round(simulation.policy.exploration * 100)}% · 扶持 ${Math.round(simulation.policy.newcomerBoost * 100)}% · 多样性 ${Math.round(simulation.policy.diversity * 100)}%`
            : "规则排序 v0.1"}
        </span>
        {branch ? (
          <button className="policy-link" onClick={onPolicy}>
            调整策略 <ChevronRight size={13} />
          </button>
        ) : (
          <span className="fixed-policy">对照组 · 规则固定</span>
        )}
      </div>
      <WorldMap
        world={world}
        frame={current}
        maxExposure={max}
        selected={selected}
        onSelect={onSelect}
        onlyNew={onlyNew}
        playing={playing}
        zoom={zoom}
      />
      <div className="map-caption">
        <span>
          <span className="tiny-new-ring" />
          外圈代表新创作者
        </span>
        <div className="map-zoom">
          <button
            className="icon-button"
            aria-label={`缩小${branch ? "实验" : "基线"}分布图`}
            disabled={zoom <= 1}
            onClick={() => setZoom((v) => Math.max(1, v - 0.15))}
          >
            <Minus size={12} />
          </button>
          <span>{Math.round(zoom * 100)}%</span>
          <button
            className="icon-button"
            aria-label={`放大${branch ? "实验" : "基线"}分布图`}
            disabled={zoom >= 1.45}
            onClick={() => setZoom((v) => Math.min(1.45, v + 0.15))}
          >
            <Plus size={12} />
          </button>
        </div>
      </div>
      <div className="metric-grid">
        {METRICS.map((metric) => (
          <button
            key={metric.key}
            className="metric"
            onClick={() => onMetric(metric.key)}
            title={metric.hint}
          >
            <span className="metric-name">
              {metric.name}
              <ArrowUpRight size={10} />
            </span>
            <span className="metric-value">
              <Num value={current.metrics[metric.key]} suffix={metric.unit} />
            </span>
            <div className="metric-bottom">
              {branch ? (
                <Delta
                  value={
                    current.metrics[metric.key] -
                    other.frames[frame].metrics[metric.key]
                  }
                  lower={metric.lower}
                  unit={metric.unit ? "pp" : "分"}
                />
              ) : (
                <span className="metric-base-caption">基线观测</span>
              )}
              <span className="metric-mini-chart">
                <Sparkline
                  values={simulation.frames
                    .slice(1, Math.max(2, frame + 1))
                    .map((f) => f.metrics[metric.key])}
                  color={branch ? "#dba075" : "#9aaaca"}
                  height={24}
                />
              </span>
            </div>
          </button>
        ))}
      </div>
    </section>
  );
}

export type ToolEvent = {
  id: number;
  tool: string;
  title: string;
  description: string;
  status: "done" | "running" | "cancelled";
  args: unknown;
  result?: unknown;
  durationMs?: number;
};

export function CreatorComparisonTable({
  world,
  baseline,
  branch,
  frame,
  onSelect,
}: {
  world: World;
  baseline: Simulation;
  branch: Simulation;
  frame: number;
  onSelect: (id: number) => void;
}) {
  const [filter, setFilter] = useState<"all" | "new">("new");
  const [sort, setSort] = useState<"change" | "gain" | "loss">("change");
  const a = baseline.frames[frame],
    b = branch.frames[frame];
  const rows = world.creators
    .filter((c) => filter === "all" || c.isNew)
    .map((c) => ({
      creator: c,
      before: a.exposure[c.id],
      after: b.exposure[c.id],
      change: b.exposure[c.id] - a.exposure[c.id],
      reachChange: b.reach[c.id] - a.reach[c.id],
    }))
    .sort((x, y) =>
      sort === "gain"
        ? y.change - x.change
        : sort === "loss"
          ? x.change - y.change
          : Math.abs(y.change) - Math.abs(x.change),
    );
  return (
    <section className="creator-table-section">
      <div className="table-heading">
        <div>
          <h3>曝光变化明细</h3>
          <span>第 {frame} 轮 · 两组累计曝光</span>
        </div>
        <div className="table-controls">
          <div className="segmented">
            <button
              className={filter === "new" ? "selected" : ""}
              onClick={() => setFilter("new")}
            >
              新创作者
            </button>
            <button
              className={filter === "all" ? "selected" : ""}
              onClick={() => setFilter("all")}
            >
              全部
            </button>
          </div>
          <select
            value={sort}
            onChange={(e) => setSort(e.target.value as typeof sort)}
            aria-label="明细排序"
          >
            <option value="change">按变化幅度</option>
            <option value="gain">按曝光增加</option>
            <option value="loss">按曝光减少</option>
          </select>
        </div>
      </div>
      <div className="table-scroll">
        <table className="creator-table">
          <thead>
            <tr>
              <th>创作者</th>
              <th>类别</th>
              <th>基线 A</th>
              <th>实验 B</th>
              <th>曝光差值</th>
              <th>触达差值</th>
              <th>
                <span className="sr-only">详情</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {rows
              .slice(0, 6)
              .map(({ creator, before, after, change, reachChange }) => (
                <tr key={creator.id}>
                  <td>
                    <button
                      className="table-creator"
                      onClick={() => onSelect(creator.id)}
                    >
                      <Avatar creator={creator} size={25} />
                      <span>
                        {creator.name}
                        <small>
                          C-{String(creator.id + 1).padStart(3, "0")}
                        </small>
                      </span>
                    </button>
                  </td>
                  <td>
                    <span className="table-category">
                      <i style={{ background: TOPICS[creator.topic].color }} />
                      {TOPICS[creator.topic].name}
                    </span>
                  </td>
                  <td>{before.toLocaleString()}</td>
                  <td>{after.toLocaleString()}</td>
                  <td
                    className={
                      change > 0 ? "gain-cell" : change < 0 ? "loss-cell" : ""
                    }
                  >
                    {change > 0 ? "+" : ""}
                    {change.toLocaleString()}
                  </td>
                  <td>
                    {reachChange > 0 ? "+" : ""}
                    {reachChange.toLocaleString()}
                  </td>
                  <td>
                    <button
                      className="icon-button"
                      aria-label={`查看${creator.name}明细`}
                      onClick={() => onSelect(creator.id)}
                    >
                      <ArrowUpRight size={14} />
                    </button>
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>
      <div className="table-footer">
        显示 {Math.min(6, rows.length)} / {rows.length} 位创作者 ·
        触达为独立用户数，重复曝光不重复计数。
      </div>
    </section>
  );
}
export function EventLog({
  events,
  busy,
}: {
  events: ToolEvent[];
  busy: boolean;
}) {
  const [expanded, setExpanded] = useState<number | null>(null);
  const [code, setCode] = useState(false);
  const scroll = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (busy && scroll.current) scroll.current.scrollTop = 0;
  }, [events.length, busy]);
  return (
    <section className="events-panel panel">
      <div className="panel-heading">
        <div>
          <Terminal size={17} />
          <h3>执行记录</h3>
          <span className="muted-badge">本地脚本</span>
        </div>
        <button
          className={`text-button ${code ? "is-active" : ""}`}
          onClick={() => setCode(!code)}
        >
          <Code2 size={14} />
          {code ? "查看过程" : "调用详情"}
        </button>
      </div>
      <div className="event-list" ref={scroll}>
        {[...events].reverse().map((event, index) => (
          <div key={event.id} className={`event-row ${event.status}`}>
            <div className="event-track">
              <span className="event-symbol">
                {event.status === "running" ? (
                  <span className="spinner" />
                ) : event.status === "cancelled" ? (
                  <X size={11} />
                ) : (
                  <Check size={11} />
                )}
              </span>
              {index < events.length - 1 && (
                <span className="event-track-line" />
              )}
            </div>
            <div className="event-content">
              <button
                className="event-toggle"
                onClick={() =>
                  setExpanded((v) => (v === event.id ? null : event.id))
                }
                aria-expanded={expanded === event.id}
              >
                <strong>{event.title}</strong>
                <span>
                  {event.status === "running"
                    ? "执行中"
                    : event.status === "cancelled"
                      ? "已停止"
                      : event.durationMs === undefined
                        ? "已完成"
                        : `${event.durationMs.toFixed(0)} ms`}
                </span>
                <ChevronDown
                  size={13}
                  className={expanded === event.id ? "rotate" : ""}
                />
              </button>
              <p>{event.description}</p>
              <span className="tool-pill">
                {event.tool}
                <span className="tiny-status" />
              </span>
              {(expanded === event.id || code) && (
                <div className="event-code">
                  <span>INPUT</span>
                  <pre>{JSON.stringify(event.args, null, 2)}</pre>
                  <span>OUTPUT</span>
                  <pre>
                    {event.status === "running"
                      ? "等待本地工具返回…"
                      : JSON.stringify(
                          event.result ?? { cancelled: true },
                          null,
                          2,
                        )}
                  </pre>
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
      <div className="panel-footnote">
        <span className="status-dot" />
        本地脚本执行记录；AGH 尚未接入。
      </div>
    </section>
  );
}

export function Dialog({
  title,
  eyebrow,
  children,
  onClose,
  wide = false,
}: {
  title: string;
  eyebrow?: string;
  children: ReactNode;
  onClose: () => void;
  wide?: boolean;
}) {
  const root = useRef<HTMLDivElement>(null);
  const headingId = useId();
  useEffect(() => {
    const previous = document.activeElement as HTMLElement;
    const oldOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    root.current?.focus();
    const keydown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key === "Tab") {
        const nodes = root.current?.querySelectorAll<HTMLElement>(
          'button:not(:disabled), input, select, textarea, [tabindex="0"]',
        );
        if (!nodes?.length) return;
        const first = nodes[0],
          last = nodes[nodes.length - 1];
        if (
          e.shiftKey &&
          (document.activeElement === first ||
            document.activeElement === root.current)
        ) {
          e.preventDefault();
          last.focus();
        } else if (
          !e.shiftKey &&
          (document.activeElement === last ||
            document.activeElement === root.current)
        ) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener("keydown", keydown);
    return () => {
      document.body.style.overflow = oldOverflow;
      document.removeEventListener("keydown", keydown);
      previous?.focus();
    };
  }, [onClose]);
  return (
    <div
      className="dialog-backdrop"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        className={`dialog ${wide ? "wide" : ""}`}
        ref={root}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-labelledby={headingId}
      >
        <div className="dialog-heading">
          <div>
            {eyebrow && <span className="eyebrow">{eyebrow}</span>}
            <h2 id={headingId}>{title}</h2>
          </div>
          <button
            className="icon-button"
            aria-label="关闭弹窗"
            onClick={onClose}
          >
            <X size={20} />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

export function CreatorDetail({
  creator,
  baseline,
  branch,
  frame,
  onClose,
  onNext,
}: {
  creator: Creator;
  baseline: Simulation;
  branch: Simulation;
  frame: number;
  onClose: () => void;
  onNext: () => void;
}) {
  const a = baseline.frames[frame],
    b = branch.frames[frame],
    id = creator.id;
  const first = branch.frames.find((f) => f.exposure[id] > 0)?.tick;
  const topic = TOPICS[creator.topic];
  return (
    <Dialog
      title="创作者对照明细"
      eyebrow={`C-${String(creator.id + 1).padStart(3, "0")} / 第 ${frame} 轮`}
      onClose={onClose}
    >
      <div className="creator-profile">
        <Avatar creator={creator} size={64} />
        <div>
          <h3>
            {creator.name}{" "}
            <span className={creator.isNew ? "new-tag" : "muted-badge"}>
              {creator.isNew ? "新创作者" : "成熟创作者"}
            </span>
          </h3>
          <p>
            {topic.name} · 初始声望 {creator.prior.toFixed(0)} · 合成样本
          </p>
        </div>
      </div>
      <div className="creator-comparison">
        <div>
          <span>
            <i className="world-dot blue" />
            基线 A
          </span>
          <strong>{a.exposure[id].toLocaleString()}</strong>
          <small>次曝光</small>
        </div>
        <span className="creator-arrow">
          <ArrowUpRight size={24} />
        </span>
        <div>
          <span>
            <i className="world-dot orange" />
            实验 B
          </span>
          <strong>{b.exposure[id].toLocaleString()}</strong>
          <small>次曝光</small>
        </div>
      </div>
      <div className="detail-chart">
        <div className="detail-chart-heading">
          <strong>累计曝光轨迹</strong>
          <span>第 0–{frame} 轮</span>
        </div>
        <div className="overlay-charts">
          <Sparkline
            values={baseline.frames
              .slice(0, frame + 1)
              .map((f) => f.exposure[id])}
            color="#7597cb"
            height={100}
            range={[0, Math.max(a.exposure[id], b.exposure[id], 1)]}
            fill
            label="基线 A曝光轨迹"
          />
          <Sparkline
            values={branch.frames
              .slice(0, frame + 1)
              .map((f) => f.exposure[id])}
            color="#d99368"
            height={100}
            range={[0, Math.max(a.exposure[id], b.exposure[id], 1)]}
            label="实验 B曝光轨迹"
          />
        </div>
        <div className="chart-axis">
          <span>实验起点</span>
          <span>现在</span>
        </div>
      </div>
      <div className="creator-detail-metrics">
        <div>
          <span>独立触达用户</span>
          <strong>
            <span className="blue-text">{a.reach[id]}</span>
            <span>→</span>
            <span className="orange-text">{b.reach[id]}</span>
          </strong>
        </div>
        <div>
          <span>累计点击</span>
          <strong>
            <span className="blue-text">{a.clicks[id]}</span>
            <span>→</span>
            <span className="orange-text">{b.clicks[id]}</span>
          </strong>
        </div>
      </div>
      <div className="story-note">
        <Info size={17} />
        <p>
          {first !== undefined && first <= frame ? (
            <>
              第 <strong>{first}</strong> 轮，{creator.name}
              在实验 B获得了第一次曝光。目前被 <strong>
                {b.reach[id]}
              </strong>{" "}
              位独立用户发现。
            </>
          ) : (
            "当前轮次没有曝光记录。继续回放或调整排序配置查看变化。"
          )}
        </p>
      </div>
      <div className="dialog-actions">
        <span>数据来自当前模拟，不代表真实平台。</span>
        <button className="secondary-button" onClick={onNext}>
          <Focus size={14} />
          下一位新作者
        </button>
      </div>
    </Dialog>
  );
}

export function GoalLabel({ goal }: { goal: Goal }) {
  const metric = METRICS.find((m) => m.key === goal.metric)!;
  return (
    <>
      {metric.name} {goal.metric === "concentration" ? "≤" : "≥"} {goal.target}
      {metric.unit || " 分"}
    </>
  );
}
