# Copyright (c) 2026 Thales
# This software is released under the MIT License.
# See the LICENSE file in the project root for full license information.

from core import VCPU, CPUVCPU, IOVCPU, RTVCPU
import numpy as np
import scipy.stats as stats
import math
import random

def analyze_scheduling_performance(sched, sim_duration):
    # Parses scheduler history tracks to extract statistical evaluation metrics.
    history = sched.history
    vms = sched.vcpus
    
    # 1. Raw CPU utilization
    cpu_counts = {}
    for block in history:
        name = block["name"]
        duration = block["end"] - block["start"] 
        cpu_counts[name] = cpu_counts.get(name, 0) + duration
        
    # 2. Context switches measurement
    switches = len(history) - 1 if len(history) > 0 else 0
            
    # 3. I/O responsiveness
    io_latencies = []
    for vm in [v for v in vms if isinstance(v, IOVCPU)]:
        vm_history = [block for block in history if block["name"] == vm.name]
        for w_time in vm.wakeup_times:
            is_running = any(block["start"] <= w_time <= block["end"] for block in vm_history)
            if not is_running:
                start_time = next(
                    (block["start"] for block in history if block["name"] == vm.name and block["start"] >= w_time), 
                    None
                )
                if start_time is not None:
                    io_latencies.append(start_time - w_time)
    avg_io_latency = sum(io_latencies) / len(io_latencies) if io_latencies else 0.0
    
    # 4. Real-time jitter & deadline misses
    rt_misses = 0
    rt_total_periods = 0
    rt_jitters = []
    for vm in [v for v in vms if isinstance(v, RTVCPU)]:
        start_delays = []
        period = getattr(vm, 'period', 10000)
        for period_index, period_start in enumerate(range(0, sim_duration, period)):
            period_end = min(period_start + period, sim_duration)
            if period_end <= period_start: break
            rt_total_periods += 1
            # Retrieve the dynamic target workload expected for this specific period
            if hasattr(vm, 'work_history') and period_index < len(vm.work_history):
                actual_target = vm.work_history[period_index]
            else:
                actual_target = getattr(vm, 'target_run_time', 0) 
            executed_time = 0
            first_run = None
            for block in history:
                if block["name"] == vm.name:
                    # Calculate execution overlap inside this specific period window
                    overlap_start = max(period_start, block["start"])
                    overlap_end = min(period_end, block["end"])
                    if overlap_start < overlap_end:
                        executed_time += (overlap_end - overlap_start)
                        if first_run is None:
                            first_run = overlap_start
            # Check if the VM was able to finish its required work before the deadline
            if executed_time < actual_target:
                rt_misses += 1
            if first_run is not None:
                start_delays.append(first_run - period_start)
        # Compute the standard deviation (jitter) of the starting delays for this specific VM
        if len(start_delays) > 1:
            mean_delay = sum(start_delays) / len(start_delays)
            variance = sum((x - mean_delay) ** 2 for x in start_delays) / len(start_delays)
            rt_jitters.append(math.sqrt(variance))
    rt_miss_ratio = (rt_misses / rt_total_periods) * 100 if rt_total_periods > 0 else 0.0
    avg_rt_jitter = sum(rt_jitters) / len(rt_jitters) if rt_jitters else 0.0

    # 5. Fair CPU sharing
    cpu_vms = [v for v in vms if isinstance(v, CPUVCPU)]
    total_bg_time = sum(cpu_counts.get(vm.name, 0) for vm in cpu_vms)
    cpu_shares = {}
    for vm in cpu_vms:
        if total_bg_time > 0:
            time_spent = cpu_counts.get(vm.name, 0)
            cpu_shares[vm.name] = (time_spent / total_bg_time) * 100
        else:
            cpu_shares[vm.name] = 0.0
        
    # 7. Resource utilization
    idle_time = cpu_counts.get("IDLE", 0) 
    idle_time_ratio = (idle_time / sim_duration) * 100 if sim_duration > 0 else 0.0

    return {
        "switches": switches,
        "io_latency_avg": avg_io_latency,
        "rt_miss_ratio": rt_miss_ratio,
        "rt_jitter": avg_rt_jitter,
        "cpu_shares": cpu_shares,
        "idle_time_ratio": idle_time_ratio
    }

def run_single_simulation(scheduler_class, vm_configs, seed, sim_duration, **kwargs):
    # Orchestrates the instantiation and single-run loop execution of a simulation.
    random.seed(seed)
    np.random.seed(seed)
    vms = [VCPU.from_config(config) for config in vm_configs]
    sched = scheduler_class(vms, **kwargs)
    for _ in range(sim_duration):
        sched.tick()
    return analyze_scheduling_performance(sched, sim_duration)

def compute_confidence_interval(data_list, confidence=0.95):
    # Calculates sample mean and precision margins using standard Student t-distributions.
    n = len(data_list)
    if n < 2:
        return (np.mean(data_list), 0.0) if n == 1 else (0.0, 0.0)
    alpha = 1 - confidence
    t_value = stats.t.ppf(1 - alpha/2, df=n - 1)
    mean_val = np.mean(data_list)
    margin = t_value * (np.std(data_list, ddof=1) / np.sqrt(n))
    return mean_val, margin

def calculate_required_simulations(pilot_data, confidence=0.95):
    # Inverts standard Student t-distribution formulas to determine adequate sizing.
    n_pilot = len(pilot_data)
    if n_pilot < 2 :
        return n_pilot
    sample_std = np.std(pilot_data, ddof=1)
    if sample_std == 0:
        return n_pilot 
    alpha = 1.0 - confidence
    t_value = stats.t.ppf(1 - (alpha / 2), df=n_pilot - 1)
    target_margin = 0.2*sample_std
    required_n = ((t_value * sample_std) / target_margin) ** 2
    return max(n_pilot, int(math.ceil(required_n)))

def get_max_required_runs_for_system(metrics_history, confidence=0.95, max_hard_limit=150):
    # Determines largest sample matrix requirement across all system parameters.
    required_runs = []
    
    # 1. Evaluate standard metrics
    for metric_name in ["io_latency_avg", "rt_jitter", "switches", "rt_miss_ratio", "idle_time_ratio"]:
        data = metrics_history.get(metric_name, [])
        req_n = calculate_required_simulations(data, confidence)
        required_runs.append(req_n)
        
    # 2. Specific evaluation of fairness for each background VM
    for vm_name, shares in metrics_history["cpu_shares"].items():
        req_n = calculate_required_simulations(shares, confidence)
        required_runs.append(req_n)
            
    # 3. Retrieve the largest N required among all evaluated metrics
    global_max_n = max(required_runs) if required_runs else 0
    return min(global_max_n, max_hard_limit)

def evaluate_scheduler(scheduler_class, vm_configs, sim_duration=1000000, initial_runs=10, max_runs=150, confidence=0.95, base_seed=42, **kwargs):
    # Executes full adaptive multi-run evaluations until statistical convergence criteria are satisfied.
    print(f"\n=======================================================")
    print(f"STATISTICAL EVALUATION: {scheduler_class.__name__}")
    print(f"=======================================================")
    
    # 1. Dynamic data aggregation structure
    metrics_history = {
        "io_latency_avg": [], "rt_jitter": [], "switches": [], 
        "rt_miss_ratio": [], "idle_time_ratio": [], "cpu_shares": {}
    }
    def append_metrics(m):
        metrics_history["io_latency_avg"].append(m["io_latency_avg"])
        metrics_history["rt_jitter"].append(m["rt_jitter"])
        metrics_history["switches"].append(m["switches"])
        metrics_history["rt_miss_ratio"].append(m["rt_miss_ratio"])
        metrics_history["idle_time_ratio"].append(m["idle_time_ratio"])
        for vm_name, share in m["cpu_shares"].items():
            if vm_name not in metrics_history["cpu_shares"]:
                metrics_history["cpu_shares"][vm_name] = []
            metrics_history["cpu_shares"][vm_name].append(share)

    # 2. Execute original initial baseline pilot study batch
    for i in range(initial_runs):
        seed = base_seed + i
        metrics = run_single_simulation(scheduler_class, vm_configs, seed, sim_duration, **kwargs)
        append_metrics(metrics)

    # 3. Adaptive sample size checking & runtime extensions
    total_runs = initial_runs
    required_run = get_max_required_runs_for_system(metrics_history, confidence, max_runs)
    if required_run > initial_runs:
        print(f"-> Variance detected. Launching {required_run - initial_runs} additional simulations...")
        for i in range(initial_runs, required_run):
            seed = base_seed + i
            metrics = run_single_simulation(scheduler_class, vm_configs, seed, sim_duration, **kwargs)
            append_metrics(metrics)
        total_runs = required_run
    else:
        print("-> Pilot study is sufficient to meet all target margins.")

    # 4. Final statistical interval calculation
    final_stats = {
        key: compute_confidence_interval(metrics_history[key], confidence)
        for key in ["io_latency_avg", "rt_jitter", "switches", "rt_miss_ratio", "idle_time_ratio"]
    }
    fairness_stats = {
        vm: compute_confidence_interval(shares, confidence)
        for vm, shares in metrics_history["cpu_shares"].items()
    }

    print(f"\nVALIDATED RESULTS ({total_runs} runs, {confidence*100:.1f}% Confidence Interval):")
    print(f" -> Average I/O Latency    : {final_stats['io_latency_avg'][0]:.2f} us ± {final_stats['io_latency_avg'][1]:.3f} us")
    print(f" -> Real-Time Jitter       : {final_stats['rt_jitter'][0]:.2f} us ± {final_stats['rt_jitter'][1]:.3f} us")
    print(f" -> Deadline Miss Ratio    : {final_stats['rt_miss_ratio'][0]:.1f} % ± {final_stats['rt_miss_ratio'][1]:.3f} %")
    print(f" -> Context Switches       : {final_stats['switches'][0]:.1f} ± {final_stats['switches'][1]:.1f}")
    fairness_str = ", ".join([f"'{vm}': {mean:.2f}% ± {margin:.3f}%" for vm, (mean, margin) in fairness_stats.items()])
    print(f" -> Fair CPU Sharing       : {{{fairness_str}}}")
    print(f" -> Idle Time              : {final_stats['idle_time_ratio'][0]:.2f} % ± {final_stats['idle_time_ratio'][1]:.3f} %")

    return final_stats, fairness_stats

def run_visual_simulation(scheduler_class, vm_configs, seed, sim_duration, **kwargs):
    # Executes a dedicated visualization tracking run to preserve object history structures.
    random.seed(seed)
    np.random.seed(seed)
    vms = [VCPU.from_config(config) for config in vm_configs]
    sched = scheduler_class(vms, **kwargs)
    for _ in range(sim_duration):
        sched.tick()
    return sched