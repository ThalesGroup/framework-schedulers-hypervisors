# Contributing

Thank you for contributing to the virtual CPU scheduling and behavioral simulation framework.

## Getting started

The project is developed and tested with Python 3.13.7. Using Conda is recommended.

```bash
conda create -n FrameworkSchedulers python=3.13.7
conda activate FrameworkSchedulers
pip install -r requirements.txt
```

Before making changes, run the existing simulation to confirm that your environment is working:

```bash
python main.py
```

## Development workflow

1. Create a focused branch from the current default branch.
2. Keep each change small and related to one purpose.
3. Preserve the existing configuration format unless the change requires otherwise.
4. Update the documentation when behavior, configuration fields, or setup steps change.
5. Run the relevant checks before opening a pull request.

Use clear branch names such as `feature/priority-scheduler`, `fix/wake-state`, or `docs/contributing`.

## Code guidelines

- Follow the existing Python style and use descriptive names.
- Keep scheduler-specific logic in `schedulers.py` and workload configuration in `config.py`.
- Avoid unrelated refactoring in feature or bug-fix changes.
- Keep simulation behavior deterministic when a seed is provided.
- Add concise comments only when the implementation is not self-explanatory.

## Adding a scheduler

A new scheduler should inherit from `Scheduler` in `core.py` and be implemented in `schedulers.py`. At minimum, implement:

- `wake(v)` to make a vCPU eligible to run.
- `sleep(v)` to remove a blocked vCPU from scheduling and clear `current_vcpu` when necessary.
- `pick_next()` to select the next vCPU according to the policy.
- `tick()` to process state transitions, account for execution, reschedule when needed, record history, and advance simulation time.

When implementing `tick()`:

1. Start by calling `self.update_vcpu_states()`.
2. Update execution using the existing execution-accounting helpers.
3. Honor `self.need_resched` and call `self.pick_next()` when a decision is required.
4. Apply the normal `RUN`/`RUNNABLE` context-switch transitions.
5. Call `self.add_history()` and increment `self.time_us`.

Register the scheduler in both places required by the application:

- Add its workload and scheduler-specific parameters to `scheduler_configs` in `config.py`.
- Add its name-to-class mapping to `class_mapper` in `main.py`.

Keep scheduler parameters in the scheduler block's top-level `kwargs`. Keep workload parameters inside each vCPU configuration entry.

## Configuration conventions

Every vCPU configuration must include `name` and `behavior`. Supported behaviors are:

- `cpu` for continuously available background work.
- `io` for sporadic workloads, with `mean_interval` and `target_run_time`.
- `rt` for periodic real-time workloads, with `period` and `target_run_time`.

Add scheduler-specific fields only when the selected policy requires them. For example, priority-based schedulers use `priority`, proportional-share schedulers use `weight`, and PRM uses both `priority` and `time_slice`.

## Validation

At minimum, run the simulation after code or configuration changes:

```bash
python main.py
```

For a focused change, also verify the relevant output and check that:

- no vCPU remains incorrectly marked as `RUN` after it sleeps;
- wake-ups and deadlines occur at the expected times;
- scheduler-specific parameters are present and valid;
- generated metrics and visualizations remain readable.

If you add automated tests in the future, run the relevant test file and the full test suite before submitting the pull request.

## Issues

Before opening an issue, search the existing issues to avoid duplicates. Use a clear, specific title and choose the most appropriate category:

- **Bug report** for incorrect behavior, crashes, or unexpected simulation results.
- **Feature request** for a new scheduler, metric, configuration option, or other improvement.
- **Question** when clarification is needed about the project or its behavior.

Bug reports should include:

- the Python version and operating system;
- the command or configuration that reproduces the problem;
- the expected behavior and the actual behavior;
- the complete error message or traceback, when available;
- relevant logs, metrics, or a minimal configuration that demonstrates the issue.

Feature requests should explain the use case, the expected behavior, and how the proposal fits the simulator's existing architecture. Do not include credentials, private data, or unnecessary generated files in an issue.

## Pull requests

A pull request should include:

- a concise description of the problem and the approach taken;
- the scheduler, workload, or metric behavior that changed;
- the commands used for validation and their results;
- updated documentation or configuration examples when applicable.

Keep pull requests reviewable. Separate unrelated cleanup, formatting changes, or dependency upgrades into separate pull requests.

## Dependencies and security

Update `requirements.txt` only when a dependency is necessary for the project. Explain the reason for the change and its impact in the pull request. Check dependencies for known vulnerabilities before submitting changes.

Do not commit generated figures, local environments, credentials, or machine-specific configuration unless they are explicitly required by the project.

## License

By contributing, you agree that your contributions are provided under the project's MIT License.
