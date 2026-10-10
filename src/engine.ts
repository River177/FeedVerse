/** A small, deterministic recommendation world. All displayed metrics come from here. */
export const ENGINE_VERSION = "feedverse-sim/0.1";
export const TOPICS = [
  { name: "科技", color: "#8186d9", soft: "#eeeffb", x: 132, y: 84 },
  { name: "生活", color: "#d8ad61", soft: "#faf4e7", x: 328, y: 72 },
  { name: "艺术", color: "#93b6a7", soft: "#edf5f1", x: 442, y: 152 },
  { name: "音乐", color: "#b194c8", soft: "#f4eef8", x: 354, y: 266 },
  { name: "知识", color: "#88b0cb", soft: "#edf4f8", x: 167, y: 274 },
  { name: "影像", color: "#d39181", soft: "#faeeea", x: 67, y: 184 },
];
export type Policy = {
  exploration: number;
  newcomerBoost: number;
  diversity: number;
};
export type Settings = {
  seed: number;
  users: number;
  creators: number;
  rounds: number;
};
export type Creator = {
  id: number;
  name: string;
  topic: number;
  isNew: boolean;
  quality: number;
  prior: number;
  x: number;
  y: number;
  bio: string;
};
export type User = { id: number; affinity: number[] };
export type World = {
  id: string;
  settings: Settings;
  creators: Creator[];
  users: User[];
};
export type Metrics = {
  satisfaction: number;
  newcomerShare: number;
  diversity: number;
  concentration: number;
  clickRate: number;
};
export type Frame = {
  tick: number;
  exposure: number[];
  clicks: number[];
  reach: number[];
  metrics: Metrics;
  total: number;
};
export type Simulation = {
  worldId: string;
  policy: Policy;
  frames: Frame[];
  durationMs: number;
};
export type GoalId = "newcomers" | "diversity" | "balance";
export type Goal = {
  id: GoalId;
  label: string;
  prompt: string;
  metric: "newcomerShare" | "diversity" | "concentration";
  target: number;
  tolerance: number;
};
export const GOALS: Goal[] = [
  {
    id: "newcomers",
    label: "发现新创作者",
    prompt: "让新创作者获得更多机会，同时保持用户满意度",
    metric: "newcomerShare",
    target: 20,
    tolerance: 3,
  },
  {
    id: "diversity",
    label: "拓宽兴趣边界",
    prompt: "让用户看到更多元的内容，同时保持用户满意度",
    metric: "diversity",
    target: 22,
    tolerance: 4,
  },
  {
    id: "balance",
    label: "减少曝光集中",
    prompt: "让曝光分配更均衡，同时保持用户满意度",
    metric: "concentration",
    target: 40,
    tolerance: 3,
  },
];
export const DEFAULT_SETTINGS: Settings = {
  seed: 42,
  users: 480,
  creators: 72,
  rounds: 60,
};
export const BASELINE_POLICY: Policy = {
  exploration: 0,
  newcomerBoost: 0,
  diversity: 0,
};
export const DEFAULT_POLICY: Policy = {
  exploration: 0.08,
  newcomerBoost: 0.12,
  diversity: 0.1,
};
const NAMES = [
  "像素漫游",
  "橘子汽水",
  "山间工作室",
  "声波旅人",
  "好奇心日报",
  "光影备忘录",
  "代码与咖啡",
  "日常碎片",
  "青石画室",
  "晚风电台",
  "纸上宇宙",
  "第七格",
  "未来来信",
  "小岛生活",
  "留白之间",
  "黑胶星期天",
  "万物简史",
  "一帧远方",
  "比特花园",
  "人间观察",
  "半亩蓝",
  "耳边星河",
  "知更笔记",
  "路过的风",
  "数字游牧",
  "慢慢食光",
  "拾色计划",
  "空白唱片",
  "地图之外",
  "银盐日记",
  "极客公园",
  "周末散步",
  "形状研究所",
  "一颗音符",
  "小小博物馆",
  "蓝调时刻",
  "电路星球",
  "面包与诗",
  "纸间山海",
  "雨天现场",
  "好问题",
  "未眠镜头",
  "算法之外",
  "温柔杂货铺",
  "一笔春天",
  "月亮合唱团",
  "百科散步",
  "日落之后",
  "零号玩家",
  "林间来信",
  "山海小画家",
  "凌晨三点",
  "一页新知",
  "沿途有光",
  "小熊造物",
  "今天也晴朗",
  "彩色星期一",
  "岛屿声音",
  "星球手记",
  "取景框外",
  "不止科技",
  "厨房小星球",
  "泥土与花",
  "自由频率",
  "小宇宙问答",
  "浮光集",
  "开源诗人",
  "春日出走",
  "野生艺术家",
  "留声花房",
  "知了又知",
  "一秒电影",
];

export function noise(seed: number, a: number, b = 0, c = 0): number {
  let x =
    (seed ^
      Math.imul(a + 1, 374761393) ^
      Math.imul(b + 1, 668265263) ^
      Math.imul(c + 1, 1274126177)) >>>
    0;
  x = Math.imul(x ^ (x >>> 13), 1274126177);
  return ((x ^ (x >>> 16)) >>> 0) / 4294967296;
}

function validateSettings(s: Settings) {
  if (!Number.isSafeInteger(s.seed) || s.seed < 1 || s.seed > 999999)
    throw new Error("种子需为 1–999999 的整数");
  if (!Number.isInteger(s.users) || s.users < 60 || s.users > 1200)
    throw new Error("用户数量需为 60–1200");
  if (!Number.isInteger(s.creators) || s.creators < 24 || s.creators > 120)
    throw new Error("创作者数量需为 24–120");
  if (!Number.isInteger(s.rounds) || s.rounds < 10 || s.rounds > 120)
    throw new Error("模拟轮数需为 10–120");
}

export function createWorld(settings: Settings): World {
  validateSettings(settings);
  const creators: Creator[] = Array.from(
    { length: settings.creators },
    (_, id) => {
      const topic = id % TOPICS.length;
      const cluster = TOPICS[topic];
      const ring = Math.floor(id / TOPICS.length);
      const angle = ring * 2.39996323 + topic * 0.65;
      const radius = 14 + Math.sqrt(ring) * 13.5;
      const isNew = id >= Math.floor((settings.creators * 2) / 3);
      return {
        id,
        name:
          NAMES[id % NAMES.length] +
          (id >= NAMES.length ? " · " + (id + 1) : ""),
        topic,
        isNew,
        quality: 0.58 + noise(settings.seed, id, 18) * 0.38,
        prior: isNew ? 1 : 8 + Math.pow(noise(settings.seed, id, 7), 3) * 280,
        x: cluster.x + Math.cos(angle) * radius,
        y: cluster.y + Math.sin(angle) * radius * 0.75,
        bio: [
          "在数字与灵感之间，发现新的可能。",
          "记录微小日常，也分享值得停留的瞬间。",
          "用自己的方式，描绘眼中的世界。",
          "把生活的声音，写成一封给你的信。",
          "从一个好问题出发，走近更大的世界。",
          "收藏光线、街角和正在发生的故事。",
        ][topic],
      };
    },
  );
  const users: User[] = Array.from({ length: settings.users }, (_, id) => {
    const primary = Math.floor(noise(settings.seed, id, 23) * 6);
    const secondary =
      (primary + 1 + Math.floor(noise(settings.seed, id, 29) * 5)) % 6;
    return {
      id,
      affinity: TOPICS.map((_, topic) =>
        topic === primary
          ? 0.94
          : topic === secondary
            ? 0.72
            : 0.12 + noise(settings.seed, id, topic, 10) * 0.28,
      ),
    };
  });
  return {
    id: `world-${settings.seed}-${settings.users}-${settings.creators}`,
    settings: { ...settings },
    creators,
    users,
  };
}

export function forkWorld(world: World): World {
  return {
    ...world,
    id: `${world.id}-branch`,
    settings: { ...world.settings },
    creators: world.creators.map((c) => ({ ...c })),
    users: world.users.map((u) => ({ ...u, affinity: [...u.affinity] })),
  };
}

export function simulate(world: World, policy: Policy): Simulation {
  for (const v of Object.values(policy))
    if (!Number.isFinite(v) || v < 0 || v > 0.6)
      throw new Error("策略参数应在 0–60% 之间");
  const start = performance.now();
  const { settings, creators, users } = world;
  const count = creators.length;
  const exposure = new Array<number>(count).fill(0);
  const clicks = new Array<number>(count).fill(0);
  const reach = new Array<number>(count).fill(0);
  const seen = new Uint16Array(settings.users * count);
  const topicsSeen = new Uint16Array(settings.users * 6);
  const frames: Frame[] = [
    {
      tick: 0,
      exposure: [...exposure],
      clicks: [...clicks],
      reach: [...reach],
      total: 0,
      metrics: {
        satisfaction: 0,
        newcomerShare: 0,
        diversity: 0,
        concentration: 0,
        clickRate: 0,
      },
    },
  ];
  let satisfaction = 0,
    newViews = 0,
    totalClicks = 0;
  for (let tick = 1; tick <= settings.rounds; tick++) {
    const maxPopularity = Math.log1p(
      Math.max(...creators.map((c) => c.prior + exposure[c.id])),
    );
    const popularity = creators.map(
      (c) => Math.log1p(c.prior + exposure[c.id]) / maxPopularity,
    );
    for (const u of users) {
      let chosen = 0,
        best = -Infinity;
      // A 2% background discovery rate is shared by both worlds; policy adds exploration.
      const exploratory =
        noise(settings.seed, tick, u.id, 500) < 0.02 + policy.exploration;
      const discovery = Math.floor(
        noise(settings.seed, tick, u.id, 501) * count,
      );
      for (const c of creators) {
        const fatigue = Math.sqrt(seen[u.id * count + c.id]) * 0.022;
        const affinity = u.affinity[c.topic];
        const diversity = 1 - topicsSeen[u.id * 6 + c.topic] / tick;
        const random = noise(settings.seed, tick, u.id, c.id);
        const score = exploratory
          ? c.id === discovery
            ? 1
            : 0
          : affinity * 0.48 +
            (c.isNew ? 0.66 : c.quality) * 0.22 +
            popularity[c.id] * 0.3 -
            fatigue +
            (c.isNew
              ? (policy.newcomerBoost * affinity) /
                Math.sqrt(1 + exposure[c.id] / 60)
              : 0) +
            policy.diversity * diversity +
            random * 0.035;
        if (score > best) {
          best = score;
          chosen = c.id;
        }
      }
      const creator = creators[chosen];
      const index = u.id * count + chosen;
      const tiredness = Math.min(0.13, seen[index] * 0.007);
      const utility = Math.max(
        0.05,
        Math.min(
          0.99,
          0.14 +
            u.affinity[creator.topic] * 0.6 +
            creator.quality * 0.21 -
            tiredness,
        ),
      );
      satisfaction += utility;
      exposure[chosen]++;
      if (seen[index] === 0) reach[chosen]++;
      seen[index]++;
      topicsSeen[u.id * 6 + creator.topic]++;
      if (creator.isNew) newViews++;
      if (noise(settings.seed, tick, u.id, 998) < utility * 0.65) {
        clicks[chosen]++;
        totalClicks++;
      }
    }
    const total = tick * settings.users;
    let entropy = 0;
    for (const u of users)
      for (let topic = 0; topic < 6; topic++) {
        const p = topicsSeen[u.id * 6 + topic] / tick;
        if (p > 0) entropy -= p * Math.log(p);
      }
    const sorted = [...exposure].sort((a, b) => b - a);
    frames.push({
      tick,
      exposure: [...exposure],
      clicks: [...clicks],
      reach: [...reach],
      total,
      metrics: {
        satisfaction: (satisfaction / total) * 100,
        newcomerShare: (newViews / total) * 100,
        diversity: (entropy / settings.users / Math.log(6)) * 100,
        concentration:
          (sorted.slice(0, Math.ceil(count * 0.1)).reduce((a, b) => a + b, 0) /
            total) *
          100,
        clickRate: (totalClicks / total) * 100,
      },
    });
  }
  return {
    worldId: world.id,
    policy: { ...policy },
    frames,
    durationMs: performance.now() - start,
  };
}

export function compareWorlds(
  baseline: Simulation,
  branch: Simulation,
  tick: number,
  goal: Goal,
) {
  const a = baseline.frames[tick].metrics,
    b = branch.frames[tick].metrics;
  const delta = Object.fromEntries(
    Object.keys(a).map((k) => [
      k,
      b[k as keyof Metrics] - a[k as keyof Metrics],
    ]),
  ) as Metrics;
  const opportunityMet =
    tick > 0 &&
    (goal.metric === "concentration"
      ? b[goal.metric] <= goal.target
      : b[goal.metric] >= goal.target);
  const satisfactionMet = tick > 0 && delta.satisfaction >= -goal.tolerance;
  return {
    delta,
    opportunityMet,
    satisfactionMet,
    passed: opportunityMet && satisfactionMet,
  };
}

export const TOOL_DEFINITIONS = [
  ["create_world", "创建可复现的世界"],
  ["inspect_world", "观察当前状态"],
  ["fork_world", "创建同源对照"],
  ["set_policy", "调整推荐规则"],
  ["simulate", "推进本地模拟"],
  ["compare_worlds", "比较收益与代价"],
  ["trace_entity", "追踪创作者经历"],
] as const;
