# Copyright (c) 2026 Thales
# This software is released under the MIT License.
# See the LICENSE file in the project root for full license information.

import matplotlib.pyplot as plt
import numpy as np
import matplotlib.patches as patches
from matplotlib.lines import Line2D
from core import IOVCPU, RTVCPU

def plot_global_results(evaluation_results):
    # Generates a 2x3 performance matrix dashboard comparing global metrics across schedulers.
    schedulers = list(evaluation_results.keys())
    n_schedulers = len(schedulers)
    
    fig, axes = plt.subplots(2, 3, figsize=(18, 10))
    
    axs = axes.flatten()
    bar_color = '#66b3ff'

    # 1. I/O wake-up latency
    io_latencies = [evaluation_results[s]["io_latency_avg"][0] for s in schedulers]
    io_errs      = [evaluation_results[s]["io_latency_avg"][1] for s in schedulers]
    axs[0].bar(schedulers, io_latencies, yerr=io_errs, capsize=5, color=bar_color)
    axs[0].set_title("I/O wake-up latency")
    axs[0].set_ylabel("Latency (us)")

    # 2. Context switches
    context_switches = [evaluation_results[s]["switches"][0] for s in schedulers]
    cs_errs          = [evaluation_results[s]["switches"][1] for s in schedulers]
    axs[1].bar(schedulers, context_switches, yerr=cs_errs, capsize=5, color=bar_color)
    axs[1].set_title("Context switch count")
    axs[1].set_ylabel("Count")

    # 3. Real-time response jitter
    rt_jitters = [evaluation_results[s]["rt_jitter"][0] for s in schedulers]
    rt_errs    = [evaluation_results[s]["rt_jitter"][1] for s in schedulers]
    axs[2].bar(schedulers, rt_jitters, yerr=rt_errs, capsize=5, color=bar_color)
    axs[2].set_title("Real-time response jitter")
    axs[2].set_ylabel("Jitter (us)")

    # 4. Real-time deadline miss ratio
    deadline_misses = [evaluation_results[s]["rt_miss_ratio"][0] for s in schedulers]
    miss_errs       = [evaluation_results[s]["rt_miss_ratio"][1] for s in schedulers]
    axs[3].bar(schedulers, deadline_misses, yerr=miss_errs, capsize=5, color=bar_color)
    axs[3].set_title("Real-time deadline miss ratio")
    axs[3].set_ylabel("Miss ratio (%)")

    # 5. Scheduler computation time ratio
    idle_ratio = [evaluation_results[s]["idle_time_ratio"][0] for s in schedulers]
    idle_errs   = [evaluation_results[s]["idle_time_ratio"][1] for s in schedulers]
    axs[4].bar(schedulers, idle_ratio, yerr=idle_errs, capsize=5, color=bar_color)
    axs[4].set_title("Idle time ratio")
    axs[4].set_ylabel("Idle time ratio (%)")

    # 6. CPU time distribution
    all_entities = ["Heavy_CPU", "Light_CPU"]
    colors = ['#ff9999', '#66b3ff'] 
    bottoms = np.zeros(n_schedulers)
    for idx, entity in enumerate(all_entities):
        entity_values = []
        for s in schedulers:
            val = evaluation_results[s]["cpu_sharing"].get(entity, 0.0)
            if isinstance(val, (tuple, list, np.ndarray)):
                val = val[0]
            entity_values.append(val)
        axs[5].bar(schedulers, entity_values, bottom=bottoms, label=entity, color=colors[idx])
        bottoms += np.array(entity_values) 
    axs[5].set_title("Fair CPU sharing - Heavy-CPU vs Light-CPU")
    axs[5].set_ylabel("CPU time (%)")
    axs[5].set_ylim(0, 100)
    axs[5].axhline(y=66.66, color='black', linestyle='--', linewidth=1, label='Theoretical frontier (66.6%)')
    axs[5].legend(loc='upper left', bbox_to_anchor=(1, 1))

    for ax in axs:
        ax.tick_params(axis='x', rotation=45)
        ax.grid(axis='y', linestyle='--', alpha=0.7)
    plt.tight_layout()
    plt.subplots_adjust(top=0.90) 

def plot_gantt_latency(sched, window_us):
    # Renders a chronological Gantt chart
    vm_names = [v.name for v in sched.vcpus]
    has_plan = hasattr(sched, 'schedule_table')
    if has_plan:
        y_labels = ["IDLE"] + vm_names + ["PLAN"] 
    else:
        y_labels = ["IDLE"] + vm_names 
    y_ticks = {name: i for i, name in enumerate(y_labels)}
    fig_height = max(4, len(y_labels) * 1.2) 
    fig, ax = plt.subplots(figsize=(12, fig_height)) 
    color_palette = ['#4E79A7', '#F28E2B', '#E15759', '#76B7B2', '#59A14F', '#EDC948']
    vm_colors = {name: color_palette[i % len(color_palette)] for i, name in enumerate(vm_names)}
    vm_colors["IDLE"] = "#BDC3C7" 
    
    # Only for the cyclic scheduler with a defined plan, we visualize the planned slots.
    if has_plan:
        major_frame = sched.major_frame
        for cycle_start in range(0, window_us, major_frame):
            for slot in sched.schedule_table:
                s_start = cycle_start + slot["start"]
                s_end = min(cycle_start + slot["end"], window_us)
                if s_start >= window_us: continue
                vm_name = slot["vm"].name if slot["vm"] else "IDLE"
                ax.barh(y_ticks["PLAN"], s_end - s_start, left=s_start, height=0.4, 
                        color=vm_colors[vm_name], edgecolor='black', alpha=0.8)
                ax.text(s_start + (s_end - s_start)/2, y_ticks["PLAN"], vm_name, 
                        ha='center', va='center', color='white', fontsize=8, fontweight='bold')
                rect = patches.Rectangle((s_start, y_ticks[vm_name] - 0.3), s_end - s_start, 0.6,
                                         linewidth=0.8, edgecolor='black', facecolor=vm_colors[vm_name], 
                                         linestyle='-', alpha=0.1, zorder=0)
                ax.add_patch(rect)

    # Real execution
    for block in sched.history:
        start, end, name = block["start"], min(block["end"], window_us), block["name"]
        if start >= window_us: break
        ax.barh(y_ticks[name], end - start, left=start, height=0.3, 
                color=vm_colors.get(name, 'gray'), edgecolor='black', zorder=3)

    # Wake-ups
    for vm in sched.vcpus:
        if isinstance(vm, (IOVCPU, RTVCPU)):
            y_pos = y_ticks[vm.name]
            for i, w_time in enumerate(vm.wakeup_times):
                if w_time >= window_us: break
                ax.plot(w_time, y_pos, marker='x', color='red', markersize=8, 
                        markeredgewidth=1, zorder=5)

    ax.set_yticks(list(y_ticks.values()))
    ax.set_yticklabels(list(y_ticks.keys()), fontweight='bold')
    ax.set_ylim(-0.5, len(y_labels) - 0.5)
    ax.set_xlabel("Time (µs)", fontweight='bold', labelpad=10)
    ax.grid(axis='x', linestyle='--', alpha=0.4, zorder=0)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    if has_plan:
        legend_elements = [
            patches.Patch(facecolor='#4E79A7', edgecolor='black', label='Real execution (Run)'),
            patches.Patch(facecolor='#4E79A7', alpha=0.1, edgecolor='black', 
                        linestyle='-', label='Allocated window (Slot)'),
            Line2D([0], [0], marker='x', color='red', label='Wake-ups', 
                linestyle='None', markersize=10, markeredgewidth=2),
        ]
    else:
        legend_elements = [
            patches.Patch(facecolor='#4E79A7', edgecolor='black', label='Real execution (Run)'),
            Line2D([0], [0], marker='x', color='red', label='Wake-ups', 
                linestyle='None', markersize=10, markeredgewidth=2),
        ]
    leg = ax.legend(handles=legend_elements, 
                    loc='upper center', 
                    bbox_to_anchor=(0.5, -0.15),
                    frameon=True, 
                    fontsize=9)
    plt.setp(leg.get_title(), fontweight='bold')
    plt.tight_layout(rect=[0, 0.05, 1, 1])