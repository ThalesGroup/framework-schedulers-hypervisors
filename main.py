# Copyright (c) 2026 Thales
# This software is released under the MIT License.
# See the LICENSE file in the project root for full license information.

import numpy as np
from config import scheduler_configs
import matplotlib.pyplot as plt
from schedulers import (
    CyclicScheduler, 
    CreditScheduler, 
    Credit2Scheduler, 
    RTDSScheduler, 
    PriorityScheduler, 
    BVTScheduler, 
    IORRScheduler,
    PRRScheduler,
    PRMScheduler
)
from evaluation import (
    run_single_simulation, 
    get_max_required_runs_for_system, 
    evaluate_scheduler,
    run_visual_simulation
)
from visualization import plot_global_results, plot_gantt_latency
from core import VCPU

if __name__ == "__main__":
    # Map configuration keys to actual Python classes robustly
    class_mapper = {
        "Cyclic": CyclicScheduler, "Credit": CreditScheduler, "Credit2": Credit2Scheduler,
        "RTDS_A": RTDSScheduler, "RTDS_B": RTDSScheduler, "Priority": PriorityScheduler,
        "BVT": BVTScheduler, "IORR": IORRScheduler, "PRR": PRRScheduler, "PRM": PRMScheduler
    }
    schedulers_info = [
        (name, class_mapper[name], info["configs"], info["kwargs"])
        for name, info in scheduler_configs.items()
    ]
    PILOT_RUNS = 10
    SIM_DURATION = 1000000
    global_max_runs = PILOT_RUNS

    print("=======================================================")
    print(" PHASE 1: PILOT RUNS & MAX RUNS CALCULATION")
    print("=======================================================")
    for name, sched_class, configs, kwargs in schedulers_info:
        # Loop 1: Gather pilot history and reshape indicators inline
        pilot_history = [
            run_single_simulation(sched_class, configs, 42 + i, SIM_DURATION, **kwargs)
            for i in range(PILOT_RUNS)
        ]
        
        metrics_history = {}
        for run_res in pilot_history:
            for key, value in run_res.items():
                if isinstance(value, dict):
                    metrics_history.setdefault(key, {})
                    for sub_key, sub_value in value.items():
                        metrics_history[key].setdefault(sub_key, []).append(sub_value)
                else:
                    metrics_history.setdefault(key, []).append(value)
                
        req_runs = get_max_required_runs_for_system(metrics_history)
        print(f"[{name}] Simulations required based on pilot: {req_runs}")
        
        if req_runs > global_max_runs:
            global_max_runs = req_runs

    # Enforce hard limits bounds on global sampling loops
    MIN_HARD_LIMIT, MAX_HARD_LIMIT = 100, 500
    global_max_runs = max(MIN_HARD_LIMIT, min(global_max_runs, MAX_HARD_LIMIT))
    print(f"\n=> TARGET LOCKED: All schedulers will be evaluated over {global_max_runs} simulations.")

    print("\n=======================================================")
    print(f" PHASE 2: FINAL EVALUATION WITH {global_max_runs} RUNS")
    print("=======================================================")
    # Loop 2: Evaluate dynamically all schedulers and structure results in a single database dict
    raw_results = {}
    for name, sched_class, configs, kwargs in schedulers_info:
        stats, fairness = evaluate_scheduler(
            sched_class, configs, 
            initial_runs=global_max_runs, sim_duration=SIM_DURATION, **kwargs
        )
        raw_results[name] = {"stats": stats, "fairness": fairness}
    
    print("\n=======================================================")
    print(" PHASE 3: PLOTTING GLOBAL RESULTS")
    print("=======================================================")
    # Map extracted database fields to expected plotting structure without intermediate variables
    results_to_plot = {
        name: {**data["stats"], "cpu_sharing": data["fairness"]}
        for name, data in raw_results.items()
    }
    plot_global_results(results_to_plot)

    print("\n=======================================================")
    print(" PHASE 4: GANTT CHART VISUALIZATION")
    print("=======================================================")
    WINDOW_US = 40000
    GANTT_SEED = 42

    # Loop 3: Generate visual traces for UI plots sequential flow mapping
    for name, sched_class, configs, kwargs in schedulers_info:
        sched = run_visual_simulation(
            scheduler_class=sched_class, vm_configs=configs, 
            seed=GANTT_SEED, sim_duration=WINDOW_US, **kwargs
        )
        plot_gantt_latency(sched, window_us=WINDOW_US)
    plt.show()