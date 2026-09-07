# Virtual CPU scheduling and behavioral simulation architecture

## Get started

This project is a Python-based discrete-event simulation framework for testing, evaluating, and visualizing the CPU allocation logic of vCPU scheduling algorithms found in open-source hypervisors. It was developed for the research paper **"VM schedulers in open-source hypervisors dedicated to embedded systems – a survey"** (Mignerey L., Ferrari A., Sauveron D., Tamine K.).

To abstract away multi-core load-balancing artifacts and evaluate preemption capabilities, the framework operates in a constrained single-core environment.

### Mixed-criticality workload

To emulate a realistic mixed-criticality environment, the framework simulates 5 distinct VM profiles running simultaneously:

- **Heavy-CPU**: Computationally intensive, non-critical workload.
- **Light-CPU**: Less demanding background workload (2 times less important than Heavy-CPU).
- **I/O-intensive**: Highly sporadic and interactive workload simulating hardware interrupts with a mean interval of 10ms.
- **RT1 (Real-Time 1)**: Highly critical, fast-paced safety domain operating at 100Hz (10ms period).
- **RT2 (Real-Time 2)**: Critical safety domain operating at 50Hz (20ms period).

### Implemented schedulers

The framework faithfully reproduces the core logic of the following scheduling algorithms:

- **Cyclic Scheduler** [1][2][3]
- **Credit Scheduler** [4][5]
- **Credit2 Scheduler** [6][7]
- **RTDS (Real-Time Deferrable Server) Scheduler** [8][9][10]
- **Priority-based Scheduler** [11]
- **BVT (Borrowed Virtual Time) Scheduler** [12]
- **IORR (I/O Round Robin) Scheduler** [13]
- **PRR (Priority-based Round Robin)** [14]
- **PRM (Priority-based Rate Monotonic)** [15]

### Installation and execution

This project was developed and tested using **Python 3.13.7**. We recommend using **Conda** to manage your virtual environment.

To set up the environment and install the required dependencies, please use the provided `requirements.txt` file:

```bash
# 1. Create a Conda virtual environment with Python 3.13.7
conda create -n FrameworkSchedulers python=3.13.7

# 2. Activate the Conda environment
conda activate FrameworkSchedulers

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run the simulations and generate the statistical evaluation matrix
python main.py
```

## Documentation

Documentation is currently available in this README and in the source files linked below. A dedicated documentation website can be added later through [GitHub Pages](https://guides.github.com/features/pages/).

### Project structure

- `core.py`: Defines the foundational `Scheduler` base class, the `VCPU` hierarchy (`CPUVCPU`, `IOVCPU`, `RTVCPU`).
- `config.py`: Contains configurations for workloads and scheduler-specific parameters.
- `schedulers.py`: Contains the implementation of the 9 algorithms.
- `evaluation.py`: Orchestrates the simulation loop and parses history tracks for metrics.
- `visualization.py`: Renders comprehensive visualization dashboards.
- `main.py`: The entry point mapping configurations and initiating the evaluations.

### Evaluation methodology and metrics

Because computer simulations are subject to non-deterministic variations, this framework uses standard Student's t-distributions to guarantee a strict 95% confidence interval. The evaluation dynamically scales up to 150 simulation runs 1,000,000 microseconds each (1 second, microsecond granularity), to reach statistical convergence.

The system extracts the following quantitative metrics:

- **Real-time guarantees**: Deadline miss ratio and response time jitter.
- **I/O responsiveness**: Wake-up latency for sporadic events.
- **Resource utilization**: Idle time percentage (work-conserving vs. non-work-conserving).
- **Fair CPU sharing**: Proportional execution ratio between Heavy-CPU and Light-CPU VMs.
- **Scheduling overhead**: Context switch counts.

### Visualization dashboard

The project generates outputs to easily analyze the algorithms' behaviors:

- **Chronological Gantt charts**: Displays execution timelines, sleep states, and wake-up events for every VM.
- **Global Performance Matrix**: A 2x3 graphical dashboard comparing all key metrics across the evaluated schedulers.

### Implementing a new scheduler

To add a new scheduling algorithm to the framework, create a new class in [schedulers.py](schedulers.py) that inherits from the `Scheduler` base class. Your custom scheduler must implement at least four core methods: `wake(v)`, `sleep(v)`, `pick_next()`, and `tick()`.

The framework uses a small factory in [core.py](core.py) to turn each configuration dictionary into the right vCPU subclass. In practice, the scheduler should receive already-instantiated `VCPU` objects, and the scheduler-specific parameters should be passed through `kwargs` from [config.py](config.py).

The `wake(v)` method is called when a vCPU transitions from SLEEP to RUNNABLE state (e.g., after a periodic deadline or I/O event); it should update the scheduler's internal state to reflect that vCPU as eligible for execution.

The `sleep(v)` method is called when a vCPU blocks (its work is complete or it entered a wait state); typically you should update state tracking and ensure `current_vcpu` is set to `None` if the sleeping vCPU is currently running.

The `pick_next()` method implements your scheduling policy by selecting which vCPU should run next based on your algorithm's logic (e.g., credit balance, priority, deadline).

The `tick()` method is the heartbeat of the simulation and should always start with `self.update_vcpu_states()` to process all asynchronous wake/sleep transitions. After state updates, update remaining work with the function `consume_execution_tick` (this variable is used to handle wake/sleep timings in the function `self.update_vcpu_states()`), then check if `self.need_resched` is set to `True` (either by a timer interrupt, a wake event, or by your own policy logic). If rescheduling is needed, call `self.pick_next()` to invoke your scheduling decision. At minimum (unless other scheduler-specific state updates are required), perform the context switch after `pick_next()` returns by executing:

```bash
if self.current_vcpu != prev_vcpu:
    if prev_vcpu is not None and prev_vcpu.state == "RUN":
        prev_vcpu.state = "RUNNABLE";
if self.current_vcpu is not None:
    self.current_vcpu.state = "RUN".
```

This logic ensures proper state transitions: if the selected vCPU differs from the previously running one, the old vCPU (if any) is demoted from RUN to RUNNABLE, and the new vCPU is promoted to RUN.

Finally, append the current execution to history with `self.add_history()` and increment `self.time_us` by 1. The tick here operates at microsecond granularity (the simulation step size) so logic can be applied at this fine-grained level or at coarser intervals. For example, if your scheduler requires a decision only every millisecond, simply wrap your logic in an `if self.time_us % 1000 == 0:` condition within the `tick()`.

Once your scheduler class is complete, register it in [config.py](config.py) by adding a new entry to the `scheduler_configs` dictionary with the scheduler's name as key, providing a `"configs"` list of vCPU configurations and optional `"kwargs"` for any scheduler-specific parameters. Finally, update the `class_mapper` dictionary in [main.py](main.py) to map your scheduler's name to its class so the framework can instantiate it during evaluation.

When documenting a new scheduler entry in `config.py`, keep the split clear:

- scheduler-specific fields go in the top-level `kwargs` of that scheduler block;
- workload-specific fields stay inside each vCPU config entry (`behavior`, and the fields required by that workload type);
- the `name` field identifies the vCPU instance used by the scheduler or the cyclic major frame layout.

### Modifying vCPUs' configuration

Each vCPU in the simulation requires a behavior profile that defines how it generates and consumes workload.

In [config.py](config.py), under `scheduler_configs["YourScheduler"]["configs"]`, add a configuration dictionary for each vCPU with the mandatory fields `"name"` and `"behavior"`. The `"behavior"` field accepts three values: `"cpu"` for background, non-critical compute tasks that always have work pending; `"io"` for sporadic, interactive workloads that block and wake on interrupt-like events; and `"rt"` for hard real-time periodic vCPUs.

For `"cpu"` behavior, no additional parameters are required.

For `"io"` behavior, specify `"mean_interval"` (the mean time in microseconds between successive I/O events following a Poisson process) and `"target_run_time"` (the duration in microseconds each event should execute, it can be the WCET). For example, an I/O vCPU with `"mean_interval": 10000` and `"target_run_time": 1000` will wake with events at random intervals averaging 10ms, each executing for approximately 1ms.

For `"rt"` behavior, provide `"period"` (the period in microseconds between successive activations) and `"target_run_time"`. RT vCPUs generate execution time randomly between 50% and 100% of `target_run_time`.

Beyond these behavior-specific fields, individual schedulers impose their own parameter requirements. These belong in the scheduler block `kwargs`, not inside the workload entries, unless the parameter is truly per-vCPU.

The **Credit Scheduler**, **Credit2 Scheduler** and **BVT Scheduler** require a `"weight"` parameter (a positive integer representing the proportional CPU share). Note that the source code of the ACRN's BVT scheduler impose that the weight value must be between 0 and 128.

The **RTDS Scheduler** requires `"period"` and `"budget"` parameters for all vCPUs, optionally with an `"extratime"` flag (boolean, default `False`) to allow execution beyond budget when no other work is pending.

The **Priority Scheduler** and **PRR Scheduler** require a `"priority"` field (an integer where higher values indicate higher priority).

The **IORR Scheduler** has no extra requirements beyond behavior parameters. When defining configurations, ensure consistency: all vCPUs must carry the parameters their target scheduler expects.

The **PRM Scheduler** requires a `"priority"` field, as well as a `"time_slice"` parameter.

A best practice is to follow the provided templates in [config.py](config.py), copy an existing scheduler's configuration block, update the vCPU names and behavior profiles as needed, and modify the scheduler-specific parameters. To simplify testing different policies, it is recommended to maintain separate configurations for each scheduler variant rather than a single global configuration, enabling independent tuning of workloads and parameters per scheduling algorithm.

### Bibliography

[1] lfd, “XtratuM/core/kernel/sched.c at master · lfd/XtratuM,” GitHub, 2025. https://github.com/lfd/XtratuM/blob/master/core/kernel/sched.c (accessed Feb. 20, 2026).

[2] “ARINC653 Scheduler – Xen” Xenproject.org, 2026. https://wiki.xenproject.org/wiki/ARINC653_Scheduler (accessed Feb. 20, 2026).

[3] “xen/common/sched/arinc653.c · staging · xen-project / xen · GitLab,” GitLab, 2026. https://gitlab.com/xen-project/xen/-/blob/staging/xen/common/sched/arinc653.c (accessed Feb. 20, 2026).

[4] “Credit Scheduler – Xen” Xenproject.org, 2026. https://wiki.xenproject.org/wiki/Credit_Scheduler (accessed Feb. 20, 2026).

[5] “xen/common/sched/credit.c · staging · xen-project / xen · GitLab,” GitLab, 2026. https://gitlab.com/xen-project/xen/-/blob/staging/xen/common/sched/credit.c (accessed Feb. 20, 2026).

[6] “Credit2 Scheduler – Xen” Xenproject.org, 2026. https://wiki.xenproject.org/wiki/Credit2_Scheduler (accessed Feb. 20, 2026).

[7] “xen/common/sched/credit2.c · staging · xen-project / xen · GitLab,” GitLab, 2026. https://gitlab.com/xen-project/xen/-/blob/staging/xen/common/sched/credit2.c (accessed Feb. 20, 2026).

[8] TDS-Based-Scheduler – Xen” Xenproject.org, 2026. https://wiki.xenproject.org/wiki/rtds-based-scheduler (accessed Feb. 20, 2026).

[9]xen/common/sched/rt.c · staging · xen-project / xen · GitLab,” GitLab, 2026. https://gitlab.com/xen-project/xen/-/blob/staging/xen/common/sched/rt.c (accessed Feb. 20, 2026).

[10] Xi et al., “Real-time Multi-Core Virtual Machine Scheduling in Xen,” in Proceedings of the 14th International Conference on Embedded Software, New Delhi India: ACM, Oct. 2014, pp. 1–10. doi: 10.1145/2656045.2656061.

[11] projectacrn, “acrn-hypervisor/hypervisor/common/sched_prio.c at master · projectacrn/acrn-hypervisor,” GitHub, 2025. https://github.com/projectacrn/acrn-hypervisor/blob/master/hypervisor/common/sched_prio.c (accessed Feb. 20, 2026).

[12] projectacrn, “acrn-hypervisor/hypervisor/common/sched_bvt.c at master · projectacrn/acrn-hypervisor,” GitHub, 2025. https://github.com/projectacrn/acrn-hypervisor/blob/master/hypervisor/common/sched_bvt.c (accessed Feb. 20, 2026).

[13] projectacrn, “acrn-hypervisor/hypervisor/common/sched_iorr.c at master · projectacrn/acrn-hypervisor,” GitHub, 2025. https://github.com/projectacrn/acrn-hypervisor/blob/master/hypervisor/common/sched_iorr.c (accessed Feb. 20, 2026).

[14] xvisor/core/schedalgo/vmm_schedalgo_prr.c at master · xvisor/xvisor. GitHub. Retrieved July 9, 2026 from https://github.com/xvisor/xvisor/blob/master/core/schedalgo/vmm_schedalgo_prr.c

[15] xvisor/core/schedalgo/vmm_schedalgo_prm.c at master · xvisor/xvisor. GitHub. Retrieved July 9, 2026 from https://github.com/xvisor/xvisor/blob/master/core/schedalgo/vmm_schedalgo_prm.c

### Security check

Project dependencies have been scanned using ` pip-audit`, and no known security vulnerabilities were found in the [requirements.txt](requirements.txt) file.

### Dependencies and licenses

This software is released by Thales under the MIT License. However, it relies on several third-party libraries that are not distributed within this repository. They must be downloaded and installed separately by the user (e.g., using `pip install -r requirements.txt`).

**Important: Each dependency is subject to its own license.**

Below is the list of dependencies used by this project and their respective indicative licenses:

| Dependency          | Version     | License                             |
| :------------------ | :---------- | :---------------------------------- |
| **contourpy**       | 1.3.3       | BSD 3-Clause                        |
| **cycler**          | 0.12.1      | BSD 3-Clause                        |
| **fonttools**       | 4.63.0      | MIT License                         |
| **kiwisolver**      | 1.5.0       | BSD 3-Clause                        |
| **matplotlib**      | 3.11.0      | Matplotlib License (PSF-compatible) |
| **numpy**           | 2.5.0       | BSD 3-Clause                        |
| **packaging**       | 26.2        | Apache 2.0 and BSD 2-Clause         |
| **pillow**          | 12.3.0      | HPND License                        |
| **pyparsing**       | 3.3.2       | MIT License                         |
| **python-dateutil** | 2.9.0.post0 | Apache 2.0 and BSD 3-Clause         |
| **scipy**           | 1.18.0      | BSD 3-Clause                        |
| **six**             | 1.17.0      | MIT License                         |

_Note on SciPy and Qhull:_ SciPy relies internally on **Qhull**, which is subject to the [Qhull License](http://www.qhull.org/COPYING.txt). Any modification or distribution of Qhull must comply with its specific terms.

For security concerns, please follow the process described in [SECURITY.md](SECURITY.md).

## Contributing

If you are interested in contributing to this project, start by reading the [Contributing guide](CONTRIBUTING.md).

The guide covers the development workflow, scheduler implementation, configuration conventions, validation, issue reporting, and pull requests.

## License

This software is released by Thales under the MIT License. The complete terms are available in the explicit [LICENSE](LICENSE) file at the root of the repository.

The project relies on third-party libraries that are not distributed within this repository. They must be downloaded and installed separately by the user. Each dependency is subject to its own license; the indicative dependency licenses are listed in the Documentation section above.
