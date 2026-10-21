"""The memory guard that must exist before any model/container comparison runs on a 16GB machine (no real kill happens here)."""
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'infra' / 'dev_checks'))
import compare_models as cm  # noqa: E402
import memory_guard as mg  # noqa: E402


def sample(free=60, swap=0, resident=0, containers=0):
    return dict(t=0, system_free_pct=free, swap_used_mb=swap, model_resident_mb=resident, containers=containers, container_mem=[])


class Rules(unittest.TestCase):
    def test_a_breach_is_free_memory_under_15_percent_or_swap_over_4gb(self):
        self.assertEqual(mg.breaches(sample()), [])
        self.assertEqual(mg.breaches(sample(free=15)), [])                     # the limits are strict
        self.assertEqual(mg.breaches(sample(swap=4096)), [])
        self.assertEqual(len(mg.breaches(sample(free=14))), 1)
        self.assertEqual(len(mg.breaches(sample(swap=4097))), 1)
        self.assertEqual(len(mg.breaches(sample(free=5, swap=9000))), 2)

    def test_an_unreadable_sample_is_never_treated_as_healthy(self):
        self.assertTrue(mg.breaches(dict(sample(), system_free_pct=None)))
        self.assertTrue(mg.breaches(dict(sample(), swap_used_mb=None)))

    def test_starting_needs_40_percent_free_and_under_2gb_of_swap(self):
        self.assertEqual(mg.ready_to_start(sample(free=62, swap=0))[0], True)
        self.assertEqual(mg.ready_to_start(sample(free=40, swap=2047))[0], True)
        self.assertEqual(mg.ready_to_start(sample(free=39))[0], False)
        self.assertEqual(mg.ready_to_start(sample(swap=2048))[0], False)
        ok, why = mg.ready_to_start(sample(free=49, swap=13807))               # the state recorded just before the freeze
        self.assertFalse(ok)
        self.assertIn('13807', why)
        self.assertFalse(mg.ready_to_start(dict(sample(), system_free_pct=None))[0])


class GuardBehaviour(unittest.TestCase):
    def guard(self, samples):
        stopped = []
        iterator = iter(samples)
        guard = mg.Guard(lambda: next(iterator), lambda: stopped.append('stop'))
        return guard, stopped

    def test_it_trips_only_after_two_consecutive_breaches(self):
        guard, stopped = self.guard([sample(free=10), sample(), sample(free=10), sample(free=9)])
        self.assertEqual([guard.step() for _ in range(4)], [False, False, False, True])
        self.assertEqual(stopped, ['stop'])
        self.assertEqual(guard.tripped['reasons'][0][:4], '여유 메')
        self.assertEqual(guard.tripped['consecutive'], 2)

    def test_swap_alone_trips_it_and_a_recovered_sample_resets_the_count(self):
        guard, stopped = self.guard([sample(swap=5000), sample(swap=5000)])
        self.assertEqual([guard.step(), guard.step()], [False, True])
        self.assertEqual(stopped, ['stop'])

    def test_it_stops_once_and_keeps_reporting_tripped(self):
        guard, stopped = self.guard([sample(free=1)] * 5)
        results = [guard.step() for _ in range(5)]
        self.assertEqual(results, [False, True, True, True, True])
        self.assertEqual(stopped, ['stop'])

    def test_peak_figures_are_kept_for_the_record(self):
        guard, _ = self.guard([sample(free=70, swap=10, resident=4800), sample(free=30, swap=900, resident=5200)])
        guard.step()
        guard.step()
        self.assertEqual((guard.min_free_pct, guard.max_swap_mb, guard.max_resident_mb), (30, 900, 5200))


class StopsOnlyWhatItStarted(unittest.TestCase):
    def test_it_ends_the_given_ollama_and_only_lifecycle_containers(self):
        killed, docker = [], []

        def runner(args, **kwargs):
            docker.append(list(args))

            class Done:
                returncode, stdout = 0, 'lifecycle-aaa\nsome-other-app\nlifecycle-bbb\nlifecycle\n'
            return Done()
        mg.stop_own_processes(4242, kill=lambda pid, sig: killed.append((pid, sig)), run=runner, alive=lambda pid: False)
        self.assertEqual(killed[0][0], 4242)
        removed = [c[-1] for c in docker if c[:3] == ['docker', 'rm', '-f']]
        self.assertEqual(removed, ['lifecycle-aaa', 'lifecycle-bbb'])           # never another app's container

    def test_a_process_that_survives_term_gets_killed(self):
        killed = []
        mg.stop_own_processes(7, kill=lambda pid, sig: killed.append(sig), run=lambda *a, **k: type('D', (), dict(returncode=0, stdout=''))(),
                              alive=lambda pid: True, wait=lambda s: None)
        self.assertEqual(len(killed), 2)
        self.assertNotEqual(killed[0], killed[1])

    def test_an_already_ended_process_is_not_an_error_and_cleanup_still_runs(self):
        docker = []

        def gone(pid, sig):
            raise ProcessLookupError

        def runner(args, **kwargs):
            docker.append(list(args))
            return type('D', (), dict(returncode=0, stdout='lifecycle-x\n'))()
        mg.stop_own_processes(4242, kill=gone, run=runner, alive=lambda pid: False, wait=lambda s: None)
        self.assertIn(['docker', 'rm', '-f', 'lifecycle-x'], docker)

    def test_it_refuses_to_signal_pid_zero_or_one_or_itself(self):
        killed = []
        for pid in (0, 1, os.getpid(), -5, None):
            mg.stop_own_processes(pid, kill=lambda p, s: killed.append(p), run=lambda *a, **k: type('D', (), dict(returncode=0, stdout=''))(),
                                  alive=lambda p: False)
        self.assertEqual(killed, [])


class FakeApi:
    """Everything the runner touches, in memory: samples are scripted, tasks finish after a number of polls."""
    def __init__(self, samples, polls_per_task=2, loaded=()):
        self.samples, self.polls, self.loaded_after_unload = list(samples), polls_per_task, list(loaded)
        self.events, self.pid = [], 4321

    def sample(self):
        return self.samples.pop(0) if len(self.samples) > 1 else self.samples[0]

    def start_server(self):
        self.events.append('server')
        return self.pid

    def stop_own(self, pid):
        self.events.append(('stop', pid))

    def unload_all(self):
        self.events.append('unload')

    def loaded_models(self):
        return self.loaded_after_unload

    def sleep(self, seconds):
        pass

    def start_task(self, model, task):
        self.events.append(('task', model, task))
        api = self

        class Handle:
            count = 0

            def poll(self):
                self.count += 1
                return 0 if self.count > api.polls else None

            def terminate(self):
                api.events.append(('terminated', model, task))

            def result(self):
                return dict(model=model, task=task, outcome='ok')
        return Handle()


class ComparisonRunner(unittest.TestCase):
    def test_it_does_not_start_anything_when_the_machine_is_not_ready(self):
        api = FakeApi([sample(free=49, swap=13807)])
        report = cm.run_comparison(['m1'], ['t1'], api)
        self.assertEqual(report['status'], 'not_started')
        self.assertEqual(api.events, [])                                       # no server, no task, nothing to stop

    def test_runs_are_strictly_one_model_one_task_at_a_time_with_an_unload_check_between_models(self):
        api = FakeApi([sample()])
        report = cm.run_comparison(['m1', 'm2'], ['t1', 't2'], api)
        self.assertEqual(report['status'], 'completed')
        self.assertEqual([e for e in api.events if isinstance(e, tuple) and e[0] == 'task'],
                         [('task', 'm1', 't1'), ('task', 'm1', 't2'), ('task', 'm2', 't1'), ('task', 'm2', 't2')])
        self.assertEqual(api.events.count('unload'), 2)                        # once before each model
        self.assertEqual(api.events[-1], ('stop', 4321))                       # the server this run started is always ended
        self.assertEqual([r['outcome'] for r in report['runs']], ['finished'] * 4)

    def test_a_model_that_is_still_loaded_after_unloading_stops_the_comparison(self):
        api = FakeApi([sample()], loaded=['m1'])
        report = cm.run_comparison(['m1', 'm2'], ['t1'], api)
        self.assertEqual(report['status'], 'aborted')
        self.assertIn('언로드', report['reason'])
        self.assertFalse([e for e in api.events if isinstance(e, tuple) and e[0] == 'task'])

    def test_two_breaches_during_a_task_stop_it_and_the_rest_and_are_recorded_as_a_resource_stop(self):
        api = FakeApi([sample(), sample(), sample(free=10), sample(free=9), sample(free=9)], polls_per_task=10)   # ready twice, then two breaches
        report = cm.run_comparison(['m1'], ['t1', 't2'], api)
        self.assertEqual(report['status'], 'aborted_for_resources')
        self.assertEqual(report['runs'][-1]['outcome'], '자원 초과로 중단')
        self.assertIn(('terminated', 'm1', 't1'), api.events)
        self.assertNotIn(('task', 'm1', 't2'), api.events)                     # the next task never starts
        self.assertEqual(api.events.count(('stop', 4321)), 2)                  # the guard stops it, then the final cleanup repeats it harmlessly

    def test_the_machine_must_be_ready_again_before_every_task(self):
        api = FakeApi([sample(), sample(), sample(free=30), sample(free=30)], polls_per_task=1)
        report = cm.run_comparison(['m1'], ['t1', 't2'], api)
        self.assertEqual(report['status'], 'stopped_before_run')
        self.assertEqual(len(report['runs']), 1)


if __name__ == '__main__':
    unittest.main()
