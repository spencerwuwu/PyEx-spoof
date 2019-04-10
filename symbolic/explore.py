# Copyright: see copyright.txt

import time

from multiprocessing import Process, Queue
from os import path
from queue import PriorityQueue
from sys import exc_info, platform

import coverage
import traceback

from .path_to_constraint import PathToConstraint
from .symbolic_types import symbolic_type, SymbolicType
from .cvc_wrap import CVCWrapper

# Scheculing policy
def central_queue(worker_pool: dict, timeouts: list, selected_timeout: float or int):
    for worker_id, worker in worker_pool.items():
        if worker is None:
            return worker_id
    else:
        return None

class ExplorationEngine:
    DEFAULT_SOLVE_TIMEOUTS = [0.13, 0.26, 0.52, 1.04, 2.08, 4.16, 8.32, 16.64, 33.28]
    SLEEP_WAIT = 0.02

    def __init__(self, funcinv):
        self.invocation = funcinv

        # the input to the function
        self.symbolic_inputs = {}  # string -> SymbolicType
        # initialize
        for n in funcinv.getNames():
            self.symbolic_inputs[n] = funcinv.createArgumentValue(n)

        self.constraints_to_solve = PriorityQueue()
        self.new_constraints = []
        self.num_processed_constraints = 0

        self.path = PathToConstraint(lambda c: self.addConstraint(c), funcinv.name)
        # link up SymbolicObject to PathToConstraint in order to intercept control-flow
        symbolic_type.SymbolicObject.SI = self.path

        solvetimeouts = ExplorationEngine.DEFAULT_SOLVE_TIMEOUTS
        self.solvetimeouts = sorted(set(solvetimeouts))

        self.solver = "cvc"

        workers = 1
        self.worker_pool = {i: None for i in range(1, workers + 1)}
        self.worker_jobs = {i: None for i in range(1, workers + 1)}
        self.finished_queries = Queue()

        # outputs
        self.solved_constraints = set()
        self.outstanding_constraint_attempts = {}
        self.generated_inputs = []
        self.execution_return_values = []


    def addConstraint(self, constraint):
        self.new_constraints.append(constraint)


    def explore(self):
        self._oneExecution()
        starttime = time.time()
        iterations = 1
        max_iterations = 0
        timeout = None
        try:
            while not self._isExplorationComplete():
                if max_iterations != 0 and iterations >= max_iterations:
                    print("Maximum number of iterations reached, terminating")
                    break

                # Check for finished queries
                if not self.finished_queries.empty():
                    print("Processing finished query")
                    ## Select finished query
                    selected_id, selected_timeout, result, model = self.finished_queries.get_nowait()
                    if selected_id in self.solved_constraints:
                        continue
                    selected = self.path.find_constraint(selected_id) # symbolic.constraint.Constraint

                elif self.constraints_to_solve.empty() or self._runningSolvers() == len(self.worker_pool):
                    ## Wait for running queries to finish
                    self._wait()
                    continue

                else:
                    ## Find constraint with free worker
                    peeked = []
                    selected_timeout, selected = None, None
                    while not self.constraints_to_solve.empty():
                        peeked_timeout, peeked_constraint = self.constraints_to_solve.get()
                        candidate_worker = central_queue(self.worker_pool, self.solvetimeouts, peeked_timeout)
                        if candidate_worker is not None:
                            selected_timeout, selected = peeked_timeout, peeked_constraint
                            break
                        else:
                            peeked.append((peeked_timeout, peeked_constraint))

                    for peeked_timeout, peeked_constraint in peeked:
                        self.constraints_to_solve.put((peeked_timeout, peeked_constraint))

                    if selected is None:
                        self._wait()
                        continue

                    if selected.processed:
                        continue

                    self._launch_worker(selected.id, selected_timeout, selected, self.solver)
                    continue

                # Tracking multiple attempts of the same query with different solvers
                self.outstanding_constraint_attempts[(selected.id, selected_timeout)] -= 1

                if selected.id in self.solved_constraints:
                    continue

                if selected.branch_id is not None:
                    print("\t".join(["Solver Result", selected.branch_id, result]))
                    print()

                if model is None:
                    if self._running_constraint(selected.id) is not None or self.outstanding_constraint_attempts[(selected.id, selected_timeout)] > 0:
                        continue
                    timeout_index = self.solvetimeouts.index(selected_timeout)
                    if timeout_index + 1 < len(self.solvetimeouts) and result != "UNSAT":
                            selected.processed = False
                            self.constraints_to_solve.put((self.solvetimeouts[timeout_index + 1], selected))
                    else:
                            from symbolic.predicate import Predicate
                            negated_predicate = Predicate(selected.predicate.symtype, not selected.predicate.result)
                            added_constraint = selected.parent.addChild(negated_predicate)
                            added_constraint.input = None
                    continue
                else:
                    while self._running_constraint(selected.id) is not None:
                        worker_id = self._running_constraint(selected.id)
                        if worker_id is None:
                            continue
                        worker = self.worker_pool[worker_id]
                        worker.terminate()
                        self.worker_pool[worker_id] = None
                        self.worker_jobs[worker_id] = None

                    for name in model.keys():
                        self._updateSymbolicParameter(name, model[name])

                self._oneExecution(selected)

                iterations += 1
                self.num_processed_constraints += 1
                self.solved_constraints.add(selected.id)

        finally:
            for worker_id, worker in self.worker_pool.items():
                if worker is not None:
                    worker.terminate()

        return self.generated_inputs, self.execution_return_values, self.path

    def _running_constraint(self, constraint_id):
        for worker_id, job_info in self.worker_jobs.items():
            if job_info is None:
                continue
            timeout, constraint = job_info
            if constraint_id == constraint.id:
                return worker_id
        return None

    def _wait(self):
        while self.finished_queries.empty() and self._runningSolvers() > 0:
            time.sleep(ExplorationEngine.SLEEP_WAIT)
            for worker_id, worker in self.worker_pool.items():
                if worker is not None:
                    worker.join(ExplorationEngine.SLEEP_WAIT)

    # private

    def _runningSolvers(self):
        for worker_id, worker in self.worker_pool.items():
            if worker is not None and not worker.is_alive():
                worker.terminate()
                self.worker_pool[worker_id] = None
                self.worker_jobs[worker_id] = None
        return sum(1 if solver_worker is not None else 0 for solver_worker in self.worker_pool.values())

    def _launch_worker(self, selected_id, selected_timeout, selected_constraint, solver):
        self.outstanding_constraint_attempts[(selected_id, selected_timeout)] = self.outstanding_constraint_attempts.get((selected_id, selected_timeout), 0) + 1

        worker_id = central_queue(self.worker_pool, self.solvetimeouts, selected_timeout)
        if self.worker_pool[worker_id] is not None:
            running_timeout, running_constraint = self.worker_jobs[worker_id]
            self.constraints_to_solve.put((running_timeout, running_constraint))
            self.worker_pool[worker_id].terminate()
            self.worker_pool[worker_id] = None
            self.worker_jobs[worker_id] = None

        asserts, query = selected_constraint.getAssertsAndQuery()
        p = Process(target=self._solve, args=(
            self.finished_queries, solver, selected_id, selected_timeout, asserts, query))
        self.worker_pool[worker_id] = p
        self.worker_jobs[worker_id] = selected_timeout, selected_constraint
        p.start()

    @staticmethod
    def _solve(finished_queries, solver_type, selected_id, selected_timeout, asserts, query):
        solver_instance = CVCWrapper()
        result, model = solver_instance.findCounterexample(asserts, query, timeout=selected_timeout)
        finished_queries.put((selected_id, selected_timeout, result, model))

    def _updateSymbolicParameter(self, name, val):
        self.symbolic_inputs[name] = self.invocation.createArgumentValue(name, val)

    def _getInputs(self):
        return self.symbolic_inputs.copy()

    def _setInputs(self, d):
        self.symbolic_inputs = d


    def _isExplorationComplete(self):
        num_constr = self.constraints_to_solve.qsize()
        if num_constr == 0 and self._runningSolvers() == 0 and self.finished_queries.empty():
            return True
        else:
            constraints_to_solve = num_constr + self._runningSolvers()
            pending_process = self.finished_queries.qsize()
            processed_constraints = self.num_processed_constraints
            return False

    def _getConcrValue(self, v):
        if isinstance(v, SymbolicType):
            return v.getConcrValue()
        else:
            return v

    def _recordInputs(self):
        args = self.symbolic_inputs
        inputs = [(k, self._getConcrValue(args[k])) for k in args]
        self.generated_inputs.append(inputs)
        print(inputs)

    def _oneExecution(self, expected_path=None):
        self._recordInputs()
        self.path.reset(expected_path)
        try:
            cov = coverage.Coverage(omit=["*pyexz3.py", "*symbolic*", "*pydev*", "*coverage*"], branch=True)
            cov.start()
            ret = self.invocation.callFunction(self.symbolic_inputs)
            cov.stop()
            while len(self.new_constraints) > 0:
                constraint = self.new_constraints.pop()
                constraint.inputs = self._getInputs()
                self.constraints_to_solve.put((self.solvetimeouts[0], constraint))

        except Exception as e:
            print("Exception")
            instrumentation_keywords = {"pyexz3.py", "symbolic", "pydev", "coverage"}
            exc_type, exc_value, exc_traceback = exc_info()
            for filename, line, function, text in reversed(traceback.extract_tb(exc_traceback)):
                if any(instrumentation_keyword in filename for instrumentation_keyword in instrumentation_keywords):
                    continue
                else:
                    e.id = "{}:{}".format(filename, line)
                    print(e.id)
                    break
            ret = e
        print(ret)
        self.execution_return_values.append(ret)
