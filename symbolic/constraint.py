# Copyright: see copyright.txt
import inspect

import coverage


class Constraint(object):
    cnt = 0
    """A constraint is a list of predicates leading to some specific
       position in the code."""

    def __init__(self, parent, last_predicate):
        self.inputs = None
        self.lines_covered = {} # {filename: frozenset(line_number)}
        self.branches_covered = {} # {filename: frozenset((origin_line_number, destination_line_number))}
        self.predicate = last_predicate
        print("Predicate: " + str(last_predicate))
        self.processed = False
        self.parent = parent
        self.children = []
        self.id = self.__class__.cnt
        self.__class__.cnt += 1
        branch = self.predicate.result if self.predicate is not None else ""
        self.branch_id = self._branch_id(inspect.stack(), branch)

    def _branch_id(self, stack, branch):
        instrumentation_keywords = {"pyexz3.py", "symbolic", "pydev", "coverage"}
        for frame, filename, linenum, funcname, context, contextline in stack:
            if any(instrumentation_keyword in filename for instrumentation_keyword in instrumentation_keywords):
                continue
            return "{}:{}:{}".format(filename, linenum, branch)
        return None

    def __eq__(self, other):
        """Two Constraints are equal iff they have the same chain of predicates"""
        if isinstance(other, Constraint):
            if not self.predicate == other.predicate:
                return False
            return self.parent is other.parent
        else:
            return False

    def set_coverage(self, cov: coverage.CoverageData):
        for file in cov.measured_files():
            self.lines_covered[file] = frozenset(cov.lines(file))
            self.branches_covered[file] = frozenset(cov.arcs(file))

    def getAssertsAndQuery(self):
        self.processed = True

        # collect the assertions
        asserts = []
        tmp = self.parent
        while tmp.predicate is not None:
            asserts.append(tmp.predicate)
            tmp = tmp.parent

        return asserts, self.predicate

    def getLength(self):
        if self.parent is None:
            return 0
        return 1 + self.parent.getLength()

    def __str__(self):
        return str(self.predicate) + "  (processed: %s, path_len: %d)" % (self.processed, self.getLength())

    def __repr__(self):
        s = repr(self.predicate) + " (processed: %s)" % self.processed
        if self.parent is not None:
            s += "\n  path: %s" % repr(self.parent)
        return s

    def findChild(self, predicate):
        for c in self.children:
            if predicate == c.predicate:
                return c
        return None

    def addChild(self, predicate):
        assert (self.findChild(predicate) is None)
        c = Constraint(self, predicate)
        self.children.append(c)
        return c

    def __lt__(self, other):
        return self.getLength() > other.getLength()
