import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowDown,
  ArrowRight,
  ArrowUpRight,
  AudioLines,
  BookOpen,
  Check,
  CheckCheck,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  CircleHelp,
  Command,
  Download,
  FlaskConical,
  GitBranch,
  Globe2,
  History,
  Info,
  Layers3,
  LoaderCircle,
  Pause,
  Play,
  RefreshCw,
  Search,
  Settings2,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Square,
  Target,
  Users,
  WandSparkles,
  X,
} from "lucide-react";
import {
  BASELINE_POLICY,
  compareWorlds,
  createWorld,
  DEFAULT_POLICY,
  DEFAULT_SETTINGS,
  ENGINE_VERSION,
  forkWorld,
  GOALS,
  simulate,
  TOOL_DEFINITIONS,
  TOPICS,
  type Goal,
  type Metrics,
  type Policy,
  type Settings,
  type Simulation,
  type World,
} from "./engine";
import {
  Avatar,
  Brand,
  CreatorDetail,
  Delta,
  Dialog,
  EventLog,
  GoalLabel,
  METRICS,
  Num,
  Sparkline,
  WorldMap,
  WorldPanel,
  type ToolEvent,
} from "./components";

type Experiment = {
  world: World;
  baseline: Simulation;
  branch: Simulation;
  policy: Policy;
};
type SavedRun = {
  id: string;
  title: string;
  settings: Settings;
  policy: Policy;
  goal: Goal;
  time: string;
  metrics: Metrics;
  passed: boolean;
};
type Modal =
  | "settings"
  | "help"
  | "history"
  | "creators"
  | "creator"
  | "metric"
  | "baseline"
  | "branch"
  | null;
type Validation = {
  seed: number;
  passed: boolean;
  delta: number;
  value: number;
};
const storageKey = "feedverse-prototype-v1";
const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));
const percent = (n: number) => Math.round(n * 100);

function buildExperiment(settings: Settings, policy: Policy): Experiment {
  const world = createWorld(settings);
  return {
    world,
    baseline: simulate(world, BASELINE_POLICY),
    branch: simulate(forkWorld(world), policy),
    policy: { ...policy },
  };
}
function loadSaved(): { settings: Settings; policy: Policy; goal: Goal } {
  try {
    const data = JSON.parse(localStorage.getItem(storageKey) || "null");
    if (data && GOALS.some((g) => g.id === data.goal?.id)) {
      const world = createWorld(data.settings);
      simulate(world, data.policy);
      if (
        !Number.isFinite(data.goal.target) ||
        !Number.isFinite(data.goal.tolerance)
      )
        throw Error();
      return data;
    }
  } catch {
    /* A corrupt local draft should not prevent the page from opening. */
  }
  return { settings: DEFAULT_SETTINGS, policy: DEFAULT_POLICY, goal: GOALS[0] };
}

function initialEvents(exp: Experiment): ToolEvent[] {
  return [
    {
      id: 1,
      tool: "create_world",
      title: "一个世界，两种可能",
      description: `已建立 ${exp.world.settings.users} 位用户、${exp.world.settings.creators} 位创作者的本地世界。`,
      status: "done",
      args: exp.world.settings,
      result: { world_id: exp.world.id, engine: ENGINE_VERSION },
    },
    {
      id: 2,
      tool: "fork_world",
      title: "从同一起点，分出另一条路",
      description: "用户、内容、随机事件保持一致，为推荐规则创建对照分支。",
      status: "done",
      args: { world_id: exp.world.id },
      result: {
        branch_id: exp.branch.worldId,
        shared_seed: exp.world.settings.seed,
      },
    },
    {
      id: 3,
      tool: "simulate",
      title: "两个世界已准备好，开始观察吧",
      description: `已计算 ${exp.world.settings.rounds} 轮轨迹。拖动时间轴，或点击一位创作者。`,
      status: "done",
      args: { rounds: exp.world.settings.rounds, policy: exp.policy },
      result: exp.branch.frames.at(-1)!.metrics,
      durationMs: exp.branch.durationMs + exp.baseline.durationMs,
    },
  ];
}

export default function App() {
  const initial = useMemo(() => {
    const saved = loadSaved();
    return {
      ...saved,
      experiment: buildExperiment(saved.settings, saved.policy),
    };
  }, []);
  const [experiment, setExperiment] = useState(initial.experiment);
  const [goal, setGoal] = useState<Goal>(initial.goal);
  const [frame, setFrame] = useState(36);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [onlyNew, setOnlyNew] = useState(false);
  const [selected, setSelected] = useState<number | null>(53);
  const [modal, setModal] = useState<Modal>(null);
  const [metric, setMetric] = useState<keyof Metrics>("newcomerShare");
  const [events, setEvents] = useState<ToolEvent[]>(() =>
    initialEvents(initial.experiment),
  );
  const [busy, setBusy] = useState(false);
  const [stage, setStage] = useState("");
  const [explored, setExplored] = useState(false);
  const [validation, setValidation] = useState<Validation | null>(null);
  const [history, setHistory] = useState<SavedRun[]>([]);
  const [draft, setDraft] = useState({
    settings: initial.settings,
    policy: initial.policy,
    goal: initial.goal,
  });
  const [draftError, setDraftError] = useState("");
  const [creatorSearch, setCreatorSearch] = useState("");
  const [toast, setToast] = useState("");
  const [showAllTopics, setShowAllTopics] = useState(true);
  const operation = useRef(0);
  const eventId = useRef(4);
  const { world, baseline, branch, policy } = experiment;
  const settings = world.settings;
  const tick = Math.min(frame, settings.rounds);
  const comparison = compareWorlds(baseline, branch, tick, goal);
  const fullComparison = compareWorlds(baseline, branch, settings.rounds, goal);
  const featured =
    world.creators[selected ?? 53] ?? world.creators[world.creators.length - 1];
  const closeModal = useCallback(() => setModal(null), []);
  const notice = useCallback((text: string) => setToast(text), []);

  useEffect(() => {
    localStorage.setItem(
      storageKey,
      JSON.stringify({ settings, policy, goal }),
    );
  }, [settings, policy, goal]);
  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => setToast(""), 4000);
    return () => clearTimeout(timer);
  }, [toast]);
  useEffect(() => {
    if (!playing) return;
    const timer = setInterval(
      () =>
        setFrame((current) => {
          if (current >= settings.rounds) {
            setPlaying(false);
            return current;
          }
          return current + 1;
        }),
      530 / speed,
    );
    return () => clearInterval(timer);
  }, [playing, speed, settings.rounds]);
  useEffect(() => {
    const keydown = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      if (
        ["INPUT", "TEXTAREA", "SELECT", "BUTTON"].includes(target.tagName) ||
        target.closest('[role="button"]') ||
        modal ||
        busy
      )
        return;
      if (e.code === "Space") {
        e.preventDefault();
        if (tick === settings.rounds) setFrame(0);
        setPlaying((v) => !v);
      }
      if (e.key === "?") {
        setPlaying(false);
        setModal("help");
      }
    };
    document.addEventListener("keydown", keydown);
    return () => document.removeEventListener("keydown", keydown);
  }, [modal, busy, tick, settings.rounds]);
  useEffect(
    () => () => {
      operation.current++;
    },
    [],
  );

  function openModal(next: Modal) {
    if (busy && next === "settings") {
      notice("请先停止探索，再调整实验参数。");
      return;
    }
    setPlaying(false);
    if (next === "settings") {
      setDraft({
        settings: { ...settings },
        policy: { ...policy },
        goal: { ...goal },
      });
      setDraftError("");
    }
    setModal(next);
  }
  function selectCreator(id: number) {
    setSelected(id);
    setPlaying(false);
    setModal("creator");
  }
  function addEvent(
    tool: string,
    title: string,
    description: string,
    args: unknown,
    result: unknown,
    ms: number,
  ) {
    setEvents((v) => [
      ...v,
      {
        id: eventId.current++,
        tool,
        title,
        description,
        status: "done",
        args,
        result,
        durationMs: ms,
      },
    ]);
  }
  function saveHistory(exp: Experiment, label: string, runGoal: Goal = goal) {
    const passed = compareWorlds(
      exp.baseline,
      exp.branch,
      exp.world.settings.rounds,
      runGoal,
    ).passed;
    setHistory((v) =>
      [
        {
          id: crypto.randomUUID(),
          title: label,
          settings: { ...exp.world.settings },
          policy: { ...exp.policy },
          goal: { ...runGoal },
          time: new Date().toLocaleTimeString("zh-CN", {
            hour: "2-digit",
            minute: "2-digit",
          }),
          metrics: exp.branch.frames.at(-1)!.metrics,
          passed,
        },
        ...v,
      ].slice(0, 20),
    );
  }
  function stopExploration() {
    operation.current++;
    setBusy(false);
    setStage("");
    setEvents((v) =>
      v.map((e) =>
        e.status === "running" ? { ...e, status: "cancelled" } : e,
      ),
    );
    notice("探索已停止，已完成的本地结果已保留。");
  }

  async function explore() {
    if (busy) return;
    const token = ++operation.current;
    setBusy(true);
    setPlaying(false);
    setValidation(null);
    setExplored(false);
    setFrame(0);
    setStage("观察现状");
    const call = async <T,>(
      tool: string,
      title: string,
      description: string,
      args: unknown,
      fn: () => T,
      preview: (data: T) => unknown = (data) => data,
    ): Promise<T> => {
      if (token !== operation.current) throw Error("cancelled");
      const id = eventId.current++;
      setEvents((v) => [
        ...v,
        { id, tool, title, description, status: "running", args },
      ]);
      await sleep(650);
      if (token !== operation.current) throw Error("cancelled");
      const start = performance.now();
      const result = fn();
      const ms = performance.now() - start;
      setEvents((v) =>
        v.map((e) =>
          e.id === id
            ? { ...e, status: "done", result: preview(result), durationMs: ms }
            : e,
        ),
      );
      return result;
    };
    try {
      await call(
        "inspect_world",
        "先看看，机会流向了哪里",
        "读取基线的曝光分布和用户反馈，确认目标对应的指标。",
        { world_id: world.id, goal: goal.id, user_note: goal.prompt },
        () => baseline.frames.at(-1)!.metrics,
      );
      setStage("创建实验分支");
      const twin = await call(
        "fork_world",
        "保留起点，只改变规则",
        "从同一世界创建实验分支，让两组结果可直接比较。",
        { world_id: world.id, seed: settings.seed },
        () => forkWorld(world),
        (w) => ({ world_id: w.id, seed: w.settings.seed }),
      );
      setStage("尝试更大胆的探索");
      const firstPolicy = {
        exploration: 0.35,
        newcomerBoost: 0.08,
        diversity: 0.1,
      };
      await call(
        "set_policy",
        "第一种方案：多给一些探索机会",
        "演示控制器先尝试较高的探索比例，观察它的收益与代价。",
        firstPolicy,
        () => ({ policy: firstPolicy, applied_to: twin.id }),
      );
      const first = await call(
        "simulate",
        `让世界向前运行 ${settings.rounds} 轮`,
        "计算真实模拟轨迹，观察新作者曝光与满意度的变化。",
        { world_id: twin.id, rounds: settings.rounds },
        () => simulate(twin, firstPolicy),
        (data) => ({
          rounds: data.frames.length - 1,
          ...data.frames.at(-1)!.metrics,
        }),
      );
      setExperiment({ world, baseline, branch: first, policy: firstPolicy });
      setFrame(settings.rounds);
      const firstResult = await call(
        "compare_worlds",
        "机会增加了吗？代价是什么？",
        "用事先设置的两个约束检查结果。未达标的方案也保留记录。",
        {
          metric: goal.metric,
          target: goal.target,
          satisfaction_drop_limit: goal.tolerance,
        },
        () => compareWorlds(baseline, first, settings.rounds, goal),
      );
      saveHistory(
        { world, baseline, branch: first, policy: firstPolicy },
        "探索方案 A",
      );
      setStage("调整推荐策略");
      const secondPolicy =
        goal.id === "balance"
          ? { exploration: 0.1, newcomerBoost: 0.3, diversity: 0.18 }
          : goal.id === "diversity"
            ? { exploration: 0.08, newcomerBoost: 0.08, diversity: 0.15 }
            : { ...DEFAULT_POLICY };
      await call(
        "set_policy",
        firstResult.passed
          ? "再试一个更克制的方案"
          : "调整：降低探索，定向扶持",
        firstResult.passed
          ? "在满足约束的基础上比较另一种参数组合。"
          : "降低随机探索，用逐渐衰减的扶持权重帮助新作者进入推荐。",
        secondPolicy,
        () => ({
          policy: secondPolicy,
          based_on: firstResult.passed
            ? "compare_alternative"
            : "constraints_not_met",
        }),
      );
      const second = await call(
        "simulate",
        "重新运行相同的世界",
        "用户和内容保持相同，重新计算另一组推荐规则。",
        { seed: settings.seed, rounds: settings.rounds },
        () => simulate(twin, secondPolicy),
        (data) => ({
          rounds: data.frames.length - 1,
          ...data.frames.at(-1)!.metrics,
        }),
      );
      const secondResult = await call(
        "compare_worlds",
        "核对目标，记录结果",
        "分别判断曝光目标与满意度约束，不将单项改善视为全部达标。",
        {
          metric: goal.metric,
          target: goal.target,
          satisfaction_drop_limit: goal.tolerance,
        },
        () => compareWorlds(baseline, second, settings.rounds, goal),
      );
      const final =
        secondResult.passed || !firstResult.passed
          ? { world, baseline, branch: second, policy: secondPolicy }
          : { world, baseline, branch: first, policy: firstPolicy };
      setExperiment(final);
      setFrame(settings.rounds);
      saveHistory(final, "探索方案 B");
      setStage("换一个种子，再验证一次");
      const seed = settings.seed + 37 > 999999 ? 37 : settings.seed + 37;
      const check = await call(
        "simulate + compare_worlds",
        "换一个起点，结果还成立吗？",
        "在另一个随机世界复验同一策略；这只是一次复验，不代表统计显著。",
        { seed, policy: final.policy, goal: goal.id },
        () => {
          const rep = buildExperiment({ ...settings, seed }, final.policy);
          const verdict = compareWorlds(
            rep.baseline,
            rep.branch,
            settings.rounds,
            goal,
          );
          return {
            seed,
            passed: verdict.passed,
            delta: verdict.delta.satisfaction,
            value: rep.branch.frames.at(-1)!.metrics[goal.metric],
          };
        },
      );
      setValidation(check);
      setExplored(true);
      notice("演示探索完成。所有指标均来自本地计算，可展开工具记录核验。");
    } catch (error) {
      if (token === operation.current)
        notice(error instanceof Error ? error.message : "探索出现问题");
    } finally {
      if (token === operation.current) {
        setBusy(false);
        setStage("");
      }
    }
  }

  function applySettings() {
    try {
      if (
        !Number.isFinite(draft.goal.target) ||
        draft.goal.target < 1 ||
        draft.goal.target > 100
      )
        throw Error("指标目标需在 1–100 之间");
      const next = buildExperiment(draft.settings, draft.policy);
      setExperiment(next);
      setGoal(draft.goal);
      setExplored(false);
      setFrame(Math.min(tick || 36, draft.settings.rounds));
      setValidation(null);
      if ((selected ?? 0) >= draft.settings.creators) setSelected(null);
      addEvent(
        "set_policy + simulate",
        "手动调整，重新计算",
        "已按新的世界设置和策略参数重新计算两个对照世界。",
        { settings: draft.settings, policy: draft.policy },
        next.branch.frames.at(-1)!.metrics,
        next.branch.durationMs + next.baseline.durationMs,
      );
      saveHistory(next, "手动实验", draft.goal);
      setModal(null);
      notice("设置已应用，两个世界已重新计算。");
    } catch (error) {
      setDraftError(error instanceof Error ? error.message : "设置不合法");
    }
  }

  function exportRun() {
    const payload = {
      product: "FeedVerse",
      engine: ENGINE_VERSION,
      exportedAt: new Date().toISOString(),
      settings,
      policy,
      goal,
      frame: tick,
      mode: "local-simulation-scripted-controller",
      validation,
      creators: world.creators,
      baseline: baseline.frames,
      intervention: branch.frames,
      events,
    };
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(payload, null, 2)], {
        type: "application/json",
      }),
    );
    const a = document.createElement("a");
    a.href = url;
    a.download = `feedverse-seed-${settings.seed}.json`;
    a.click();
    URL.revokeObjectURL(url);
    notice("已导出实验快照：参数、轨迹、工具记录和复验结果。");
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <button
          className="brand-button"
          title="FeedVerse 实验室"
          onClick={() => {
            setModal(null);
            window.scrollTo({ top: 0, behavior: "smooth" });
          }}
        >
          <Brand />
        </button>
        <div className="sidebar-divider" />
        <nav aria-label="主导航">
          <button
            className={`nav-icon ${!["history", "creators"].includes(modal ?? "") ? "active" : ""}`}
            aria-label="实验室"
            title="实验室"
            onClick={() => setModal(null)}
          >
            <FlaskConical size={21} />
            <span>实验室</span>
          </button>
          <button
            className={`nav-icon ${modal === "history" ? "active" : ""}`}
            aria-label="实验档案"
            title="实验档案"
            onClick={() => openModal("history")}
          >
            <History size={21} />
            <span>实验档案</span>
          </button>
          <button
            className={`nav-icon ${modal === "creators" ? "active" : ""}`}
            aria-label="创作者"
            title="创作者"
            onClick={() => openModal("creators")}
          >
            <Users size={21} />
            <span>创作者</span>
          </button>
        </nav>
        <div className="sidebar-bottom">
          <button
            className="nav-icon"
            aria-label="使用指南"
            title="使用指南"
            onClick={() => openModal("help")}
          >
            <CircleHelp size={20} />
          </button>
          <div className="profile-dot">
            F<span />
          </div>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div className="brand-wordmark">
            FeedVerse<span>LAB</span>
          </div>
          <div className="header-divider" />
          <div className="breadcrumb">
            工作空间 <ChevronRight size={12} />
            <span>推荐平行世界</span>
          </div>
          <div className="topbar-actions">
            <button
              className="icon-button mobile-only"
              aria-label="实验档案"
              title="实验档案"
              onClick={() => openModal("history")}
            >
              <History size={17} />
            </button>
            <button
              className="icon-button mobile-only"
              aria-label="创作者"
              title="创作者"
              onClick={() => openModal("creators")}
            >
              <Users size={17} />
            </button>
            <span className="local-status">
              <span className="status-dot" />
              本地模拟引擎
            </span>
            <button className="header-button" onClick={exportRun}>
              <Download size={14} />
              <span>导出实验</span>
            </button>
            <button
              className="icon-button help-button"
              aria-label="帮助"
              onClick={() => openModal("help")}
            >
              <CircleHelp size={18} />
            </button>
          </div>
        </header>
        <main>
          <div className="page-heading">
            <div>
              <div className="eyebrow">
                <span className="eyebrow-line" />
                RECOMMENDATION OBSERVATORY
              </div>
              <h1>
                改变规则，看见另一种可能<span className="heading-dot">.</span>
              </h1>
              <p>同一个世界，不同的推荐。探索好内容如何被看见。</p>
            </div>
            <button
              className="secondary-button setup-button"
              disabled={busy}
              onClick={() => openModal("settings")}
            >
              <SlidersHorizontal size={15} />
              实验设置
            </button>
          </div>

          <section className="goal-panel">
            <div className="goal-icon">
              <Sparkles size={22} />
            </div>
            <div className="goal-content">
              <label htmlFor="goal-input">
                给这个世界一个目标
                <span className="goal-label-en">YOUR NEXT WHAT IF</span>
              </label>
              <div className="goal-input-row">
                <input
                  id="goal-input"
                  value={goal.prompt}
                  maxLength={180}
                  disabled={busy}
                  onChange={(e) =>
                    setGoal((g) => ({ ...g, prompt: e.target.value }))
                  }
                  aria-describedby="goal-disclaimer"
                  placeholder="你想让这个推荐世界变得怎样？"
                />
                {busy ? (
                  <button
                    className="primary-button busy-button"
                    onClick={stopExploration}
                  >
                    <LoaderCircle size={16} className="spin" />
                    <span>{stage}</span>
                    <Square size={12} />
                  </button>
                ) : (
                  <button className="primary-button" onClick={explore}>
                    <WandSparkles size={16} />
                    <span>开始探索</span>
                    <ArrowRight size={15} />
                  </button>
                )}
              </div>
              <div className="goal-bottom">
                <div className="goal-presets">
                  {GOALS.map((g) => (
                    <button
                      key={g.id}
                      className={`goal-chip ${goal.id === g.id ? "selected" : ""}`}
                      disabled={busy}
                      onClick={() => {
                        setGoal({ ...g });
                        setValidation(null);
                        setExplored(false);
                      }}
                    >
                      <span>
                        {g.id === "newcomers" ? (
                          <Sparkles size={11} />
                        ) : g.id === "diversity" ? (
                          <Layers3 size={11} />
                        ) : (
                          <AudioLines size={11} />
                        )}
                      </span>
                      {g.label}
                    </button>
                  ))}
                </div>
                <span id="goal-disclaimer" className="demo-note">
                  <Info size={12} />
                  预设流程演示 · 无模型调用
                </span>
              </div>
            </div>
          </section>

          <div className="worlds-section-heading">
            <div className="section-title">
              <h2>两个世界，一次对照</h2>
              <span className="shared-badge">
                <GitBranch size={11} />
                同源分叉
              </span>
            </div>
            <div className="world-controls">
              <span className="world-counts">
                {settings.users} 位用户<span>·</span>
                {settings.creators} 位创作者<span>·</span>Seed {settings.seed}
              </span>
              <label className="switch-label">
                <input
                  type="checkbox"
                  checked={onlyNew}
                  onChange={(e) => setOnlyNew(e.target.checked)}
                />
                <span className="switch-track" />
                聚焦新作者
              </label>
            </div>
          </div>
          <div className="world-grid">
            <WorldPanel
              world={world}
              simulation={baseline}
              other={branch}
              frame={tick}
              selected={selected}
              onSelect={selectCreator}
              onlyNew={onlyNew}
              playing={playing}
              onPolicy={() => openModal("settings")}
              onMetric={(k) => {
                setMetric(k);
                openModal("metric");
              }}
              onExpand={() => openModal("baseline")}
            />
            <div className="world-connection">
              <GitBranch size={13} />
            </div>
            <WorldPanel
              world={{ ...world, id: branch.worldId }}
              simulation={branch}
              other={baseline}
              frame={tick}
              selected={selected}
              onSelect={selectCreator}
              onlyNew={onlyNew}
              playing={playing}
              branch
              onPolicy={() => openModal("settings")}
              onMetric={(k) => {
                setMetric(k);
                openModal("metric");
              }}
              onExpand={() => openModal("branch")}
            />
          </div>
          <div className="legend-row">
            <button
              className="legend-label"
              onClick={() => setShowAllTopics(!showAllTopics)}
            >
              内容宇宙{" "}
              <ChevronDown
                size={12}
                className={!showAllTopics ? "rotate" : ""}
              />
            </button>
            {showAllTopics &&
              TOPICS.map((t) => (
                <span key={t.name} className="topic-legend">
                  <i style={{ background: t.color }} />
                  {t.name}
                </span>
              ))}
            <span className="legend-explanation">
              圆点面积随累计曝光变化 · 点击创作者探索
            </span>
          </div>

          <section className="timeline-panel">
            <div className="playback-buttons">
              <button
                className={`play-button ${playing ? "playing" : ""}`}
                disabled={busy}
                aria-label={playing ? "暂停回放" : "播放回放"}
                onClick={() => {
                  if (tick === settings.rounds) setFrame(0);
                  setPlaying(!playing);
                }}
              >
                {playing ? (
                  <Pause size={16} fill="currentColor" />
                ) : (
                  <Play size={16} fill="currentColor" />
                )}
              </button>
              <button
                className="icon-button"
                disabled={busy || tick === 0}
                aria-label="上一轮"
                onClick={() => {
                  setPlaying(false);
                  setFrame((v) => Math.max(0, v - 1));
                }}
              >
                <ChevronLeft size={16} />
              </button>
              <button
                className="icon-button"
                disabled={busy || tick === settings.rounds}
                aria-label="下一轮"
                onClick={() => {
                  setPlaying(false);
                  setFrame((v) => Math.min(settings.rounds, v + 1));
                }}
              >
                <ChevronRight size={16} />
              </button>
            </div>
            <div className="timeline-position">
              <strong>{String(tick).padStart(2, "0")}</strong>
              <span>/ {settings.rounds} 轮</span>
            </div>
            <div className="timeline-slider">
              <input
                type="range"
                min={0}
                max={settings.rounds}
                value={tick}
                disabled={busy}
                aria-label="模拟时间轴"
                style={
                  {
                    "--progress": `${(tick / settings.rounds) * 100}%`,
                  } as React.CSSProperties
                }
                onChange={(e) => {
                  setPlaying(false);
                  setFrame(Number(e.target.value));
                }}
              />
              <div className="timeline-ticks">
                <span>起点</span>
                <span>{Math.round(settings.rounds * 0.25)}</span>
                <span>{Math.round(settings.rounds * 0.5)}</span>
                <span>{Math.round(settings.rounds * 0.75)}</span>
                <span>{settings.rounds}</span>
              </div>
            </div>
            <div className="playback-speed">
              {[1, 2, 4].map((n) => (
                <button
                  key={n}
                  className={speed === n ? "selected" : ""}
                  onClick={() => setSpeed(n)}
                  aria-label={`${n}倍速`}
                >
                  {n}×
                </button>
              ))}
            </div>
            <button
              className="reset-button"
              disabled={busy}
              title="回到实验起点"
              onClick={() => {
                setPlaying(false);
                setFrame(0);
                notice("已回到实验起点，点击播放即可重新观察。");
              }}
            >
              <RefreshCw size={14} />
            </button>
          </section>

          <div className="spotlight-strip">
            <div className="spotlight-copy">
              <span className="spotlight-star">
                <Sparkles size={15} />
              </span>
              <strong>宏观的变化，微小的命运。</strong>
              <span>看看一位创作者在两个世界里的不同经历。</span>
            </div>
            <button onClick={() => selectCreator(featured.id)}>
              <Avatar creator={featured} size={25} />
              <span>追踪「{featured.name}」</span>
              <ArrowUpRight size={14} />
            </button>
          </div>

          <div className="results-grid">
            <EventLog events={events} busy={busy} />
            <section className="outcome-panel panel">
              <div className="panel-heading">
                <div>
                  <Target size={17} />
                  <h3>这次改变，值得吗？</h3>
                </div>
                <span className="muted-badge">
                  {tick === settings.rounds
                    ? "单次模拟结果"
                    : `第 ${tick} 轮快照`}
                </span>
              </div>
              <div className="outcome-body">
                <div
                  className={`outcome-status ${tick === 0 ? "waiting" : comparison.passed ? "passed" : "tradeoff"}`}
                >
                  <span>
                    {tick === 0 ? (
                      <Globe2 size={19} />
                    ) : comparison.passed ? (
                      <CheckCheck size={20} />
                    ) : (
                      <GitBranch size={20} />
                    )}
                  </span>
                  <div>
                    <strong>
                      {tick === 0
                        ? "世界正在等待第一步"
                        : comparison.passed
                          ? "当前模拟达到目标"
                          : explored && tick === settings.rounds
                            ? "未找到满足条件的方案"
                            : "改变之中，仍有取舍"}
                    </strong>
                    <p>
                      {tick === 0
                        ? "推进时间，观察两种规则如何改变分配。"
                        : comparison.passed
                          ? "两项约束均满足，接下来检验它是否稳定。"
                          : explored && tick === settings.rounds
                            ? "两种方案均未满足全部约束，尝试记录已保留。"
                            : "查看下面的约束，再尝试另一组策略。"}
                    </p>
                  </div>
                </div>
                <div className="constraint-row">
                  <div>
                    <span className="constraint-label">
                      <GoalLabel goal={goal} />
                    </span>
                    <div className="constraint-track">
                      <span
                        style={{
                          width: `${Math.min(100, branch.frames[tick].metrics[goal.metric])}%`,
                        }}
                      />
                      <i style={{ left: `${goal.target}%` }} />
                    </div>
                  </div>
                  <div className="constraint-result">
                    <strong>
                      {branch.frames[tick].metrics[goal.metric].toFixed(1)}
                      {goal.metric === "diversity" ? "" : "%"}
                    </strong>
                    <span
                      className={
                        comparison.opportunityMet ? "good-label" : "warn-label"
                      }
                    >
                      {comparison.opportunityMet ? (
                        <Check size={12} />
                      ) : (
                        <MinusMark />
                      )}
                      {comparison.opportunityMet ? "达标" : "未达标"}
                    </span>
                  </div>
                </div>
                <div className="constraint-row">
                  <div>
                    <span className="constraint-label">
                      满意度下降不超过 {goal.tolerance} 分
                    </span>
                    <p className="constraint-hint">相对同轮基线的变化</p>
                  </div>
                  <div className="constraint-result">
                    <strong
                      className={
                        comparison.delta.satisfaction >= 0 ? "green-text" : ""
                      }
                    >
                      {comparison.delta.satisfaction >= 0 ? "+" : ""}
                      {comparison.delta.satisfaction.toFixed(1)}
                      <small> 分</small>
                    </strong>
                    <span
                      className={
                        comparison.satisfactionMet ? "good-label" : "warn-label"
                      }
                    >
                      {comparison.satisfactionMet ? (
                        <Check size={12} />
                      ) : (
                        <MinusMark />
                      )}
                      {comparison.satisfactionMet ? "达标" : "未达标"}
                    </span>
                  </div>
                </div>
                <div className="validation-line">
                  <ShieldCheck size={15} />
                  <span>
                    {validation ? (
                      <>
                        Seed {validation.seed} 复验：
                        <b>
                          {validation.passed
                            ? "同样达到目标"
                            : "未达到全部目标"}
                        </b>
                      </>
                    ) : (
                      "不同种子复验 · 尚未运行"
                    )}
                  </span>
                  <button
                    disabled={busy}
                    onClick={async () => {
                      const seed =
                        settings.seed + 37 > 999999 ? 37 : settings.seed + 37;
                      const start = performance.now();
                      const test = buildExperiment(
                        { ...settings, seed },
                        policy,
                      );
                      const result = compareWorlds(
                        test.baseline,
                        test.branch,
                        settings.rounds,
                        goal,
                      );
                      setValidation({
                        seed,
                        passed: result.passed,
                        delta: result.delta.satisfaction,
                        value: test.branch.frames.at(-1)!.metrics[goal.metric],
                      });
                      addEvent(
                        "simulate + compare_worlds",
                        "用新种子复验当前方案",
                        `Seed ${seed} 的完整模拟已结束。结果来自相同规则下的另一个世界。`,
                        { seed, policy },
                        result,
                        performance.now() - start,
                      );
                      notice("复验已完成；一次新种子结果不代表统计显著。");
                    }}
                  >
                    {validation ? "重新复验" : "运行复验"}
                    <ArrowUpRight size={12} />
                  </button>
                </div>
              </div>
              <div className="panel-footnote">
                <Info size={12} />
                结论限于当前模拟假设，可在实验设置中查看。
              </div>
            </section>
          </div>
          <footer className="page-footer">
            <span>
              <Brand small />
              <strong>FeedVerse</strong> <span>让推荐的可能性，被看见。</span>
            </span>
            <button onClick={() => openModal("help")}>
              关于这个世界 <ArrowUpRight size={12} />
            </button>
          </footer>
        </main>
      </div>

      {modal === "creator" && (
        <CreatorDetail
          creator={featured}
          baseline={baseline}
          branch={branch}
          frame={tick}
          onClose={closeModal}
          onNext={() => {
            const candidates = world.creators.filter((c) => c.isNew);
            const index = candidates.findIndex((c) => c.id === featured.id);
            setSelected(candidates[(index + 1) % candidates.length].id);
          }}
        />
      )}
      {modal === "settings" && (
        <Dialog
          title="定义你的实验"
          eyebrow="WORLD & POLICY"
          onClose={closeModal}
        >
          <div className="settings-section">
            <div className="settings-section-title">
              <Globe2 size={16} />
              <h3>世界设置</h3>
              <span>两组共同使用</span>
            </div>
            <div className="settings-inputs">
              <label>
                随机种子
                <input
                  type="number"
                  min={1}
                  max={999999}
                  value={draft.settings.seed || ""}
                  onChange={(e) =>
                    setDraft((v) => ({
                      ...v,
                      settings: { ...v.settings, seed: Number(e.target.value) },
                    }))
                  }
                />
              </label>
              <label>
                用户数量
                <select
                  value={draft.settings.users}
                  onChange={(e) =>
                    setDraft((v) => ({
                      ...v,
                      settings: {
                        ...v.settings,
                        users: Number(e.target.value),
                      },
                    }))
                  }
                >
                  {[240, 480, 960].map((v) => (
                    <option key={v} value={v}>
                      {v} 位用户
                    </option>
                  ))}
                </select>
              </label>
              <label>
                模拟轮数
                <select
                  value={draft.settings.rounds}
                  onChange={(e) =>
                    setDraft((v) => ({
                      ...v,
                      settings: {
                        ...v.settings,
                        rounds: Number(e.target.value),
                      },
                    }))
                  }
                >
                  {[30, 60, 90].map((v) => (
                    <option key={v} value={v}>
                      {v} 轮
                    </option>
                  ))}
                </select>
              </label>
            </div>
          </div>
          <div className="settings-section">
            <div className="settings-section-title">
              <SlidersHorizontal size={16} />
              <h3>干预策略</h3>
              <span className="orange-text">仅改变世界 B</span>
            </div>
            {(
              [
                [
                  "exploration",
                  "探索比例",
                  "从完整候选中随机探索，给尚未被发现的内容一个机会。",
                ],
                [
                  "newcomerBoost",
                  "新作者扶持",
                  "兴趣匹配时增加排序权重，随着曝光增长逐渐衰减。",
                ],
                [
                  "diversity",
                  "多样性重排",
                  "适度奖励该用户较少接触的内容类别。",
                ],
              ] as const
            ).map(([key, name, hint]) => (
              <div className="setting-slider" key={key}>
                <label htmlFor={`policy-${key}`}>
                  {name}
                  <strong>{percent(draft.policy[key])}%</strong>
                </label>
                <input
                  id={`policy-${key}`}
                  type="range"
                  min={0}
                  max={key === "exploration" ? 60 : 40}
                  step={1}
                  value={percent(draft.policy[key])}
                  onChange={(e) =>
                    setDraft((v) => ({
                      ...v,
                      policy: {
                        ...v.policy,
                        [key]: Number(e.target.value) / 100,
                      },
                    }))
                  }
                />
                <p>{hint}</p>
              </div>
            ))}
          </div>
          <div className="settings-section">
            <div className="settings-section-title">
              <Target size={16} />
              <h3>验收约束</h3>
            </div>
            <div className="settings-inputs two">
              <label>
                {METRICS.find((m) => m.key === goal.metric)!.name}
                {goal.metric === "concentration" ? "上限" : "目标"}
                <input
                  type="number"
                  min={1}
                  max={100}
                  value={draft.goal.target}
                  onChange={(e) =>
                    setDraft((v) => ({
                      ...v,
                      goal: { ...v.goal, target: Number(e.target.value) },
                    }))
                  }
                />
              </label>
              <label>
                允许满意度下降
                <select
                  value={draft.goal.tolerance}
                  onChange={(e) =>
                    setDraft((v) => ({
                      ...v,
                      goal: { ...v.goal, tolerance: Number(e.target.value) },
                    }))
                  }
                >
                  {[0, 1, 2, 3, 4, 5, 8].map((v) => (
                    <option value={v} key={v}>
                      {v} 分
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <p className="setting-note">
              演示控制器按以上约束执行，顶部文字作为实验备注；尚未接入自然语言模型。
            </p>
          </div>
          <details className="assumptions">
            <summary>
              这个世界基于哪些假设？
              <ChevronDown size={14} />
            </summary>
            <p>
              用户兴趣和内容池固定，每位用户每轮获得一次推荐。新创作者占
              1/3，初始声望较低。满意度由兴趣匹配、内容质量和重复疲劳计算。两组共有
              2%
              的背景探索率；滑块表示额外干预。反馈会影响下一轮排序，但不会改变用户兴趣。没有模拟社交转发或真实收入。
            </p>
          </details>
          {draftError && (
            <p className="field-error" role="alert">
              {draftError}
            </p>
          )}
          <div className="dialog-actions">
            <button
              className="text-button"
              onClick={() =>
                setDraft((v) => ({ ...v, policy: { ...DEFAULT_POLICY } }))
              }
            >
              恢复推荐参数
            </button>
            <button className="primary-button" onClick={applySettings}>
              应用并重新计算
              <ArrowRight size={14} />
            </button>
          </div>
        </Dialog>
      )}
      {modal === "metric" && (
        <Dialog
          title={
            METRICS.find((m) => m.key === metric)!.name + "，随着时间怎样变化？"
          }
          eyebrow="METRIC EXPLORER"
          onClose={closeModal}
          wide
        >
          <p className="dialog-description">
            {METRICS.find((m) => m.key === metric)!.hint}
          </p>
          <div className="metric-modal-tabs">
            {METRICS.map((m) => (
              <button
                key={m.key}
                onClick={() => setMetric(m.key)}
                className={metric === m.key ? "selected" : ""}
              >
                {m.name}
              </button>
            ))}
          </div>
          <div className="big-line-chart">
            <div className="y-axis">
              <span>100</span>
              <span>50</span>
              <span>0</span>
            </div>
            <div className="overlay-charts">
              <Sparkline
                values={baseline.frames.slice(1).map((f) => f.metrics[metric])}
                color="#7697cd"
                height={190}
                range={[0, 100]}
                fill
                label="基线完整趋势"
              />
              <Sparkline
                values={branch.frames.slice(1).map((f) => f.metrics[metric])}
                color="#d58f65"
                height={190}
                range={[0, 100]}
                fill
                label="干预完整趋势"
              />
            </div>
          </div>
          <div className="chart-axis">
            <span>第 1 轮</span>
            <span>第 {settings.rounds} 轮</span>
          </div>
          <div className="chart-legend">
            <span>
              <i className="world-dot blue" />
              基线 {baseline.frames.at(-1)!.metrics[metric].toFixed(1)}
            </span>
            <span>
              <i className="world-dot orange" />
              干预 {branch.frames.at(-1)!.metrics[metric].toFixed(1)}
            </span>
            <Delta
              value={fullComparison.delta[metric]}
              lower={metric === "concentration"}
              unit={METRICS.find((m) => m.key === metric)!.unit ? "pp" : "分"}
            />
          </div>
          <p className="setting-note">
            显示全部 {settings.rounds} 轮的累计指标；主画布的快照当前停在第{" "}
            {tick} 轮。
          </p>
        </Dialog>
      )}
      {(modal === "baseline" || modal === "branch") && (
        <Dialog
          title={
            modal === "baseline"
              ? "基线世界 · 点击率优先"
              : "干预世界 · 另一种可能"
          }
          eyebrow={`WORLD ${modal === "baseline" ? "A" : "B"} / ROUND ${tick}`}
          onClose={closeModal}
          wide
        >
          <WorldMap
            world={{ ...world, id: "expanded" }}
            frame={(modal === "baseline" ? baseline : branch).frames[tick]}
            maxExposure={Math.max(
              ...baseline.frames[tick].exposure,
              ...branch.frames[tick].exposure,
              1,
            )}
            selected={selected}
            onSelect={selectCreator}
            onlyNew={onlyNew}
            playing={false}
          />
          <p className="dialog-description">
            每个圆点是一位创作者，外圈标记新作者。点击圆点查看同一个人在两个世界中的经历。
          </p>
        </Dialog>
      )}
      {modal === "creators" && (
        <Dialog
          title="每个圆点背后，都有一个故事"
          eyebrow="THE PEOPLE IN THIS WORLD"
          onClose={closeModal}
          wide
        >
          <div className="creator-search">
            <Search size={16} />
            <input
              autoFocus
              placeholder="搜索创作者或内容类别…"
              value={creatorSearch}
              onChange={(e) => setCreatorSearch(e.target.value)}
              aria-label="搜索创作者"
            />
          </div>
          <div className="creator-directory">
            {world.creators
              .filter((c) =>
                (
                  c.name +
                  TOPICS[c.topic].name +
                  (c.isNew ? "新作者" : "")
                ).includes(creatorSearch),
              )
              .map((c) => (
                <button
                  className="creator-directory-item"
                  key={c.id}
                  onClick={() => selectCreator(c.id)}
                >
                  <Avatar creator={c} />
                  <div>
                    <strong>{c.name}</strong>
                    <span>
                      {TOPICS[c.topic].name} ·{" "}
                      {c.isNew ? "新创作者" : "成熟创作者"}
                    </span>
                  </div>
                  <span className="creator-exposures">
                    {branch.frames[tick].exposure[c.id].toLocaleString()}
                    <small>次曝光</small>
                  </span>
                  <ChevronRight size={14} />
                </button>
              ))}
          </div>
          {!world.creators.some((c) =>
            (
              c.name +
              TOPICS[c.topic].name +
              (c.isNew ? "新作者" : "")
            ).includes(creatorSearch),
          ) && (
            <div className="empty-state">
              <Search size={28} />
              <h3>没有找到这位创作者</h3>
              <p>试试“林间”或“生活”，也可以清空搜索。</p>
              <button
                className="secondary-button"
                onClick={() => setCreatorSearch("")}
              >
                查看全部创作者
              </button>
            </div>
          )}
        </Dialog>
      )}
      {modal === "history" && (
        <Dialog
          title="值得保留的每一次尝试"
          eyebrow="EXPERIMENT ARCHIVE"
          onClose={closeModal}
          wide
        >
          <p className="dialog-description">
            本次页面会话中的实验方案。点击一条，重新打开它的完整轨迹。
          </p>
          {history.length ? (
            <div className="history-list">
              {history.map((run) => (
                <button
                  key={run.id}
                  disabled={busy}
                  onClick={() => {
                    const restored = buildExperiment(run.settings, run.policy);
                    setExperiment(restored);
                    setGoal(run.goal);
                    setExplored(false);
                    setFrame(run.settings.rounds);
                    setValidation(null);
                    setModal(null);
                    addEvent(
                      "restore_run",
                      "回到一段实验记录",
                      "已重新计算并载入所选方案。",
                      { seed: run.settings.seed, policy: run.policy },
                      restored.branch.frames.at(-1)!.metrics,
                      restored.branch.durationMs,
                    );
                    notice("实验轨迹已载入。");
                  }}
                >
                  <span className="history-icon">
                    <GitBranch size={18} />
                  </span>
                  <div>
                    <strong>
                      {run.title}
                      <span className={run.passed ? "new-tag" : "muted-badge"}>
                        {run.passed ? "达标" : "存在取舍"}
                      </span>
                    </strong>
                    <p>
                      Seed {run.settings.seed} · 探索{" "}
                      {percent(run.policy.exploration)}% · 新作者曝光{" "}
                      {run.metrics.newcomerShare.toFixed(1)}%
                    </p>
                  </div>
                  <span>{run.time}</span>
                  <ArrowUpRight size={15} />
                </button>
              ))}
            </div>
          ) : (
            <div className="empty-state">
              <History size={34} />
              <h3>你的第一个实验，正等待开始</h3>
              <p>运行一次演示探索，或手动调整策略，方案就会出现在这里。</p>
              <button
                className="primary-button"
                onClick={() => {
                  setModal(null);
                  explore();
                }}
              >
                开始第一个实验
                <ArrowRight size={14} />
              </button>
            </div>
          )}
        </Dialog>
      )}
      {modal === "help" && (
        <Dialog
          title="欢迎来到推荐平行世界"
          eyebrow="A SMALL WORLD. BIG WHAT IFS."
          onClose={closeModal}
          wide
        >
          <p className="dialog-description">
            FeedVerse
            是一个可操作、可回放的推荐机制沙盘。在同一个起点改变规则，观察机会如何重新分配。
          </p>
          <div className="help-steps">
            {[
              [
                "01",
                "提出一个目标",
                "选择预设目标，或在实验设置中修改可计算的约束。",
              ],
              [
                "02",
                "看见世界分叉",
                "左侧固定为基线，右侧应用干预。播放或拖动时间轴同步观察。",
              ],
              [
                "03",
                "走近一位创作者",
                "点击圆点，对照曝光、独立用户和点击，追踪具体变化。",
              ],
              [
                "04",
                "检查而不只相信",
                "展开工具输入输出，用另一个随机种子复验，导出完整记录。",
              ],
            ].map(([num, title, desc]) => (
              <div key={num}>
                <span>{num}</span>
                <div>
                  <h3>{title}</h3>
                  <p>{desc}</p>
                </div>
              </div>
            ))}
          </div>
          <div className="help-callout">
            <Info size={18} />
            <div>
              <strong>关于这个交互原型</strong>
              <p>
                模拟引擎和工具结果是真实的本地计算。“AGH
                实验记录”由预设控制流程驱动，尚未连接 AGH
                或任何付费模型。固定初始条件让实验可重复；这些结果不能直接解释为真实平台的因果效果。
              </p>
            </div>
          </div>
          <div className="tools-inventory">
            {TOOL_DEFINITIONS.map(([tool, label]) => (
              <span key={tool}>
                <code>{tool}</code>
                {label}
              </span>
            ))}
          </div>
          <div className="dialog-actions">
            <span className="shortcut">
              <kbd>Space</kbd> 播放 / 暂停 <kbd>Esc</kbd> 关闭弹窗
            </span>
            <button className="primary-button" onClick={closeModal}>
              去看看另一个世界
              <ArrowRight size={14} />
            </button>
          </div>
        </Dialog>
      )}
      {toast && (
        <div className="toast" role="status">
          <Check size={16} />
          <span>{toast}</span>
          <button aria-label="关闭提示" onClick={() => setToast("")}>
            <X size={14} />
          </button>
        </div>
      )}
    </div>
  );
}

function MinusMark() {
  return <span className="minus-mark">−</span>;
}
