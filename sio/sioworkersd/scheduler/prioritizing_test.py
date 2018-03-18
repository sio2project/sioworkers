import random
import unittest

from sio.sioworkersd.scheduler import prioritizing


class WaitingTasksQueueTest(unittest.TestCase):
    def test_basic_methods_should_work_as_expected(self):
        s = prioritizing._WaitingTasksQueue()
        task = create_task_info()
        self.assertNotIn(task, s)
        self.assertEqual(len(s), 0)

        s.add(task)
        self.assertIn(task, s)
        self.assertEqual(len(s), 1)

        s.remove(task)
        self.assertNotIn(task, s)
        self.assertEqual(len(s), 0)

    def test_left_should_return_first_inserted_element(self):
        s = prioritizing._WaitingTasksQueue()
        task_1 = create_task_info()
        task_2 = create_task_info()

        s.add(task_2)
        s.add(task_1)
        self.assertEqual(s.left(), task_2)

    def test_left_should_return_none_when_empty(self):
        s = prioritizing._WaitingTasksQueue()
        self.assertIsNone(s.left())

    def test_popleft_should_remove_oldest_element(self):
        s = prioritizing._WaitingTasksQueue()
        task_1 = create_task_info()
        task_2 = create_task_info()
        s.add(task_2)
        s.add(task_1)

        self.assertEqual(s.popleft(), task_2)
        self.assertEqual(len(s), 1)

        self.assertEqual(s.left(), task_1)

    def test_should_keep_track_of_task_ram_requirements(self):
        s = prioritizing._WaitingTasksQueue()
        task_1 = create_task_info(ram=1024)
        task_2 = create_task_info(ram=256)

        s.add(task_1)
        s.add(task_2)

        self.assertEqual(s.getTasksRequiredRam(), [256, 1024])

    def test_should_update_ram_requirements_when_task_is_removed(self):
        s = prioritizing._WaitingTasksQueue()
        task_1 = create_task_info(ram=1024)
        task_2 = create_task_info(ram=256)

        s.add(task_1)
        s.add(task_2)
        s.remove(task_2)

        self.assertEqual(s.getTasksRequiredRam(), [1024])


class WorkerInfoTest(unittest.TestCase):
    def test_get_queue_name_should_pick_correct_queue(self):
        vcpu_only_worker = create_worker_info(is_real_cpu=False)
        any_cpu_worker = create_worker_info(is_real_cpu=True)

        self.assertEqual(vcpu_only_worker.getQueueName(), 'vcpu-only')
        self.assertEqual(any_cpu_worker.getQueueName(), 'any-cpu')

    def test_get_queue_name_should_return_none_when_worker_is_busy(self):
        vcpu_only_worker = create_worker_info(concurrency=2, is_real_cpu=False)
        any_cpu_worker = create_worker_info(is_real_cpu=True)

        vcpu_only_worker.attachTask(create_task_info(is_real_cpu=False))
        vcpu_only_worker.attachTask(create_task_info(is_real_cpu=False))

        any_cpu_worker.attachTask(create_task_info(is_real_cpu=True))

        self.assertIsNone(vcpu_only_worker.getQueueName())
        self.assertIsNone(any_cpu_worker.getQueueName())

    def test_get_available_ram_should_depend_on_attached_tasks(self):
        worker = create_worker_info(ram=1024, is_real_cpu=False)
        task_1 = create_task_info(ram=256, is_real_cpu=False)
        task_2 = create_task_info(ram=512, is_real_cpu=False)

        self.assertEqual(worker.getAvailableRam(), 1024)

        worker.attachTask(task_1)
        self.assertEqual(worker.getAvailableRam(), 1024 - 256)

        worker.attachTask(task_2)
        self.assertEqual(worker.getAvailableRam(), 1024 - 256 - 512)

        worker.detachTask(task_1)
        self.assertEqual(worker.getAvailableRam(), 1024 - 512)

    def test_get_available_vcpu_slots_should_depend_on_attached_tasks(self):
        worker = create_worker_info(concurrency=2, is_real_cpu=False)
        task_1 = create_task_info(is_real_cpu=False)
        task_2 = create_task_info(is_real_cpu=False)

        self.assertEqual(worker.getAvailableVcpuSlots(), 2)

        worker.attachTask(task_1)
        self.assertEqual(worker.getAvailableVcpuSlots(), 1)

        worker.attachTask(task_2)
        self.assertEqual(worker.getAvailableVcpuSlots(), 0)

        worker.detachTask(task_1)
        self.assertEqual(worker.getAvailableVcpuSlots(), 1)

    def test_get_available_vcpu_slots_should_be_zero_when_cpu_is_busy(self):
        worker = create_worker_info(concurrency=2, is_real_cpu=True)
        task = create_task_info(is_real_cpu=True)

        self.assertEqual(worker.getAvailableVcpuSlots(), 2)

        worker.attachTask(task)
        self.assertEqual(worker.getAvailableVcpuSlots(), 0)

        worker.detachTask(task)
        self.assertEqual(worker.getAvailableVcpuSlots(), 2)


class TasksQueuesTest(unittest.TestCase):
    def test_should_prefer_tasks_from_higher_priority_contests(self):
        contest_1 = create_contest_info(id=1, priority=5)
        contest_2 = create_contest_info(id=2, priority=10)

        task_1 = create_task_info(contest=contest_1, priority=100)
        task_2 = create_task_info(contest=contest_2, priority=1)

        queues = prioritizing.TasksQueues(random.Random())

        queues.addTask(task_1)
        queues.addTask(task_2)

        self.assertEqual(queues.chooseTask(), task_2)

        queues.delTask(task_2)
        self.assertEqual(queues.chooseTask(), task_1)

    def test_should_prefer_tasks_with_higher_priority_from_same_contest(self):
        contest = create_contest_info()

        task_1 = create_task_info(contest=contest, priority=1)
        task_2 = create_task_info(contest=contest, priority=100)

        queues = prioritizing.TasksQueues(random.Random())

        queues.addTask(task_1)
        queues.addTask(task_2)

        self.assertEqual(queues.chooseTask(), task_2)

        queues.delTask(task_2)
        self.assertEqual(queues.chooseTask(), task_1)

    def test_should_respect_contest_weights_if_same_priority(self):
        contest_1 = create_contest_info(id=1, priority=10, weight=2)
        contest_2 = create_contest_info(id=2, priority=10, weight=8)

        queues = prioritizing.TasksQueues(random.Random())

        # Add an equal amount of tasks.
        for _ in range(100):
            queues.addTask(create_task_info(contest=contest_1))
            queues.addTask(create_task_info(contest=contest_2))

        def choose_and_remove():
            task = queues.chooseTask()
            queues.delTask(task)
            return task

        chosen_tasks = [choose_and_remove() for _ in range(100)]

        tasks_from_1 = sum(task.contest.uid == 1 for task in chosen_tasks)
        tasks_from_2 = sum(task.contest.uid == 2 for task in chosen_tasks)

        self.assertGreater(tasks_from_1, 0)
        self.assertGreater(tasks_from_2, 0)
        self.assertGreater(tasks_from_2, 2 * tasks_from_1)


class PrioritizingSchedulerTest(unittest.TestCase):
    def test_should_prefer_vcpu_only_workers_for_virtual_cpu_tasks(self):
        vcpu_only_worker = {'id': 1, 'concurrency': 4, 'is_real_cpu': False}
        any_cpu_worker_1 = {'id': 2, 'is_real_cpu': True}
        any_cpu_worker_2 = {'id': 3, 'is_real_cpu': True}

        scheduler = prioritizing.PrioritizingScheduler(WorkerManagerStub(
            vcpu_only_worker, any_cpu_worker_1, any_cpu_worker_2))

        scheduler.addWorker(1)
        scheduler.addWorker(2)
        scheduler.addWorker(3)

        scheduler.updateContest(contest_uid=1, priority=10, weight=10)

        add_task_to_scheduler(scheduler, 1, is_real_cpu=False, ram=256)
        add_task_to_scheduler(scheduler, 2, is_real_cpu=False, ram=256)

        scheduled_tasks = scheduler.schedule()

        self.assertItemsEqual([(1, 1), (2, 1)], scheduled_tasks)

    def test_should_respect_ram_limits_when_assigning_vcpu_tasks(self):
        vcpu_only_worker = {
            'id': 1, 'concurrency': 4, 'ram': 2048, 'is_real_cpu': False}

        scheduler = prioritizing.PrioritizingScheduler(WorkerManagerStub(
            vcpu_only_worker))

        scheduler.addWorker(1)

        scheduler.updateContest(contest_uid=1, priority=10, weight=10)

        add_task_to_scheduler(scheduler, 1, is_real_cpu=False, ram=1024)
        add_task_to_scheduler(scheduler, 2, is_real_cpu=False, ram=512)
        add_task_to_scheduler(scheduler, 3, is_real_cpu=False, ram=1024)

        scheduled_tasks = scheduler.schedule()

        # Third task should be blocked.
        self.assertItemsEqual([(1, 1), (2, 1)], scheduled_tasks)

    def test_should_respect_concurrency_limits_when_assigning_vcpu_tasks(self):
        vcpu_only_worker = {
            'id': 1, 'concurrency': 2, 'ram': 8192, 'is_real_cpu': False}

        scheduler = prioritizing.PrioritizingScheduler(WorkerManagerStub(
            vcpu_only_worker))

        scheduler.addWorker(1)

        scheduler.updateContest(contest_uid=1, priority=10, weight=10)

        add_task_to_scheduler(scheduler, 1, is_real_cpu=False, ram=256)
        add_task_to_scheduler(scheduler, 2, is_real_cpu=False, ram=256)
        add_task_to_scheduler(scheduler, 3, is_real_cpu=False, ram=256)

        scheduled_tasks = scheduler.schedule()

        # Third task should be blocked.
        self.assertItemsEqual([(1, 1), (2, 1)], scheduled_tasks)

    def test_should_assign_vcpu_tasks_to_any_cpu_workers_if_no_others(self):
        any_cpu_worker = {'id': 1, 'is_real_cpu': True}

        scheduler = prioritizing.PrioritizingScheduler(WorkerManagerStub(
            any_cpu_worker))

        scheduler.addWorker(1)

        scheduler.updateContest(contest_uid=1, priority=10, weight=10)
        add_task_to_scheduler(scheduler, 1, is_real_cpu=False)

        scheduled_tasks = scheduler.schedule()

        self.assertItemsEqual([(1, 1)], scheduled_tasks)

    def test_should_block_partially_busy_workers_for_real_cpu_tasks(self):
        any_cpu_worker_1 = {
            'id': 1, 'concurrency': 2, 'ram': 512, 'is_real_cpu': True}
        any_cpu_worker_2 = {
            'id': 2, 'concurrency': 2, 'ram': 4096, 'is_real_cpu': True}

        scheduler = prioritizing.PrioritizingScheduler(WorkerManagerStub(
            any_cpu_worker_1, any_cpu_worker_2))

        scheduler.addWorker(1)
        scheduler.addWorker(2)

        scheduler.updateContest(contest_uid=1, priority=10, weight=10)

        add_task_to_scheduler(scheduler, 1, is_real_cpu=False, ram=256)
        add_task_to_scheduler(scheduler, 2, is_real_cpu=False, ram=1024)
        add_task_to_scheduler(scheduler, 3, is_real_cpu=True, ram=256)
        add_task_to_scheduler(scheduler, 4, is_real_cpu=True, ram=1024)
        add_task_to_scheduler(scheduler, 5, is_real_cpu=False, ram=256)
        add_task_to_scheduler(scheduler, 6, is_real_cpu=False, ram=1024)

        scheduled_tasks = scheduler.schedule()

        # Tasks 3 and 4 should block 5 and 6.
        self.assertItemsEqual([(1, 1), (2, 2)], scheduled_tasks)

        scheduler.delTask(1)
        scheduler.delTask(2)
        scheduled_tasks = scheduler.schedule()

        self.assertItemsEqual([(3, 1), (4, 2)], scheduled_tasks)

        scheduler.delTask(3)
        scheduler.delTask(4)
        scheduled_tasks = scheduler.schedule()

        self.assertItemsEqual([(5, 1), (6, 2)], scheduled_tasks)

    def test_should_respect_ram_limits_when_assigning_real_cpu_tasks(self):
        any_cpu_worker_1 = {'id': 1, 'ram': 512, 'is_real_cpu': True}
        any_cpu_worker_2 = {'id': 2, 'ram': 4096, 'is_real_cpu': True}

        scheduler = prioritizing.PrioritizingScheduler(WorkerManagerStub(
            any_cpu_worker_1, any_cpu_worker_2))

        scheduler.addWorker(1)
        scheduler.addWorker(2)

        scheduler.updateContest(contest_uid=1, priority=10, weight=10)

        add_task_to_scheduler(scheduler, 1, is_real_cpu=True, ram=1024)
        add_task_to_scheduler(scheduler, 2, is_real_cpu=True, ram=1024)

        scheduled_tasks = scheduler.schedule()

        # Second task should be blocked.
        self.assertItemsEqual([(1, 2)], scheduled_tasks)

    def test_should_try_to_match_tasks_ram_to_workers_average_ram(self):
        """For more info, check out _getSuitableWorkerForVcpuTask()."""
        vcpu_only_worker_1 = {
            'id': 1, 'concurrency': 4, 'ram': 2048, 'is_real_cpu': False}
        vcpu_only_worker_2 = {
            'id': 2, 'concurrency': 4, 'ram': 8192, 'is_real_cpu': False}

        scheduler = prioritizing.PrioritizingScheduler(WorkerManagerStub(
            vcpu_only_worker_1, vcpu_only_worker_2))

        scheduler.addWorker(1)
        scheduler.addWorker(2)

        scheduler.updateContest(contest_uid=1, priority=10, weight=10)

        # A huge task.
        add_task_to_scheduler(scheduler, 1, is_real_cpu=False, ram=2048)

        # A small task.
        add_task_to_scheduler(scheduler, 2, is_real_cpu=False, ram=16)

        scheduled_tasks = scheduler.schedule()

        self.assertItemsEqual([(1, 2), (2, 1)], scheduled_tasks)

    def test_should_block_more_workers_if_waiting_tasks_are_huge(self):
        any_cpu_worker_1 = {
            'id': 1, 'concurrency': 2, 'ram': 512, 'is_real_cpu': True}
        any_cpu_worker_2 = {
            'id': 2, 'concurrency': 2, 'ram': 2048, 'is_real_cpu': True}
        any_cpu_worker_3 = {
            'id': 3, 'concurrency': 2, 'ram': 8192, 'is_real_cpu': True}

        scheduler = prioritizing.PrioritizingScheduler(WorkerManagerStub(
            any_cpu_worker_1, any_cpu_worker_2, any_cpu_worker_3))

        scheduler.addWorker(1)
        scheduler.addWorker(2)
        scheduler.addWorker(3)

        scheduler.updateContest(contest_uid=1, priority=10, weight=10)

        add_task_to_scheduler(scheduler, 1, is_real_cpu=False, ram=256)
        add_task_to_scheduler(scheduler, 2, is_real_cpu=False, ram=256)
        add_task_to_scheduler(scheduler, 3, is_real_cpu=False, ram=1024)
        add_task_to_scheduler(scheduler, 4, is_real_cpu=False, ram=1024)
        add_task_to_scheduler(scheduler, 5, is_real_cpu=False, ram=4096)
        add_task_to_scheduler(scheduler, 6, is_real_cpu=False, ram=4096)

        scheduled_tasks = scheduler.schedule()

        self.assertEqual(len(scheduled_tasks), 6)

        scheduler.delTask(1)
        scheduler.delTask(3)
        scheduler.delTask(5)

        # Now every worker is partially busy.

        # Real-cpu task that can only be handled by 2 and 3
        add_task_to_scheduler(scheduler, 7, is_real_cpu=True, ram=1024)

        add_task_to_scheduler(scheduler, 8, is_real_cpu=False, ram=256)
        add_task_to_scheduler(scheduler, 9, is_real_cpu=False, ram=256)
        add_task_to_scheduler(scheduler, 10, is_real_cpu=False, ram=256)

        scheduled_tasks = scheduler.schedule()

        # Task 7 should block 2 workers, allowing only one vcpu task
        # to be scheduled.
        self.assertEqual(len(scheduled_tasks), 1)

        # Suppose the task was cancelled.
        scheduler.delTask(7)

        scheduled_tasks = scheduler.schedule()

        # Now it should be OK.
        self.assertEqual(len(scheduled_tasks), 2)


class WorkerManagerStub(object):
    class WorkerDataStub(object):
        def __init__(self, **wdata):
            self.concurrency = wdata.get('concurrency', 4)
            self.available_ram_mb = wdata.get('ram', 4096)
            self.can_run_cpu_exec = wdata.get('is_real_cpu', False)
            self.is_running_cpu_exec = False
            self.tasks = []

    def __init__(self, *workers):
        self.workerData = {
            worker['id']: WorkerManagerStub.WorkerDataStub(**worker)
            for worker in workers
        }

        any_cpus_ram = [
                worker.available_ram_mb
                for _, worker in self.workerData.iteritems()
                if worker.can_run_cpu_exec]

        vcpu_onlys_ram = [
                worker.available_ram_mb
                for _, worker in self.workerData.iteritems()
                if not worker.can_run_cpu_exec]

        self.minAnyCpuWorkerRam = min(any_cpus_ram) if any_cpus_ram else None
        self.maxAnyCpuWorkerRam = max(any_cpus_ram) if any_cpus_ram else None
        self.minVcpuOnlyWorkerRam = (
                min(vcpu_onlys_ram) if vcpu_onlys_ram else None)
        self.maxVcpuOnlyWorkerRam = (
                max(vcpu_onlys_ram) if vcpu_onlys_ram else None)

    def getWorkers(self):
        return self.workerData


def create_worker_info(id=0, concurrency=4, ram=4096, is_real_cpu=False):
    class WorkerDataStub(object):
        def __init__(self):
            self.concurrency = concurrency
            self.available_ram_mb = ram
            self.can_run_cpu_exec = is_real_cpu
            self.is_running_cpu_exec = False
            self.tasks = []

    return prioritizing.WorkerInfo(id, WorkerDataStub())


def create_contest_info(id=0, priority=10, weight=10):
    return prioritizing.ContestInfo(
        contest_uid=id, priority=priority, weight=weight)


# This function can be useful for some helper structure tests,
# but unfortunately scheduler API accepts the env dict directly,
# so it can't be used there.
def create_task_info(id=0,
                     ram=256,
                     is_real_cpu=False,
                     contest=create_contest_info(),
                     priority=0):
    env = {
        'task_id': id,
        'job_type': 'cpu-exec' if is_real_cpu else 'vcpu-exec',
        'exec_mem_limit': ram * 1024,
        'task_priority': priority,
    }

    return prioritizing.TaskInfo(env, contest)


# This function is similar to the one above, but can be used with
# the scheduler API.
def add_task_to_scheduler(scheduler,
                          id,
                          contest_uid=1,
                          is_real_cpu=True,
                          ram=256,
                          priority=0):
    env = {
        'task_id': id,
        'contest_uid': 1,
        'job_type': 'cpu-exec' if is_real_cpu else 'vcpu-exec',
        'exec_mem_limit': ram * 1024,
        'task_priority': priority,
    }

    scheduler.addTask(env)
