import assert from "node:assert/strict";
import { test } from "node:test";
import {
  BASELINE_POLICY,
  compareWorlds,
  createWorld,
  DEFAULT_POLICY,
  DEFAULT_SETTINGS,
  forkWorld,
  GOALS,
  simulate,
} from "../src/engine.ts";

test("seeded experiments and common-condition forks are reproducible", () => {
  const world = createWorld(DEFAULT_SETTINGS);
  const before = JSON.stringify(world);
  const a = simulate(world, DEFAULT_POLICY);
  const b = simulate(forkWorld(world), DEFAULT_POLICY);
  assert.deepEqual(a.frames, b.frames);
  assert.equal(
    JSON.stringify(world),
    before,
    "running a branch must not mutate its source world",
  );
  assert.deepEqual(createWorld(DEFAULT_SETTINGS), world);
  assert.notDeepEqual(createWorld({ ...DEFAULT_SETTINGS, seed: 79 }), world);
});

test("exposure, clicks, distinct reach, and metrics obey their definitions", () => {
  const world = createWorld({ ...DEFAULT_SETTINGS, users: 60, rounds: 20 });
  const run = simulate(world, DEFAULT_POLICY);
  for (const frame of run.frames) {
    assert.equal(
      frame.exposure.reduce((a, b) => a + b, 0),
      frame.tick * 60,
    );
    assert.equal(frame.total, frame.tick * 60);
    frame.exposure.forEach((count, id) => {
      assert.ok(frame.clicks[id] <= count);
      assert.ok(frame.reach[id] <= Math.min(count, 60));
    });
    for (const value of Object.values(frame.metrics))
      assert.ok(Number.isFinite(value) && value >= 0 && value <= 100);
    if (frame.tick) {
      const newExposures = world.creators
        .filter((c) => c.isNew)
        .reduce((sum, c) => sum + frame.exposure[c.id], 0);
      assert.equal(
        frame.metrics.newcomerShare,
        (newExposures / frame.total) * 100,
      );
    }
  }
});

test("goals are evaluated from results, including tradeoffs and unstarted worlds", () => {
  const world = createWorld(DEFAULT_SETTINGS);
  const baseline = simulate(world, BASELINE_POLICY);
  const intervention = simulate(world, DEFAULT_POLICY);
  const verdict = compareWorlds(baseline, intervention, 60, GOALS[0]);
  assert.equal(
    verdict.passed,
    verdict.opportunityMet && verdict.satisfactionMet,
  );
  assert.equal(
    verdict.delta.newcomerShare,
    intervention.frames[60].metrics.newcomerShare -
      baseline.frames[60].metrics.newcomerShare,
  );
  assert.equal(
    compareWorlds(baseline, intervention, 0, GOALS[0]).passed,
    false,
  );
  assert.equal(
    compareWorlds(baseline, intervention, 60, { ...GOALS[0], target: 100 })
      .passed,
    false,
  );
  const aggressive = simulate(world, {
    exploration: 0.6,
    newcomerBoost: 0,
    diversity: 0,
  });
  assert.equal(
    compareWorlds(baseline, aggressive, 60, { ...GOALS[0], tolerance: 0 })
      .satisfactionMet,
    false,
  );
});

test("invalid settings and policy values are rejected", () => {
  assert.throws(() => createWorld({ ...DEFAULT_SETTINGS, seed: NaN }));
  assert.throws(() => createWorld({ ...DEFAULT_SETTINGS, users: 5000 }));
  assert.throws(() =>
    simulate(createWorld(DEFAULT_SETTINGS), {
      ...DEFAULT_POLICY,
      exploration: Infinity,
    }),
  );
});
