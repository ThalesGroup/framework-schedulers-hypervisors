# Copyright (c) 2026 Thales
# This software is released under the MIT License.
# See the LICENSE file in the project root for full license information.

from core import Scheduler, VCPUState
import config
from rbtree import RBTree

# =============================================
# Cyclic scheduler
# =============================================
class CyclicScheduler(Scheduler):
    """
    Config link from `config.py`:
    - `cycle_config`: required scheduler layout, as a list of `(vm_name, duration)` pairs.

    Each slot is fixed for the whole simulation and the scheduler simply maps
    the current simulation time into the active slot.
    """
    def __init__(self, vcpus, cycle_config, **kwargs):
        super().__init__(vcpus)
        self.cycle_config = cycle_config
        # A major frame represents the total duration of one full cycle
        self.major_frame = sum(duration for _, duration in cycle_config)
        self.schedule_table = []
        # Build the static execution matrix with precise start/end time windows
        current_offset = 0
        for vm_name, duration in cycle_config:
            vm_obj = next((v for v in self.vcpus if v.name == vm_name), None)
            self.schedule_table.append({
                "start": current_offset,
                "end": current_offset + duration,
                "vm": vm_obj
            })
            current_offset += duration
        self.next_timer_interrupt = 0
        self.need_resched = False

    def wake(self, v):
        v.state = VCPUState.RUNNABLE
        self.need_resched = True
        pass

    def sleep(self, v):
        v.state = VCPUState.SLEEP
        self.need_resched = True
        if self.current_vcpu == v:
            self.current_vcpu = None
        pass

    def pick_next(self):
        # Map the absolute simulation time to its position inside the current cycle
        current_time_in_cycle = self.time_us % self.major_frame
        scheduled_vm = None
        # Find which static time slot matches the current cycle progression
        for slot in self.schedule_table:
            if slot["start"] <= current_time_in_cycle < slot["end"]:
                scheduled_vm = slot["vm"]
                # Program the next interrupt at the end boundary of this slot
                self.next_timer_interrupt = self.time_us + (slot["end"] - current_time_in_cycle)
                break
        if scheduled_vm and (scheduled_vm.state == VCPUState.RUNNABLE or scheduled_vm.state == VCPUState.RUN):
            return scheduled_vm
        return None

    def tick(self):
        prev_vcpu = self.current_vcpu
        self.need_resched = False

        # 1. Update vCPU states & process asynchronous wake/sleep transitions
        self.update_vcpu_states()

        # 2. Execution
        if self.current_vcpu:
            self.current_vcpu.consume_execution_tick()

        # 3. Hardware timer interrupt
        if self.time_us > self.next_timer_interrupt:
            self.need_resched = True
        
        # 4. Scheduling decision and context switch execution
        if self.need_resched:
            self.current_vcpu = self.pick_next()
            if self.current_vcpu != prev_vcpu:
                if prev_vcpu is not None and prev_vcpu.state == VCPUState.RUN:
                    prev_vcpu.state = VCPUState.RUNNABLE
            if self.current_vcpu is not None:
                self.current_vcpu.state = VCPUState.RUN
        
        # 4. History tracking & time progression
        name = self.current_vcpu.name if self.current_vcpu else "IDLE"
        self.add_history(name)
        self.time_us += 1

# =============================================
# Credit scheduler
# =============================================

class CreditScheduler(Scheduler):
    """
    Config link from `config.py`:
    - `weight`: scheduler-facing field used to initialize credit shares per vCPU.

    Credits are replenished every accounting period and the runqueue is ordered
    by priority bands. Waking vCPUs may receive a boost so that interactive or
    newly ready workloads preempt more quickly.
    """
    def __init__(self, vcpus, **kwargs):
        super().__init__(vcpus)
        self.runqueue = []
        self.total_weight = sum(getattr(v, 'weight', 256) for v in self.vcpus if v.state in [VCPUState.RUNNABLE, VCPUState.RUN])
        self.accounting_period = config.CSCHED_DEFAULT_TSLICE_US
        self.accounting_timer = self.accounting_period
        self.need_resched = False
        self.current_running_time = 0
        # Distribute original credits proportionally based on vCPU weights
        for v in self.vcpus:
            v.weight = getattr(v, 'weight', 256)
            if self.total_weight > 0:
                v.credit = (config.CREDITS_PER_SLICE * v.weight + self.total_weight - 1) // self.total_weight
            else:
                v.credit = 0
            v.pri = config.PRIO_UNDER
            if v.state == VCPUState.RUNNABLE:
                self.wake(v)
            v.start_time = 0
            v.residual = 0

    def csched_sort_runqueue(self):
        # Strict sorting by priority band. VMs within the same band are treated FIFO
        self.runqueue.sort(key=lambda v: getattr(v, 'pri', -2), reverse=True)
    
    def csched_burn_credits(self, v, current_time):
        # Deduct credits based on the actual wall-clock execution time elapsed
        delta = current_time - getattr(v, 'start_time', current_time)
        if delta <= 0:
            return
        val = delta * config.CREDITS_PER_MSEC + getattr(v, 'residual', 0)
        credits_to_burn = val // 1000
        v.residual = val % 1000 # Save sub-millisecond fractions for the next burn
        v.credit -= credits_to_burn
        v.start_time =current_time


    def wake(self, v, boost=False):
        # Determine the target priority band based on current credit health or wake-up signals
        if boost:
            v.pri = config.PRIO_BOOST
        elif v.credit >= 0:
            v.pri = config.PRIO_UNDER
        else:
            v.pri = config.PRIO_OVER
        # O(N) ordered insertion to keep the runqueue sorted by priority bands
        inserted = False
        for i, vcpu in enumerate(self.runqueue):
            if vcpu.pri < v.pri:
                self.runqueue.insert(i, v)
                inserted = True
                break
        if not inserted:
            self.runqueue.append(v)
        v.state = VCPUState.RUNNABLE
        self.need_resched = True

    def sleep(self, v):
        if v in self.runqueue:
            self.runqueue.remove(v)
        v.state = VCPUState.SLEEP
        self.need_resched = True

    def pick_next(self):
        return self.runqueue[0] if self.runqueue else None

    def tick(self):
        self.need_resched = False
        prev_vcpu = self.current_vcpu

        # 1. Global accounting replenishment interval
        self.accounting_timer -= 1
        if self.accounting_timer <= 0:
            self.accounting_timer = self.accounting_period
            active = [v for v in self.vcpus if v.state == VCPUState.RUNNABLE or v.state == VCPUState.RUN]
            weight_active = sum(getattr(v, 'weight', 256) for v in active)
            credit_peak = config.CREDITS_PER_SLICE
            # Redistribute fair credits to active vCPUs based on active weights
            for v in active:
                if weight_active > 0:
                    credit_fair = (config.CREDITS_PER_SLICE*v.weight+weight_active-1)//weight_active
                else:
                    credit_fair = 0
                if credit_fair > credit_peak:
                    credit_fair = credit_peak
                v.credit += credit_fair
                # Recalculate priority band caps based on new credit balance
                if v.credit < 0:
                    v.pri = config.PRIO_OVER
                    if v.credit < -config.CREDITS_PER_SLICE:
                        v.credit = -config.CREDITS_PER_SLICE # Cap credit deficit to prevent starvation lock
                else:
                    v.pri = config.PRIO_UNDER
                    if v.credit > config.CREDITS_PER_SLICE:
                        v.credit //= 2 # Hoarding mitigation
            self.csched_sort_runqueue()

        # 2. Update vCPU states & process asynchronous wake/sleep transitions
        for v in self.vcpus:
            was_sleeping = (v.state == VCPUState.SLEEP)
            v.update_state(self.time_us)
            
            if was_sleeping and v.state == VCPUState.RUNNABLE:
                self.wake(v, boost=True)
            elif not was_sleeping and v.state == VCPUState.SLEEP:
                self.sleep(v)

        # 3. Execution
        if self.current_vcpu:
            self.current_vcpu.consume_execution_tick()
            self.current_running_time += 1
            # Preemption check: trigger switch if a higher priority VM is waiting at the head
            if self.current_running_time >= config.CREDIT_CONTEXT_SWITCH_LIMIT and len(self.runqueue) > 0 and self.runqueue[0].pri > self.current_vcpu.pri:
                self.need_resched = True

        # 4. Hardware timer interrupt
        if self.time_us % config.CSCHED_TICK_PERIOD_US == 0:
            if self.current_vcpu:
                if self.current_vcpu.pri == config.PRIO_BOOST:
                    self.current_vcpu.pri = config.PRIO_UNDER
                self.csched_burn_credits(self.current_vcpu, self.time_us)
                    
        # 5. Scheduling decision and context switch execution
        if self.need_resched:
            candidate = self.pick_next()
            # Enforce context switch rate-limiting to prevent excessive thrashing
            if self.current_vcpu and self.current_vcpu.state != VCPUState.SLEEP and self.current_running_time < config.CREDIT_CONTEXT_SWITCH_LIMIT:
                candidate = self.current_vcpu
            self.current_vcpu = candidate

            if self.current_vcpu != prev_vcpu:
                self.current_running_time = 0
                if prev_vcpu is not None:
                    self.csched_burn_credits(prev_vcpu, self.time_us)
                    if prev_vcpu.state != VCPUState.SLEEP:
                        self.sleep(prev_vcpu)
                        self.wake(prev_vcpu, boost=False)
                if self.current_vcpu is not None:
                    self.current_vcpu.start_time = self.time_us
            if self.current_vcpu is not None:
                self.current_vcpu.state = VCPUState.RUN

        # 6. History tracking & time progression
        name = self.current_vcpu.name if self.current_vcpu else "IDLE"
        self.add_history(name)
        self.time_us += 1

# =============================================
# Credit2 scheduler
# =============================================

class Credit2Scheduler(Scheduler):
    """
    Config link from `config.py`:
    - `weight`: scheduler-facing field used to compute credit decay and runtime bias.

    It uses a per-vCPU runtime timer
    derived from the credit lead over the next runnable candidate. It is meant
    to model a more dynamic credit-based policy.
    """

    def __init__(self, vcpus, **kwargs):
        super().__init__(vcpus)
        self.runqueue = []
        self.need_resched = False
        self.current_running_time = 0
        for v in self.vcpus:
            v.weight = getattr(v, 'weight', 256)
            v.credit = config.CSCHED2_CREDIT_INIT
            v.residual = 0
            v.runtime_timer = 0
            v.start_time = 0
            if v.state == VCPUState.RUNNABLE:
                self.wake(v)
        self.max_weight = max((getattr(v, 'weight', 256) for v in self.vcpus))

    def csched2_burn_credits(self, v, current_time):
        # Burn rate is inversely proportional to weight: higher weight = slower credit consumption
        delta_us = current_time - v.start_time
        if delta_us <= 0:
            return
        delta_ns = delta_us * 1000 
        val = (delta_ns * self.max_weight) + v.residual
        credits_to_burn = val // v.weight
        v.residual = val % v.weight
        v.credit -= credits_to_burn
        if v.credit < config.CSCHED2_CREDIT_MIN:
            v.credit = config.CSCHED2_CREDIT_MIN
        v.start_time = 0

    def insert_runqueue(self, v):
        if v in self.runqueue:
            self.runqueue.remove(v)
        # Credit2 queues are sorted descendingly by remaining credit values
        inserted = False
        for i, current_v in enumerate(self.runqueue):
            if v.credit > current_v.credit:
                self.runqueue.insert(i, v)
                inserted = True
                break
        if not inserted:
            self.runqueue.append(v)
        
    def remove_runqueue(self, v):
        try:
            self.runqueue.remove(v)
        except ValueError:
            pass
    
    def csched2_runtime(self, prev_vcpu, next_vcpu):
        # Calculates a custom variable timeslice based on credit lead over the runner-up.
        rt_credit = next_vcpu.credit
        if self.runqueue:
            next_best = self.runqueue[0] 
            if next_best.credit > 0:
                rt_credit -= next_best.credit
        if rt_credit > 0:
            time_ns = (rt_credit * next_vcpu.weight) // self.max_weight
        else :
            time_ns = 0
        time_us = time_ns // 1000
        # Enforce structural min/max scheduler runtime boundary conditions
        min_time = config.CSCHED2_MIN_TIMER
        rate_limit = config.CSCHED2_CONTEXT_SWITCH_LIMIT
        if prev_vcpu == next_vcpu:
            rate_limit -= self.current_running_time
        if rate_limit > min_time:
            min_time = rate_limit
        if time_us < min_time:
            return min_time
        elif time_us > config.CSCHED2_MAX_TIMER:
            return config.CSCHED2_MAX_TIMER
        return time_us
    
    def reset_credits(self, next_vcpu):
        # Global system credit reset triggered when any active vCPUs runs out of credits
        reset_amount = config.CSCHED2_CREDIT_INIT
        if next_vcpu.credit <= config.CSCHED2_CREDIT_MIN:
            reset_amount += config.CSCHED2_CREDIT_INIT
        max_credit_allowed = config.CSCHED2_CREDIT_INIT + config.CSCHED2_CARRYOVER_MAX
        for v in self.vcpus:
            v.credit += reset_amount
            if v.credit > max_credit_allowed:
                v.credit = max_credit_allowed

    def wake(self, v):
        if v.state == VCPUState.RUN or v in self.runqueue:
            return
        self.insert_runqueue(v)
        v.state = VCPUState.RUNNABLE
        self.need_resched = True

    def sleep(self, v):
        self.remove_runqueue(v)
        v.state = VCPUState.SLEEP
        self.need_resched = True

    def pick_next(self, current_v):
        # Prevent preemption if current vCPU has not executed for the minimum switch threshold
        if current_v is not None and current_v.state != VCPUState.SLEEP:
            if self.current_running_time < config.CSCHED2_CONTEXT_SWITCH_LIMIT:
                return current_v
        next_best = self.runqueue[0] if self.runqueue else None
        if next_best is not None and current_v is not None and current_v.state != VCPUState.SLEEP:
            if current_v.credit >= next_best.credit:
                return current_v
        if next_best is None and current_v is not None and current_v.state != VCPUState.SLEEP:
            return current_v
        return next_best

    def tick(self):
        prev_vcpu = self.current_vcpu
        self.need_resched = False
                            
        # 1. Update vCPU states & process asynchronous wake/sleep transitions
        self.update_vcpu_states()

        # 2. Execution
        if self.current_vcpu :
            self.current_vcpu.consume_execution_tick()
            self.current_vcpu.runtime_timer -= 1 # Deplete the custom variable timeslice
            self.current_running_time += 1
            if self.current_vcpu.runtime_timer <= 0:
                self.need_resched = True
        else:
            self.need_resched = True

        # 3. Scheduling decision and context switch execution
        if self.need_resched:
            if self.current_vcpu is not None:
                self.csched2_burn_credits(self.current_vcpu, self.time_us)
            candidate = self.pick_next(self.current_vcpu)
            if candidate is not None and candidate.credit <= 0:
                self.reset_credits(candidate)
            self.current_vcpu = candidate
            if self.current_vcpu is not None:
                self.current_vcpu.state = VCPUState.RUN
                self.remove_runqueue(self.current_vcpu)
                self.current_vcpu.start_time = self.time_us
                if prev_vcpu is not None and prev_vcpu.state != VCPUState.SLEEP and prev_vcpu != self.current_vcpu:
                    self.insert_runqueue(prev_vcpu)
                    prev_vcpu.state = VCPUState.RUNNABLE
                elif prev_vcpu is not None and prev_vcpu != self.current_vcpu:
                    self.sleep(prev_vcpu)
                self.current_vcpu.runtime_timer = self.csched2_runtime(prev_vcpu,self.current_vcpu)
            if self.current_vcpu != prev_vcpu:
                self.current_running_time = 0
                if prev_vcpu is not None:
                    prev_vcpu.runtime_timer = 0
                
        # 4. History tracking & time progression
        name = self.current_vcpu.name if self.current_vcpu else "IDLE"
        self.add_history(name)
        self.time_us += 1

# =============================================
# RTDS scheduler
# =============================================
class RTDSScheduler(Scheduler):
    """
    Config link from `config.py`:
    - `period`: periodic replenishment interval.
    - `budget`: execution budget granted at each period.
    - `extratime`: scheduler flag enabling work-conserving behavior.

    When a budget is exhausted the vCPU is either blocked until the next period
    or, if `extratime` is enabled, allowed to continue in a work-conserving
    mode. The runqueue is ordered by priority level and deadline.
    """

    def __init__(self, vcpus, **kwargs):
        super().__init__(vcpus)
        self.runqueue = []
        self.need_resched = False
        for v in self.vcpus:
            # The extratime flag determines if the scheduler acts as work-conserving
            if not hasattr(v, 'extratime'):
                v.extratime = False
            v.cur_budget = v.budget
            v.cur_deadline = self.time_us + v.period
            v.priority_level = 0
            v.is_depleted = False  
            if v.state == VCPUState.RUNNABLE:
                self.wake(v)
        self.next_timer = min((v.cur_deadline for v in self.vcpus), default=0)
    def wake(self, v):
        # Strict EDF sorting hierarchy: priority_level first, then earliest deadline
        inserted = False
        if v.cur_budget > 0 or v.extratime:
            for i, vcpu in enumerate(self.runqueue):
                if (vcpu.priority_level > v.priority_level) or \
                (vcpu.priority_level == v.priority_level and vcpu.cur_deadline > v.cur_deadline):
                    self.runqueue.insert(i, v)
                    inserted = True
                    break
            if not inserted:
                self.runqueue.append(v)
            v.state = VCPUState.RUNNABLE
            self.need_resched = True

    def sleep(self, v):
        if v in self.runqueue:
            self.runqueue.remove(v)
        v.state = VCPUState.SLEEP
        self.need_resched = True

    def pick_next(self):
        return self.runqueue[0] if self.runqueue else None

    def tick(self):
        prev_vcpu = self.current_vcpu
        self.need_resched = False

        # 1. Update vCPU states & process asynchronous wake/sleep transitions
        self.update_vcpu_states()

        # 2. Replenishment budget
        if self.time_us == self.next_timer:
            for v in self.vcpus:
                if self.time_us >= v.cur_deadline:
                    while self.time_us >= v.cur_deadline:
                        v.cur_deadline += v.period
                    v.cur_budget = v.budget
                    v.priority_level = 0
                    if v.is_depleted:
                        v.is_depleted = False
                        if v.state != VCPUState.SLEEP:
                            self.wake(v)
                    elif v in self.runqueue:
                        self.runqueue.remove(v)
                        self.wake(v)
            self.next_timer = min((v.cur_deadline for v in self.vcpus))

        # 3. Execution
        if self.current_vcpu:
            self.current_vcpu.consume_execution_tick()
            self.current_vcpu.cur_budget -= 1
                
            if self.current_vcpu.cur_budget <= 0:
                if getattr(self.current_vcpu, 'extratime', False):
                    # Work-conserving expansion mode: demote priority and refill budget to utilize unreserved idle slots
                    self.current_vcpu.priority_level += 1
                    self.current_vcpu.cur_budget = self.current_vcpu.budget
                    self.sleep(self.current_vcpu)
                    self.wake(self.current_vcpu)
                else:
                    # Non-work-conserving standard: block the vCPU until its next tracking period
                    self.current_vcpu.is_depleted = True
                    if self.current_vcpu in self.runqueue:
                        self.runqueue.remove(self.current_vcpu)
                    self.current_vcpu.state = VCPUState.RUNNABLE
                    self.need_resched = True

        # 4. Scheduling decision and context switch execution
        if self.need_resched:
            self.current_vcpu = self.pick_next()
            if self.current_vcpu != prev_vcpu:
                if prev_vcpu is not None and prev_vcpu.state == VCPUState.RUN:
                    prev_vcpu.state = VCPUState.RUNNABLE
            if self.current_vcpu is not None:
                self.current_vcpu.state = VCPUState.RUN
        
        # 5. History tracking & time progression
        name = self.current_vcpu.name if self.current_vcpu else "IDLE"
        self.add_history(name)
        self.time_us += 1

# =============================================
# Priority-based scheduler
# =============================================
class PriorityScheduler(Scheduler):
    """
    Config link from `config.py`:
    - `priority`: required ordering key used to sort the runqueue.
    - `time_slice`: per-vCPU preemption threshold.

    vCPUs are kept in a FIFO list ordered by priority value. Higher priority
    values are selected first, and a time-slice threshold drives preemption.
    """

    def __init__(self, vcpus, **kwargs):
        super().__init__(vcpus)
        self.runqueue = []
        self.need_resched = False
        for v in self.vcpus:
            if v.state == "RUNNABLE":
                self.wake(v)

    def wake(self, v):
        # Keeps queue descendingly ordered by priority rating counters
        inserted = False
        for i, vcpu in enumerate(self.runqueue):
            if vcpu.priority < v.priority:
                self.runqueue.insert(i, v)
                inserted = True
                break
        if not inserted:
            self.runqueue.append(v)
        v.state = VCPUState.RUNNABLE
        self.need_resched = True

    def sleep(self, v):
        if v in self.runqueue:
            self.runqueue.remove(v)
        v.state = VCPUState.SLEEP
        self.need_resched = True

    def pick_next(self):
        return self.runqueue[0] if self.runqueue[0] else None

    def tick(self):
        prev_vcpu = self.current_vcpu
        self.need_resched = False

        # 1. Update vCPU states & process asynchronous wake/sleep transitions
        self.update_vcpu_states()
        
        # 2. Execution
        if self.current_vcpu:
            self.current_vcpu.consume_execution_tick()

        # 3. Scheduling decision and context switch execution
        if self.need_resched:
            self.current_vcpu = self.pick_next()
            if self.current_vcpu != prev_vcpu:
                if prev_vcpu is not None and prev_vcpu.state == VCPUState.RUN:
                    prev_vcpu.state = VCPUState.RUNNABLE
            if self.current_vcpu is not None:
                self.current_vcpu.state = VCPUState.RUN
        
        # 4. History tracking & time progression
        name = self.current_vcpu.name if self.current_vcpu else "IDLE"
        self.add_history(name)
        self.time_us += 1

# =============================================
# BVT scheduler
# =============================================

class BVTScheduler(Scheduler):
    """
    Config link from `config.py`:
    - `weight`: fairness weight used to derive the virtual-time ratio.

    Each vCPU tracks actual and effective virtual time. The next vCPU is chosen
    by the smallest effective virtual time.
    """

    def __init__(self, vcpus, **kwargs):
        super().__init__(vcpus)
        self.runqueue = []
        # Scheduler Virtual Time (SVT) tracks the minimum AVT of any runnable thread
        self.svt = 0 
        self.need_resched = False
        self.next_timer = 0
        for v in self.vcpus:
            v.avt = 0 # Actual Virtual Time (unbiased progression tracking)
            v.evt = 0 # Effective Virtual Time (AVT adjusted by latency borrowing offsets)
            v.vt_ratio = config.BVT_VT_RATIO_MAX // getattr(v, 'weight', 64)
            v.start_time = 0
            if v.state == "RUNNABLE":
                self.wake(v)

    def wake(self, v):
        # Prevent penalizing long-sleeping vCPUs by capping their AVT catch-up jump threshold
        threshold = self.svt - (config.BVT_CSA_MCU*v.vt_ratio)
        if v.avt <= threshold:
            v.avt = self.svt
        v.evt = v.avt
        self.runqueue_add(v)
        v.state = VCPUState.RUNNABLE
        self.need_resched = True

    def sleep(self, v):
        if v in self.runqueue:
            self.runqueue.remove(v)
        v.state = VCPUState.SLEEP
        self.need_resched = True

    def pick_next(self):
        if self.current_vcpu:
            self.update_vt(self.current_vcpu)
        self.update_svt()
        self.next_timer = 0
        if self.runqueue:
            first = self.runqueue[0]
            second = self.runqueue[1] if len(self.runqueue) > 1 else None
            if second:
                delta = second.evt - first.evt
                run_countdown = delta/first.vt_ratio + config.BVT_CSA_MCU
            else:
                run_countdown = config.UINT64_MAX
            first.start_time = self.time_us
            next = first
            if run_countdown != config.UINT64_MAX:
                self.next_timer = self.time_us + int(run_countdown)
        else:
            next = None
        return next
    
    def update_vt(self, v):
        if v is None:
            return
        delta = 0
        if self.time_us > v.start_time:
            # Advance virtual time proportionally to the execution duration and vCPU's ratio
            delta = (self.time_us - v.start_time) * v.vt_ratio
        v.avt += delta
        v.evt = v.avt
        if v in self.runqueue:
            self.runqueue.remove(v)
            self.runqueue_add(v) # Re-insert to fix sorting order alterations
    
    def update_svt(self):
        if self.runqueue:
            temp = self.runqueue[0]
            self.svt = temp.avt
        
    def runqueue_add(self, v):
        # Always ordered ascendingly by Effective Virtual Time (EVT) values
        if not self.runqueue:
            self.runqueue.append(v)
            return
        else:
            for i, vcpu in enumerate(self.runqueue):
                if vcpu.evt > v.evt:
                    self.runqueue.insert(i, v)
                    return
            self.runqueue.append(v)
                
    def tick(self):
        self.need_resched = False
        prev_vcpu = self.current_vcpu

        # 1. Update vCPU states & process asynchronous wake/sleep transitions
        self.update_vcpu_states()

        # 2. Execution
        if self.current_vcpu:
            self.current_vcpu.consume_execution_tick()

        # 3. Hardware timer interrupt
        if self.time_us == self.next_timer:
            if self.current_vcpu is None:
                self.need_resched = True
            elif self.runqueue :
                self.need_resched = True

        # 4. Scheduling decision and context switch execution
        if self.need_resched:
            self.current_vcpu = self.pick_next()
            if self.current_vcpu != prev_vcpu:
                if prev_vcpu is not None and prev_vcpu.state == VCPUState.RUN:
                    prev_vcpu.state = VCPUState.RUNNABLE
            if self.current_vcpu is not None:
                self.current_vcpu.state = VCPUState.RUN
        
        # 5. History tracking & time progression
        name = self.current_vcpu.name if self.current_vcpu else "IDLE"
        self.add_history(name)
        self.time_us += 1

# =============================================
# IORR scheduler
# =============================================
CONFIG_SLICE_US = 10000

class IORRScheduler(Scheduler):
    """
        Config link from `config.py`:
        - No scheduler-specific extra field is required.

        Every runnable vCPU gets a fixed slice and the queue is rotated so that a
        runnable vCPU reaching the end of its slice is moved to the tail.
    """

    def __init__(self, vcpus, **kwargs):
        super().__init__(vcpus)
        self.runqueue = []
        self.slice_us = CONFIG_SLICE_US 
        for v in self.vcpus:
            v.slice = self.slice_us
            if v.state == VCPUState.RUNNABLE:
                self.wake(v)
        self.need_resched = False

    def wake(self, v):
        v.slice = self.slice_us
        if v not in self.runqueue:
            self.runqueue.insert(0, v)
        v.state = VCPUState.RUNNABLE
        self.need_resched = True

    def sleep(self, v):
        if v in self.runqueue:
            self.runqueue.remove(v)
        v.state = VCPUState.SLEEP
        self.need_resched = True

    def pick_next(self):
        return self.runqueue[0] if self.runqueue else None

    def tick(self):
        self.need_resched = False
        prev_vcpu = self.current_vcpu

        # 1. Update vCPU states & process asynchronous wake/sleep transitions
        self.update_vcpu_states()

        # 2. Execution
        if self.current_vcpu:
            self.current_vcpu.consume_execution_tick()
            self.current_vcpu.slice -= 1
                
            if self.time_us % 1000 == 0:
                if self.current_vcpu.slice <= 0:
                    self.need_resched = True
                    self.current_vcpu.slice = self.slice_us
                    if self.current_vcpu in self.runqueue:
                        self.runqueue.remove(self.current_vcpu)
                    # The vCPU is rotated to the TAIL of the queue, ensuring basic 
                    # fair CPU sharing among background CPU-bound VMs.
                    self.runqueue.append(self.current_vcpu)

        # 3. Scheduling decision and context switch execution
        if self.need_resched:
            self.current_vcpu = self.pick_next()
            if self.current_vcpu != prev_vcpu:
                if prev_vcpu is not None and prev_vcpu.state == VCPUState.RUN:
                    prev_vcpu.state = VCPUState.RUNNABLE
            if self.current_vcpu is not None:
                self.current_vcpu.state = VCPUState.RUN

        # 4. History tracking & time progression
        name = self.current_vcpu.name if self.current_vcpu else "IDLE"
        self.add_history(name)
        self.time_us += 1

# =============================================
# Priority-based scheduler
# =============================================
class PRRScheduler(Scheduler):
    """
    Config link from `config.py`:
    - `priority`: per-vCPU scheduling key.
    - `time_slice`: per-vCPU preemption threshold.

    The runqueue is partitioned into one Round-Robin queue per priority level. The
    scheduler always scans from highest to lowest priority.
    """

    def __init__(self, vcpus, **kwargs):
        super().__init__(vcpus)
        self.max_priority = 255
        self.runqueue = {p: [] for p in range(self.max_priority + 1)}
        self.need_resched = False
        self.current_running_time = 0
        for v in self.vcpus:
            if v.state == "RUNNABLE":
                self.wake(v)
    def insert_runqueue(self, vcpu):
        if vcpu not in self.runqueue[vcpu.priority]:
            self.runqueue[vcpu.priority].append(vcpu)
    def remove_runqueue(self, vcpu):
        if vcpu in self.runqueue[vcpu.priority]:
            self.runqueue[vcpu.priority].remove(vcpu)
    def wake(self, v):
        self.insert_runqueue(v)
        v.state = "RUNNABLE"
        self.need_resched = True

    def sleep(self, v):
        self.remove_runqueue(v)
        v.state = VCPUState.SLEEP
        self.need_resched = True

    def pick_next(self):
        for p in range(self.max_priority, -1, -1):
            if self.runqueue[p]:
                return self.runqueue[p][0]
        return None

    def tick(self):
        prev_vcpu = self.current_vcpu
        self.need_resched = False

        # 1. Update vCPU states & process asynchronous wake/sleep transitions
        self.update_vcpu_states()
        
        # 2. Execution
        if self.current_vcpu:
            self.current_running_time += 1
            self.current_vcpu.consume_execution_tick()

        # 3. Time slice expiration check
        if self.current_vcpu:
            if self.current_running_time >= self.current_vcpu.time_slice:
                self.need_resched = True

        # 4. Scheduling decision and context switch execution
        if self.need_resched:
            self.current_vcpu = self.pick_next()
            if self.current_vcpu != prev_vcpu:
                self.current_running_time = 0
                if prev_vcpu is not None and prev_vcpu.state == VCPUState.RUN:
                    prev_vcpu.state = VCPUState.RUNNABLE
                    self.remove_runqueue(prev_vcpu)
                    self.insert_runqueue(prev_vcpu)
            if self.current_vcpu is not None:
                self.current_vcpu.state = VCPUState.RUN
        
        # 5. History tracking & time progression
        name = self.current_vcpu.name if self.current_vcpu else "IDLE"
        self.add_history(name)
        self.time_us += 1

class PRMScheduler(Scheduler):
    """
    Config link from `config.py`:
    - `priority`: per-vCPU scheduling key.
    - `time_slice`: per-vCPU preemption threshold.

    Each priority band owns a balanced tree ordered by deadline,
    which keeps insertion and removal efficient when many runnable vCPUs share
    the same priority class.
    """

    def __init__(self, vcpus, **kwargs):
        super().__init__(vcpus)
        self.max_priority = 255
        self.runqueue = {p: RBTree() for p in range(self.max_priority + 1)}
        self.need_resched = False
        self.current_running_time = 0
        for v in self.vcpus:
            if v.state == VCPUState.RUNNABLE:
                self.wake(v)

    def insert_runqueue(self, vcpu):
        self.runqueue[vcpu.priority].insert(vcpu)

    def remove_runqueue(self, vcpu):
        self.runqueue[vcpu.priority].remove(vcpu)

    def wake(self, v):
        self.insert_runqueue(v)
        v.state = VCPUState.RUNNABLE
        self.need_resched = True

    def sleep(self, v):
        self.remove_runqueue(v)
        v.state = VCPUState.SLEEP
        self.need_resched = True

    def pick_next(self):
        for p in range(self.max_priority, -1, -1):
            if self.runqueue[p].root is not None:
                first_node = self.runqueue[p].rb_first()
                if first_node:
                    return first_node.vcpu
        return None

    def tick(self):
        # 1. Update vCPU states & process asynchronous wake/sleep transitions
        prev_vcpu = self.current_vcpu
        self.need_resched = False
        self.update_vcpu_states()
        
        # 2. Execution
        if self.current_vcpu:
            self.current_running_time += 1
            self.current_vcpu.consume_execution_tick()

        # 3. Time slice management
        if self.current_vcpu:
            if self.current_running_time >= self.current_vcpu.time_slice:
                self.need_resched = True

        # 4. Scheduling decision and context switch execution
        if self.need_resched:
            self.current_vcpu = self.pick_next()
            if self.current_vcpu != prev_vcpu:
                self.current_running_time = 0
                if prev_vcpu is not None and prev_vcpu.state == VCPUState.RUN:
                    prev_vcpu.state = VCPUState.RUNNABLE
                    self.remove_runqueue(prev_vcpu)
                    self.insert_runqueue(prev_vcpu)
            if self.current_vcpu is not None:
                self.current_vcpu.state = VCPUState.RUN
        
        # 5. History tracking & time progression
        name = self.current_vcpu.name if self.current_vcpu else "IDLE"
        self.add_history(name)
        self.time_us += 1