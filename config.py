# Copyright (c) 2026 Thales
# This software is released under the MIT License.
# See the LICENSE file in the project root for full license information.

# =============================================
# Credit scheduler
# =============================================
CREDITS_PER_MSEC = 10
CSCHED_DEFAULT_TSLICE_MS = 30 # Default timeslice granted to a running VM: 30ms
CSCHED_DEFAULT_TSLICE_US = CSCHED_DEFAULT_TSLICE_MS * 1000
CSCHED_DEFAULT_TICK_PER_SLICE = 3
CSCHED_TICK_PERIOD_US =  CSCHED_DEFAULT_TSLICE_US / CSCHED_DEFAULT_TICK_PER_SLICE
CREDITS_PER_SLICE = CREDITS_PER_MSEC * CSCHED_DEFAULT_TSLICE_MS
CREDIT_CONTEXT_SWITCH_LIMIT = 1000 # 1ms by default
PRIO_BOOST = 0    # Absolute priority granted to waking VMs
PRIO_UNDER = -1   # Has remaining credits
PRIO_OVER = -2    # Credit deficit

# =============================================
# Credit2 scheduler
# =============================================
CSCHED2_CREDIT_INIT = 10000000    # 10ms en ns
CSCHED2_MAX_TIMER = 10000  # 10 ms en us
CSCHED2_MIN_TIMER = 500 # 0.5 ms en us
CSCHED2_CONTEXT_SWITCH_LIMIT = 1000 # 1 ms en us
CSCHED2_CREDIT_MIN = -CSCHED2_CREDIT_INIT
CSCHED2_CARRYOVER_MAX = 500000

# =============================================
# BVT scheduler
# =============================================
BVT_CSA_MCU = 5000          # Context switch allowance
BVT_WEIGHT_MIN = 1
BVT_WEIGHT_MAX = 128
BVT_VT_RATIO_MIN = 8
UINT64_MAX = 0xffffffffffffffff
BVT_VT_RATIO_MAX = int((BVT_WEIGHT_MAX * BVT_VT_RATIO_MIN) / BVT_WEIGHT_MIN)

# Static execution matrix allocation layout for the Cyclic Scheduler configuration
cycle_plan = [ 
    ("IO", 1000), ("RT1", 2000), ("RT2", 4000), ("Heavy_CPU", 3000), 
    ("IO", 1000), ("RT1", 2000), ("Heavy_CPU", 4000), ("Light_CPU", 3000)
]

# Heterogeneous behavioral profiles configuration arrays for testing different workloads
scheduler_configs = {
    "Cyclic": {
        "configs": [
            {"name": "Heavy_CPU", "behavior": "cpu"},
            {"name": "Light_CPU", "behavior": "cpu"},
            {"name": "IO",        "behavior": "io", "mean_interval": 10000, "target_run_time": 1000},
            {"name": "RT1",       "behavior": "rt", "period": 10000, "target_run_time": 2000},
            {"name": "RT2",       "behavior": "rt", "period": 20000, "target_run_time": 4000}
        ],
        "kwargs": {"cycle_config": cycle_plan}
    },
    "Credit": {
        "configs": [
            {"name": "Heavy_CPU", "behavior": "cpu",  "weight": 256},
            {"name": "Light_CPU", "behavior": "cpu",  "weight": 128},
            {"name": "IO",        "behavior": "io",   "weight": 512, "mean_interval": 10000, "target_run_time": 1000},
            {"name": "RT1",       "behavior": "rt",   "weight": 512, "period": 10000, "target_run_time": 2000},
            {"name": "RT2",       "behavior": "rt",   "weight": 512, "period": 20000, "target_run_time": 4000},
        ],
        "kwargs": {}
    },
    "Credit2": {
        "configs": [
            {"name": "Heavy_CPU", "behavior": "cpu",  "weight": 256},
            {"name": "Light_CPU", "behavior": "cpu",  "weight": 128},
            {"name": "IO",        "behavior": "io",   "weight": 512, "mean_interval": 10000, "target_run_time": 1000},
            {"name": "RT1",       "behavior": "rt",   "weight": 512, "period": 10000, "target_run_time": 2000},
            {"name": "RT2",       "behavior": "rt",   "weight": 512, "period": 20000, "target_run_time": 4000},
        ],
        "kwargs": {}
    },
    "RTDS_A": {
        "configs": [
            {"name": "Heavy_CPU", "behavior": "cpu",  "period": 50000, "budget": 14000, "extratime": True},
            {"name": "Light_CPU", "behavior": "cpu",  "period": 50000, "budget": 7000, "extratime": True},
            {"name": "IO",        "behavior": "io",   "period": 2500,  "budget": 250, "target_run_time": 1000, "mean_interval": 10000, "extratime": True},
            {"name": "RT1",       "behavior": "rt",   "period": 10000, "budget": 2000, "target_run_time": 2000},
            {"name": "RT2",       "behavior": "rt",   "period": 20000, "budget": 4000, "target_run_time": 4000}   
        ],
        "kwargs": {}
    },
    "RTDS_B": {
        "configs": [
            {"name": "Heavy_CPU", "behavior": "cpu",  "period": 50000, "budget": 14000, "extratime": True},
            {"name": "Light_CPU", "behavior": "cpu",  "period": 50000, "budget": 7000, "extratime": True},
            {"name": "IO",        "behavior": "io",   "period": 10000, "budget": 1000, "target_run_time": 1000, "mean_interval": 10000, "extratime": True},
            {"name": "RT1",       "behavior": "rt",   "period": 10000, "budget": 2000, "target_run_time": 2000},
            {"name": "RT2",       "behavior": "rt",   "period": 20000, "budget": 4000, "target_run_time": 4000}   
        ],
        "kwargs": {}
    },
    "Priority": {
        "configs": [
            {"name": "Heavy_CPU", "behavior": "cpu",  "priority": 10},
            {"name": "Light_CPU", "behavior": "cpu",  "priority": 10},
            {"name": "IO",        "behavior": "io",   "priority": 50, "period": 10000, "target_run_time": 1000, "mean_interval": 10000},
            {"name": "RT1",       "behavior": "rt",   "priority": 40, "period": 10000, "target_run_time": 2000},
            {"name": "RT2",       "behavior": "rt",   "priority": 30, "period": 20000, "target_run_time": 4000}  
        ],
        "kwargs": {}
    },
    "BVT": {
        "configs": [
            {"name": "Heavy_CPU", "behavior": "cpu",  "weight": 64},
            {"name": "Light_CPU", "behavior": "cpu",  "weight": 32},
            {"name": "IO",        "behavior": "io",   "weight": 128, "target_run_time": 1000, "mean_interval": 10000},
            {"name": "RT1",       "behavior": "rt",   "weight": 128, "period": 10000, "target_run_time": 2000},
            {"name": "RT2",       "behavior": "rt",   "weight": 128, "period": 20000, "target_run_time": 4000}  
        ],
        "kwargs": {}
    },
    "IORR": {
        "configs": [
            {"name": "Heavy_CPU", "behavior": "cpu"},
            {"name": "Light_CPU", "behavior": "cpu"},
            {"name": "IO",        "behavior": "io", "target_run_time": 1000, "mean_interval": 10000},
            {"name": "RT1",       "behavior": "rt", "period": 10000, "target_run_time": 2000},
            {"name": "RT2",       "behavior": "rt", "period": 20000, "target_run_time": 4000}
        ],
        "kwargs": {}
    },
    "PRR": {
        "configs": [
            {"name": "Heavy_CPU", "behavior": "cpu",  "priority": 50, "time_slice": 10000},
            {"name": "Light_CPU", "behavior": "cpu",  "priority": 50, "time_slice": 10000},
            {"name": "IO",        "behavior": "io",   "priority": 255, "time_slice": 1000, "period": 10000, "target_run_time": 1000, "mean_interval": 10000},
            {"name": "RT1",       "behavior": "rt",   "priority": 200, "time_slice": 2000, "period": 10000, "target_run_time": 2000},
            {"name": "RT2",       "behavior": "rt",   "priority": 150, "time_slice": 4000, "period": 20000, "target_run_time": 4000}  
        ],
        "kwargs": {}
    },
    "PRM": {
        "configs": [
            {"name": "Heavy_CPU", "behavior": "cpu",  "priority": 252, "time_slice": 10000, "period": 1000000},
            {"name": "Light_CPU", "behavior": "cpu",  "priority": 252, "time_slice": 10000, "period": 1000000},
            {"name": "IO",        "behavior": "io",   "priority": 255, "time_slice": 1000, "period": 10000, "target_run_time": 1000, "mean_interval": 10000},
            {"name": "RT1",       "behavior": "rt",   "priority": 254, "time_slice": 2000, "period": 10000, "target_run_time": 2000},
            {"name": "RT2",       "behavior": "rt",   "priority": 253, "time_slice": 4000, "period": 20000, "target_run_time": 4000}  
        ],
        "kwargs": {}
    }
}