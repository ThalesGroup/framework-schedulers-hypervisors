# Copyright (c) 2026 Thales
# This software is released under the MIT License.
# See the LICENSE file in the project root for full license information.

import random
import time
from contextlib import contextmanager
from enum import Enum
import numpy as np


class VCPUState(str, Enum):
    RUNNABLE = "RUNNABLE"
    RUN = "RUN"
    SLEEP = "SLEEP"

class Scheduler:
    def __init__(self, vcpus):
        self.vcpus = vcpus
        self.time_us = 0
        self.history = [] # Tracks scheduling intervals for visualization/analysis
        self.current_vcpu = None
        self._is_measuring = False

    def add_history(self, name):
        # Records execution intervals for vCPUs, merging back-to-back blocks.
        if not self.history or self.history[-1]["name"] != name:
            self.history.append({
                "name": name,
                "start": round(self.time_us, 3),
                "end": round(self.time_us + 1, 3)
            })
        else:
            self.history[-1]["end"] += 1
    
    def update_vcpu_states(self):
        """Standard management of asynchronous vCPU wake-ups and sleeps."""
        for v in self.vcpus:
            was_sleeping = (v.state == VCPUState.SLEEP)
            v.update_state(self.time_us)
            if was_sleeping and v.state == VCPUState.RUNNABLE:
                self.wake(v)
            elif not was_sleeping and v.state == VCPUState.SLEEP:
                self.sleep(v)

    # ---------------------------------------------------------
    # ABSTRACT METHODS (To be implemented by child classes)
    # ---------------------------------------------------------
    def wake(self, v):
        raise NotImplementedError("Each scheduler must implement the wake() method.")

    def sleep(self, v):
        raise NotImplementedError("Each scheduler must implement the sleep() method.")
    
    def pick_next(self):
        raise NotImplementedError("Each scheduler must implement the pick_next() method.")
    
    def tick(self):
        raise NotImplementedError("Each scheduler must implement the tick() method.")

class VCPU:
    # Simulates a vCPU with specific workloads (CPU-bound, IO, or Real-Time).
    def __init__(self, name, behavior="cpu", **kwargs):
        self.name = name
        self.behavior = behavior # Options: "cpu", "io", "rt"
        self.remaining_work = 0
        self.wakeup_times = []
        self.work_history = []
        self.state = VCPUState.RUNNABLE
        
        # Dynamically map extra attributes (e.g., period, target_run_time, mean_interval)
        for key, value in kwargs.items():
            setattr(self, key, value)
        if self.behavior == "rt":
            self.offset = random.randint(0, 999)
        if self.behavior != "cpu":
            self.next_wakeup = getattr(self, 'offset', 0)
            self.wakeup_times.append(self.next_wakeup)
            self.state = VCPUState.SLEEP 
        else:
            self.next_wakeup = 0
            self.state = VCPUState.RUNNABLE

    @classmethod
    def from_config(cls, config):
        config = dict(config)
        behavior = config.pop("behavior", "cpu")
        vcpu_class = {
            "cpu": CPUVCPU,
            "io": IOVCPU,
            "rt": RTVCPU,
        }.get(behavior, VCPU)
        return vcpu_class(**config)

    def consume_execution_tick(self):
        return None


    def update_state(self, current_time):
        return None


class CPUVCPU(VCPU):
    def __init__(self, name, **kwargs):
        super().__init__(name, behavior="cpu", **kwargs)


class IOVCPU(VCPU):
    def __init__(self, name, **kwargs):
        super().__init__(name, behavior="io", **kwargs)

    def consume_execution_tick(self):
        if self.remaining_work > 0:
            self.remaining_work -= 1

    def update_state(self, current_time):
        if current_time >= self.next_wakeup:
            lambda_ = 1.0 / self.mean_interval
            delay = random.expovariate(lambda_)
            self.next_wakeup = current_time + delay
            self.wakeup_times.append(self.next_wakeup)
            self.remaining_work += self.target_run_time
            if self.state == VCPUState.SLEEP:
                self.state = VCPUState.RUNNABLE
        elif self.remaining_work <= 0:
            self.state = VCPUState.SLEEP


class RTVCPU(VCPU):
    def __init__(self, name, **kwargs):
        super().__init__(name, behavior="rt", **kwargs)

    def consume_execution_tick(self):
        if self.remaining_work > 0:
            self.remaining_work -= 1

    def update_state(self, current_time):
        if current_time >= self.next_wakeup:
            self.remaining_work += random.randint(int(0.5 * self.target_run_time), self.target_run_time)
            self.work_history.append(self.remaining_work)
            self.next_wakeup += self.period
            self.wakeup_times.append(self.next_wakeup)
            if self.state == VCPUState.SLEEP:
                self.state = VCPUState.RUNNABLE
        elif self.remaining_work <= 0:
            self.state = VCPUState.SLEEP
